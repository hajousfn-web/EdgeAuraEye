"""Standalone Edge Camera and Active Hazard Detection Dashboard.

Local-first desktop runtime. Camera inference runs off the Tk thread; the UI only
renders the newest frame and consumes bounded telemetry/event queues.
"""

from __future__ import annotations

import json
import math
import os
import queue
import sqlite3
import threading
import time
import tkinter as tk
from tkinter import ttk
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tkinter import ttk
from typing import Any, Deque, Dict, List, Optional, Tuple

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:
    Image = ImageDraw = ImageTk = None

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

try:
    import serial
except ImportError:
    serial = None


Coordinate = Tuple[float, float]
LogRecord = Tuple[float, float, float, float, str, str, float]


class EdgeNavigationEngine:
    """Offline geographic primitives retained for local telemetry consumers."""

    EARTH_RADIUS_KM = 6371.0

    @classmethod
    def haversine_km(cls, start: Coordinate, end: Coordinate) -> float:
        lat1, lon1, lat2, lon2 = map(math.radians, (*start, *end))
        dlat, dlon = lat2 - lat1, lon2 - lon1
        value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return cls.EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

    @classmethod
    def distance_to_route_km(cls, position: Coordinate, route: List[Coordinate]) -> float:
        if not route:
            return float("inf")
        if len(route) == 1:
            return cls.haversine_km(position, route[0])
        latitude_scale = 111.32
        longitude_scale = 111.32 * math.cos(math.radians(position[0]))
        px, py = position[1] * longitude_scale, position[0] * latitude_scale
        nearest = float("inf")
        for start, end in zip(route, route[1:]):
            ax, ay = start[1] * longitude_scale, start[0] * latitude_scale
            bx, by = end[1] * longitude_scale, end[0] * latitude_scale
            dx, dy = bx - ax, by - ay
            length_sq = dx * dx + dy * dy
            factor = 0.0 if length_sq == 0 else ((px - ax) * dx + (py - ay) * dy) / length_sq
            factor = max(0.0, min(1.0, factor))
            nearest = min(nearest, math.hypot(px - (ax + factor * dx), py - (ay + factor * dy)))
        return nearest

    @classmethod
    def check_route_drift(cls, position: Coordinate, route: List[Coordinate], threshold_m: float = 150.0):
        distance_km = cls.distance_to_route_km(position, route)
        return distance_km * 1000.0 > threshold_m, distance_km * 1000.0


class GPSLowPassFilter:
    """Exponential low-pass filter for latitude/longitude samples."""

    def __init__(self, alpha: float = 0.25, initial: Optional[Coordinate] = None):
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be greater than 0 and at most 1")
        self.alpha = alpha
        self._value = initial

    @property
    def value(self) -> Optional[Coordinate]:
        return self._value

    def reset(self, coordinate: Coordinate):
        self._value = coordinate
        return coordinate

    def update(self, coordinate: Coordinate) -> Coordinate:
        if self._value is None:
            return self.reset(coordinate)
        previous_lat, previous_lon = self._value
        self._value = (
            previous_lat + self.alpha * (coordinate[0] - previous_lat),
            previous_lon + self.alpha * (coordinate[1] - previous_lon),
        )
        return self._value


class GNSSSerialReader:
    """Read local NMEA fixes without touching the Tkinter thread."""

    def __init__(self, port: str, output_queue: queue.Queue, baudrate: int = 9600):
        self.port = port
        self.output_queue = output_queue
        self.baudrate = baudrate
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _coordinate(raw: str, hemisphere: str) -> Optional[float]:
        if not raw:
            return None
        degrees = int(float(raw) // 100)
        value = degrees + minutes / 60.0
        return -value if hemisphere in {"S", "W"} else value

    @classmethod
    def parse_nmea(cls, sentence: str) -> Optional[Tuple[float, float, float]]:
        fields = sentence.strip().split(",")
        if fields[0].endswith("RMC") and len(fields) > 7 and fields[2] == "A":
            latitude = cls._coordinate(fields[3], fields[4])
            longitude = cls._coordinate(fields[5], fields[6])
            speed = float(fields[7] or 0.0) * 1.852
            return (latitude, longitude, speed) if latitude is not None and longitude is not None else None
        if fields[0].endswith("GGA") and len(fields) > 9 and fields[6] != "0":
            latitude = cls._coordinate(fields[2], fields[3])
            longitude = cls._coordinate(fields[4], fields[5])
            return (latitude, longitude, 0.0) if latitude is not None and longitude is not None else None
        return None

    def start(self):
        self._thread = threading.Thread(target=self._run, name="local-gnss", daemon=True)
        self._thread.start()

    def _run(self):
        if serial is None:
            self.output_queue.put((0.0, 0.0, 0.0, "pyserial unavailable", "GNSS_ERROR"))
            return
        try:
            connection = serial.Serial(self.port, self.baudrate, timeout=1)
        except Exception as error:
            self.output_queue.put((0.0, 0.0, 0.0, str(error), "GNSS_ERROR"))
            return
        with connection:
            while not self._stop_event.is_set():
                raw = connection.readline().decode("ascii", errors="ignore")
                fix = self.parse_nmea(raw)
                if fix:
                    latitude, longitude, speed = fix
                    self.output_queue.put((latitude, longitude, speed, datetime.now(timezone.utc).isoformat(), "GNSS"))

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


class LocalPrivacyGuard:
    """Offline pixelation helper for sensitive face or plate regions."""

    @staticmethod
    def anonymize_frame(frame, regions, block_size: int = 12):
        if block_size < 2:
            raise ValueError("block_size must be at least 2")
        if cv2 is not None and hasattr(frame, "shape") and hasattr(frame, "__getitem__"):
            height, width = frame.shape[:2]
            for x, y, region_width, region_height in regions:
                left, top = max(0, int(x)), max(0, int(y))
                right = min(width, left + max(0, int(region_width)))
                bottom = min(height, top + max(0, int(region_height)))
                if right <= left or bottom <= top:
                    continue
                roi = frame[top:bottom, left:right]
                small = cv2.resize(roi, (max(1, (right - left) // block_size), max(1, (bottom - top) // block_size)), interpolation=cv2.INTER_AREA)
                frame[top:bottom, left:right] = cv2.resize(small, (right - left, bottom - top), interpolation=cv2.INTER_NEAREST)
            return frame
        raise TypeError("frame must be an OpenCV array")


class LocalTelemetryStore:
    """Threaded SQLite blackbox store using the existing database contract."""

    def __init__(self, database_path: str):
        self.database_path = database_path
        self._requests: "queue.Queue[tuple]" = queue.Queue()
        self._results: "queue.Queue[tuple]" = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, name="camera-sqlite", daemon=True)
        self._thread.start()

    def _worker(self):
        connection = sqlite3.connect(self.database_path)
        connection.execute("""CREATE TABLE IF NOT EXISTS trip_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at TEXT NOT NULL,
            latitude REAL NOT NULL, longitude REAL NOT NULL, speed REAL NOT NULL,
            eta REAL NOT NULL, source TEXT NOT NULL, segment_distance REAL NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS hazard_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at TEXT NOT NULL,
            severity TEXT NOT NULL, label TEXT NOT NULL, confidence REAL NOT NULL,
            details TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS hazard_prebuffer_frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL,
            captured_at REAL NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL,
            speed REAL NOT NULL, jpeg BLOB NOT NULL
        )""")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(trip_logs)")}
        if "segment_distance" not in columns:
            connection.execute("ALTER TABLE trip_logs ADD COLUMN segment_distance REAL NOT NULL DEFAULT 0.0")
        connection.commit()
        while not self._stop.is_set():
            try:
                command = self._requests.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if command[0] == "close":
                    break
                if command[0] == "log":
                    connection.execute("INSERT INTO trip_logs (recorded_at, latitude, longitude, speed, eta, source, segment_distance) VALUES (?, ?, ?, ?, ?, ?, ?)", command[1])
                elif command[0] == "hazard":
                    connection.execute("INSERT INTO hazard_events (recorded_at, severity, label, confidence, details) VALUES (?, ?, ?, ?, ?)", command[1])
                elif command[0] == "commit_prebuffer":
                    _, frames, latitude, longitude, speed = command[1:]
                    connection.execute("INSERT INTO hazard_events (recorded_at, severity, label, confidence, details) VALUES (?, ?, ?, ?, ?)", (datetime.now(timezone.utc).isoformat(), "EMERGENCY", "prebuffer", 1.0, f"{len(frames)} frames committed"))
                    event_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
                    connection.executemany("INSERT INTO hazard_prebuffer_frames (event_id, captured_at, latitude, longitude, speed, jpeg) VALUES (?, ?, ?, ?, ?, ?)", [(event_id, captured_at, latitude, longitude, speed, jpeg) for captured_at, jpeg in frames])
                elif command[0] == "summary":
                    row = connection.execute("SELECT COUNT(*), COALESCE(SUM(segment_distance), 0), MAX(recorded_at) FROM trip_logs").fetchone()
                    hazards = connection.execute("SELECT COUNT(*) FROM hazard_events").fetchone()[0]
                    self._results.put((command[1], row[0], row[1], row[2], hazards))
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
        connection.close()

    def log(self, telemetry: LogRecord):
        self._requests.put(("log", telemetry))

    def log_hazard(self, event: tuple):
        self._requests.put(("hazard", event))

    def commit_prebuffer(self, frames: list, position: Coordinate, speed: float):
        if not frames:
            return
        self._requests.put(("commit_prebuffer", time.time_ns(), list(frames), position[0], position[1], speed))

    def request_summary(self, request_id: int):
        self._requests.put(("summary", request_id))

    def get_results(self):
        results = []
        while True:
            try:
                results.append(self._results.get_nowait())
            except queue.Empty:
                return results

    def close(self):
        self._stop.set()
        self._requests.put(("close",))
        self._thread.join(timeout=2.0)


class TelemetryRequestHandler(BaseHTTPRequestHandler):
    telemetry_queue: "queue.Queue[tuple]"

    def do_POST(self):
        if self.path != "/telemetry":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            latitude, longitude = float(payload["lat"]), float(payload["lon"])
            speed = float(payload.get("speed", 0.0))
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("coordinates out of range")
            self.telemetry_queue.put((latitude, longitude, speed, datetime.now(timezone.utc).isoformat(), "HTTP"))
            body = b'{"ok":true}'
            self.send_response(200)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            body = b'{"ok":false}'
            self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


@dataclass
class Detection:
    label: str
    confidence: float
    x: int
    y: int
    width: int
    height: int
    distance_m: Optional[float] = None


class CameraWorker(threading.Thread):
    """Capture, infer, anonymize, and encode frames away from Tkinter."""

    HAZARD_LABELS = {"fire", "smoke", "knife", "weapon", "fall", "intrusion", "accident"}
    REAL_HEIGHTS_M = {"person": 1.7, "car": 1.5, "truck": 3.0}
    FOCAL_LENGTH_PX = 700.0
    INFERENCE_WIDTH = 640
    TARGET_LATENCY_S = 0.12
    RECONNECT_DELAY_S = 2.0
    MAX_CAPTURE_FAILURES = 3

    def __init__(self, output_queue: queue.Queue, stop_event: threading.Event, privacy_guard: LocalPrivacyGuard):
        super().__init__(name="edge-camera-worker", daemon=True)
        self.output_queue = output_queue
        self.stop_event = stop_event
        self.privacy_guard = privacy_guard
        self.camera = None
        self.model = None
        self.camera_index = None
        self.frame_number = 0
        self.model_status = "MODEL OFFLINE"
        self._previous_centers: Dict[str, Tuple[float, float]] = {}
        self._last_detections: List[Detection] = []
        self._skip_frames = 0
        self._capture_failures = 0
        self._next_reconnect_at = 0.0
        self._camera_status = "CAMERA STARTING"

    def open_camera(self):
        if cv2 is None:
            return None
        for index in (2, 0, 1):
            for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
                camera = cv2.VideoCapture(index, backend)
                if camera.isOpened():
                    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    camera.set(cv2.CAP_PROP_FPS, 20)
                    self.camera_index = index
                    return camera
                camera.release()
        return None

    def release_camera(self):
        if self.camera is not None:
            try:
                self.camera.release()
            except Exception:
                pass
            self.camera = None

    def reconnect_camera_if_due(self):
        now = time.monotonic()
        if self.camera is not None or now < self._next_reconnect_at:
            return
        self._next_reconnect_at = now + self.RECONNECT_DELAY_S
        try:
            self.camera = self.open_camera()
            self._camera_status = "CAMERA ONLINE" if self.camera is not None else "CAMERA RETRY"
            if self.camera is not None:
                self._capture_failures = 0
        except Exception:
            self.release_camera()
            self._camera_status = "CAMERA RETRY"

    def load_model(self):
        if YOLO is None:
            self.model_status = "VISION FALLBACK"
            return
        model_path = os.environ.get("YOLO_MODEL", "yolov8n.pt")
        if not os.path.exists(model_path):
            self.model_status = "VISION FALLBACK"
            return
        try:
            self.model = YOLO(model_path)
            self.model_status = "YOLO ONLINE"
        except Exception:
            self.model_status = "VISION FALLBACK"

    def infer(self, frame, scale: float = 1.0) -> List[Detection]:
        if self.model is None:
            return []
        detections = []
        try:
            results = self.model.predict(frame, verbose=False, conf=0.35, device="cpu")
            names = self.model.names
            for result in results:
                for box in result.boxes:
                    coordinates = box.xyxy[0].tolist()
                    label = str(names[int(box.cls[0])]).lower()
                    x, y = int(coordinates[0] * scale), int(coordinates[1] * scale)
                    width = int((coordinates[2] - coordinates[0]) * scale)
                    height = int((coordinates[3] - coordinates[1]) * scale)
                    real_height = self.REAL_HEIGHTS_M.get(label)
                    distance = self.FOCAL_LENGTH_PX * real_height / height if real_height and height > 0 else None
                    detections.append(Detection(label, float(box.conf[0]), x, y, width, height, distance))
        except Exception:
            self.model_status = "VISION ERROR"
        return detections

    def prepare_inference_frame(self, frame):
        try:
            height, width = frame.shape[:2]
            if width <= self.INFERENCE_WIDTH:
                return frame, 1.0
            scale = self.INFERENCE_WIDTH / width
            return cv2.resize(frame, (self.INFERENCE_WIDTH, max(1, int(height * scale))), interpolation=cv2.INTER_AREA), 1.0 / scale
        except Exception:
            return frame, 1.0

    def update_skip_policy(self, latency: float):
        if latency > self.TARGET_LATENCY_S:
            self._skip_frames = min(4, self._skip_frames + 1)
        elif latency < self.TARGET_LATENCY_S * 0.55:
            self._skip_frames = max(0, self._skip_frames - 1)

    @staticmethod
    def synthetic_frame(width=1280, height=720):
        if cv2 is None:
            return None
        frame = __import__("numpy").zeros((height, width, 3), dtype="uint8")
        frame[:] = (18, 24, 25)
        tick = int(time.monotonic() * 90) % (width - 240)
        cv2.rectangle(frame, (0, 0), (width, 76), (25, 35, 36), -1)
        cv2.putText(frame, "مدخل كاميرا احتياطي", (32, 46), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (125, 245, 207), 2, cv2.LINE_AA)
        cv2.rectangle(frame, (tick + 100, 250), (tick + 240, 430), (65, 120, 110), 2)
        cv2.putText(frame, "لا توجد كاميرا", (tick + 112, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (92, 173, 255), 2, cv2.LINE_AA)
        return frame

    def annotate(self, frame, detections):
        try:
            if cv2 is None or frame is None:
                return frame
            privacy_regions = [(d.x, d.y, d.width, d.height) for d in detections if d.label in {"person", "face", "license plate"}]
            if privacy_regions:
                self.privacy_guard.anonymize_frame(frame, privacy_regions)
            for detection in detections:
                hazard = detection.label in self.HAZARD_LABELS
                color = (70, 80, 255) if hazard else (90, 225, 170)
                cv2.rectangle(frame, (detection.x, detection.y), (detection.x + detection.width, detection.y + detection.height), color, 2)
                distance = f"  {detection.distance_m:.1f}m" if detection.distance_m is not None else ""
                cv2.putText(frame, f"{detection.label.upper()} {detection.confidence:.0%}{distance}", (detection.x, max(24, detection.y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2, cv2.LINE_AA)
            return frame
        except Exception:
            return frame

    def motion_score(self, detections: List[Detection]) -> float:
        current = {
            f"{d.label}:{index}": (d.x + d.width / 2, d.y + d.height / 2)
            for index, d in enumerate(detections)
        }
        if not current or not self._previous_centers:
            self._previous_centers = current
            return 0.0
        distances = []
        for key, center in current.items():
            previous = self._previous_centers.get(key)
            if previous is not None:
                distances.append(math.hypot(center[0] - previous[0], center[1] - previous[1]))
        self._previous_centers = current
        return max(distances, default=0.0)

    def publish(self, frame, detections, fps, motion_score):
        if cv2 is None or frame is None:
            return
        _, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        packet = (encoded.tobytes(), detections, fps, f"{self.model_status} | {self._camera_status}", motion_score)
        try:
            self.output_queue.put_nowait(packet)
        except queue.Full:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                pass
            self.output_queue.put_nowait(packet)

    def run(self):
        try:
            self.load_model()
            self.reconnect_camera_if_due()
        except Exception:
            self._camera_status = "CAMERA RETRY"
        last_time = time.monotonic()
        while not self.stop_event.is_set():
            try:
                self.reconnect_camera_if_due()
                if self.camera is not None:
                    try:
                        ok, frame = self.camera.read()
                    except Exception:
                        ok, frame = False, None
                    if not ok or frame is None:
                        self._capture_failures += 1
                        if self._capture_failures >= self.MAX_CAPTURE_FAILURES:
                            self.release_camera()
                            self._camera_status = "CAMERA RECOVERING"
                        time.sleep(0.02)
                        continue
                    self._capture_failures = 0
                    self._camera_status = "CAMERA ONLINE"
                else:
                    frame = self.synthetic_frame()
                    self._camera_status = "CAMERA FALLBACK"
                    if frame is None:
                        time.sleep(0.2)
                        continue
                    time.sleep(0.04)
                if self.model is not None and self.frame_number % (self._skip_frames + 1) == 0:
                    try:
                        inference_frame, scale = self.prepare_inference_frame(frame)
                        started = time.perf_counter()
                        self._last_detections = self.infer(inference_frame, scale)
                        self.update_skip_policy(time.perf_counter() - started)
                    except Exception:
                        self._last_detections = []
                detections = self._last_detections
                motion_score = self.motion_score(detections)
                frame = self.annotate(frame, detections)
                now = time.monotonic()
                self.publish(frame, detections, 1.0 / max(now - last_time, 0.001), motion_score)
                last_time = now
                self.frame_number += 1
            except Exception:
                self.release_camera()
                self._camera_status = "CAMERA RECOVERING"
                time.sleep(0.05)
        self.release_camera()


class EdgeCameraDashboard(tk.Frame):
    """Dark industrial UI for live edge vision and local hazard operations."""

    POLL_MS = 50
    TELEMETRY_MS = 1000
    PREBUFFER_SECONDS = 8
    PREBUFFER_FPS = 20
    MOTION_WARNING_PIXELS = 18.0
    WARNING_DISTANCE_M = 7.0
    EMERGENCY_DISTANCE_M = 5.0
    LANGUAGE_OPTIONS = (
        ("ar", "العربية"),
        ("en", "English"),
        ("zgh", "ⵜⴰⵎⴰⵣⵉⵖⵜ"),
        ("fr", "Français"),
        ("es", "Español"),
        ("ru", "Русский"),
        ("ko", "한국어"),
        ("zh", "中文"),
        ("ja", "日本語"),
    )
    LOCALIZATION = {
        "ar": {
        "title": "مركز التحكم في الرؤية الميدانية",
        "camera": "المراقبة بالكاميرا المباشرة",
        "status": "حالة التهديد",
        "metrics": "المؤشرات الحية",
        "alerts": "سجل التنبيهات الفورية",
        "telemetry": "البيانات المحلية",
        "distance_card": "المسافة الآمنة",
        "blackbox_card": "حالة الصندوق الأسود",
        "safe": "آمن",
        "warning": "انتباه",
        "emergency": "خطر حرج",
        "camera_online": "الكاميرا متصلة",
        "camera_retry": "إعادة الاتصال بالكاميرا",
        "fallback": "وضع الكاميرا الاحتياطي",
        "language": "اللغة",
        "english": "الإنجليزية",
        "arabic": "العربية الفصحى",
        "initializing": "جار تهيئة الكاميرا...",
        "privacy_ready": "الذاكرة الدائرية ٠٫٠ ثانية | حماية الخصوصية جاهزة",
        "local_processing": "المعالجة المحلية",
        "distance": "أقرب مسافة",
        "no_value": "لا توجد بيانات",
        "distance_value": "{value:.1f} متر",
        "points_summary": "{value} نقطة",
        "seconds": "ثانية",
        "pixels": "بكسل",
        "frame_error": "تعذر عرض إطار الكاميرا",
        "pillow_error": "يلزم تثبيت مكتبة عرض الصور",
        "warning_motion": "انتباه: حركة بقيمة {value} بكسل",
        "emergency_alert": "خطر حرج: {label}، نسبة الثقة {confidence}",
        "buffer_saved": "تم حفظ الذاكرة السابقة: {label}",
        "vision_online": "محرك الرؤية يعمل",
        "vision_fallback": "وضع الرؤية الاحتياطي",
        "camera_reconnecting": "جار إعادة الاتصال بالكاميرا",
        "buffer_meta": "{state} | الذاكرة الدائرية {seconds:.1f} ثانية | الحركة {motion:.1f} بكسل",
        "gateway": "بوابة البيانات المحلية: 127.0.0.1:8765",
        "database": "الصندوق الأسود المحلي: driver_tactical_log.db",
        "gnss_start": "تشغيل تحديد الموقع",
        "gnss_stop": "إيقاف تحديد الموقع",
        "metric_fps": "معدل الإطارات",
        "metric_objects": "الأجسام المتتبعة",
        "metric_buffer": "إطارات الذاكرة الدائرية",
        "metric_state": "حالة الخطر",
        "metric_safe": "دورات الأمان",
        "metric_warning": "دورات الانتباه",
        "metric_emergency": "حالات الخطر الحرج",
        "metric_commits": "عمليات حفظ الذاكرة",
        "metric_model": "محرك الرؤية",
        "metric_points": "نقاط الصندوق الأسود",
        "distance": "أقرب مسافة",
        },
        "en": {
        "title": "EdgeControl // Vision Operations Center",
        "camera": "Live Camera Monitoring",
        "status": "Threat Status",
        "metrics": "Live Metrics",
        "alerts": "Instant Alert Log",
        "telemetry": "Local Telemetry",
        "distance_card": "Safety distance",
        "blackbox_card": "Blackbox status",
        "safe": "SAFE",
        "warning": "WARNING",
        "emergency": "EMERGENCY",
        "camera_online": "Camera connected",
        "camera_retry": "Reconnecting camera",
        "fallback": "Camera fallback mode",
        "language": "Language",
        "english": "English",
        "arabic": "Modern Standard Arabic",
        "initializing": "Initializing camera...",
        "privacy_ready": "Circular buffer 0.0 seconds | Privacy protection ready",
        "local_processing": "Local processing",
        "distance": "Nearest distance",
        "no_value": "No data",
        "distance_value": "{value:.1f} m",
        "points_summary": "{value} points",
        "seconds": "seconds",
        "pixels": "pixels",
        "frame_error": "Unable to render camera frame",
        "pillow_error": "Pillow is required for image preview",
        "warning_motion": "WARNING: motion {value} pixels",
        "emergency_alert": "EMERGENCY: {label}, confidence {confidence}",
        "buffer_saved": "Pre-buffer saved: {label}",
        "vision_online": "Vision engine online",
        "vision_fallback": "Vision fallback mode",
        "camera_reconnecting": "Reconnecting camera",
        "buffer_meta": "{state} | Circular buffer {seconds:.1f} seconds | Motion {motion:.1f} pixels",
        "gateway": "Local data gateway: 127.0.0.1:8765",
        "database": "Local blackbox: driver_tactical_log.db",
        "gnss_start": "Start location service",
        "gnss_stop": "Stop location service",
        "metric_fps": "Frame rate",
        "metric_objects": "Tracked objects",
        "metric_buffer": "Circular buffer frames",
        "metric_state": "Hazard state",
        "metric_safe": "Safe cycles",
        "metric_warning": "Warning cycles",
        "metric_emergency": "Emergency events",
        "metric_commits": "Buffer commits",
        "metric_model": "Vision engine",
        "metric_points": "Blackbox points",
        "distance": "Nearest distance",
        },
        "zgh": {
        "title": "ⵄⵉⵏ ⵏ ⵓⵙⵏⵓⴱⴳ // ⵜⵉⵏⵎⵍ ⵏ ⵓⵙⵏⵓⴱⴳ",
        "camera": "ⴰⵙⵏⵓⴱⴳ ⵙ ⵜⴽⴰⵎⵉⵔⴰ",
        "status": "ⴰⴷⴷⴰⴷ ⵏ ⵓⵎⵏⴰⵣ",
        "metrics": "ⵉⵙⵏⵓⵎⵎⵔⵏ ⵉⵎⵉⵔⴰ",
        "alerts": "ⴰⵎⵢⴰⵡ ⵏ ⵉⵙⵙⵏ",
        "telemetry": "ⵉⵙⴼⴽⴰ ⵏ ⴷⴰⵅⵍ",
        "distance_card": "ⵜⴰⵎⵙⵙⵉⵔⵜ ⵏ ⵓⵎⵏⴰⵣ",
        "blackbox_card": "ⴰⴷⴷⴰⴷ ⵏ ⵓⵙⵏⵓⴱⴳ ⴰⵎⵙⵙⴰⵏ",
        "safe": "ⵉⵎⵏ",
        "warning": "ⵙⵙⵏ",
        "emergency": "ⴰⵎⵏⴰⵣ ⴰⵎⵇⵔⴰⵏ",
        "language": "ⵜⵓⵜⵍⴰⵢⵜ", "english": "ⵜⴰⵏⴳⵍⵉⵣⵜ", "arabic": "ⵜⴰⵄⵔⴰⴱⵜ",
        "initializing": "ⴰⵙⵏⵓⴱⴳ ⵏ ⵜⴽⴰⵎⵉⵔⴰ...", "privacy_ready": "ⴰⵎⵙⵙⴰⵏ ⵏ ⵜⵏⴰⵡⵜ 0.0 ⵏ ⵜⵙⵔⴰⵙ | ⵜⵉⵏⵎⵍ ⵏ ⵜⵏⵎⵍⴰ",
        "local_processing": "ⴰⵙⵙⵏⵓⴱⴳ ⴰⴷⴰⵅⵍⴰⵏ", "distance": "ⵜⴰⵎⵙⵙⵉⵔⵜ ⵜⴰⵎⵣⵡⴰⵔⵓⵜ", "no_value": "ⵓⵍⴰ ⵢⵉⵍⵉ ⵓⵙⵏⵓⵎⵎⵔ",
        "distance_value": "{value:.1f} ⵏ ⵎⵉⵜⵔ", "points_summary": "{value} ⵏ ⵉⵏⵇⵇⵉⴹ",
        "seconds": "ⵜⵉⵙⵔⴰⵙ", "pixels": "ⵉⴱⵉⴽⵙⵍⵏ", "frame_error": "ⵓⵔ ⵉⵣⵎⵉⵔ ⵓⵙⵏⵓⴱⴳ ⵏ ⵓⴼⵔⴰⵎ", "pillow_error": "ⵉⵙⵔⵙ ⵓⵙⵏⵓⴱⴳ ⵏ ⵉⵎⵙⵙⵉⵔⵏ",
        "warning_motion": "ⵙⵙⵏ: ⴰⵎⵙⵙⵉⵔ ⵏ {value} ⵉⴱⵉⴽⵙⵍⵏ", "emergency_alert": "ⴰⵎⵏⴰⵣ: {label}, ⵜⴰⵏⵎⵎⵉⵔⵜ {confidence}", "buffer_saved": "ⵉⵜⵜⵓⵙⵏⵓⴱⴳ ⵓⵙⵏⵓⴱⴳ: {label}",
        "vision_online": "ⴰⵎⵙⵙⵏ ⵏ ⵜⵡⵉⵙⵉ ⵉⵔⵔⴰ", "vision_fallback": "ⴰⵙⵏⵓⴱⴳ ⴰⵎⵙⵙⴰⵏ", "camera_reconnecting": "ⴰⵙⵙⵏⵓⴱⴳ ⵏ ⵜⴽⴰⵎⵉⵔⴰ",
        "buffer_meta": "{state} | ⵜⴰⵏⴰⵡⵜ {seconds:.1f} ⵜⵉⵙⵔⴰⵙ | ⴰⵎⵙⵙⵉⵔ {motion:.1f} ⵉⴱⵉⴽⵙⵍⵏ", "gateway": "ⵜⴰⵏⵓⴹⵜ ⵏ ⵉⵙⴼⴽⴰ: 127.0.0.1:8765", "database": "ⴰⵙⵏⵓⴱⴳ ⴰⵎⵙⵙⴰⵏ: driver_tactical_log.db",
        "gnss_start": "ⴰⵙⵙⵏⵓⴱⴳ ⵏ ⵓⵙⵏⵓⴱⴳ", "gnss_stop": "ⴰⵙⵔⵙ ⵏ ⵓⵙⵏⵓⴱⴳ",
        "metric_fps": "ⴰⵎⵔⵉⵔ ⵏ ⵉⴼⵔⴰⵎⵏ", "metric_objects": "ⵉⵎⵏⵣⴰⵡⵏ ⵉⵜⵜⵓⵙⵏⵓⴱⴳⵏ", "metric_buffer": "ⵉⴼⵔⴰⵎⵏ ⵏ ⵜⵏⴰⵡⵜ", "metric_state": "ⴰⴷⴷⴰⴷ ⵏ ⵓⵎⵏⴰⵣ", "metric_safe": "ⵉⵎⵏ ⵏ ⵉⵎⵉⵔⴰ", "metric_warning": "ⵙⵙⵏ ⵏ ⵉⵎⵉⵔⴰ", "metric_emergency": "ⵉⵎⵏⴰⵣⵏ ⵉⵎⵇⵔⴰⵏⵏ", "metric_commits": "ⵉⵙⵏⵓⴱⴳⵏ", "metric_model": "ⴰⵎⵙⵙⵏ ⵏ ⵜⵡⵉⵙⵉ", "metric_points": "ⵉⵏⵇⵇⵉⴹ ⵏ ⵓⵙⵏⵓⴱⴳ",
        },
        "fr": {
        "title": "Centre de vision Edge Aura", "camera": "Surveillance camera en direct", "status": "Etat de menace", "metrics": "Indicateurs en direct", "alerts": "Journal des alertes", "telemetry": "Telemetrie locale", "distance_card": "Distance de securite", "blackbox_card": "Etat de la boite noire", "safe": "SECURISE", "warning": "ATTENTION", "emergency": "DANGER CRITIQUE", "camera_online": "Camera connectee", "camera_retry": "Reconnexion de la camera", "fallback": "Mode camera de secours", "language": "Langue", "english": "Anglais", "arabic": "Arabe standard", "initializing": "Initialisation de la camera...", "privacy_ready": "Tampon circulaire 0.0 seconde | Protection privee active", "local_processing": "Traitement local", "distance": "Distance la plus proche", "no_value": "Aucune donnee", "distance_value": "{value:.1f} m", "points_summary": "{value} points", "seconds": "secondes", "pixels": "pixels", "frame_error": "Impossible d'afficher l'image", "pillow_error": "Pillow est requis", "warning_motion": "ATTENTION: mouvement {value} pixels", "emergency_alert": "DANGER CRITIQUE: {label}, confiance {confidence}", "buffer_saved": "Tampon sauvegarde: {label}", "vision_online": "Moteur de vision actif", "vision_fallback": "Mode vision de secours", "camera_reconnecting": "Reconnexion de la camera", "buffer_meta": "{state} | Tampon {seconds:.1f} secondes | Mouvement {motion:.1f} pixels", "gateway": "Passerelle locale: 127.0.0.1:8765", "database": "Boite noire locale: driver_tactical_log.db", "gnss_start": "Activer la localisation", "gnss_stop": "Arreter la localisation", "metric_fps": "Images par seconde", "metric_objects": "Objets suivis", "metric_buffer": "Images du tampon", "metric_state": "Etat de menace", "metric_safe": "Cycles securises", "metric_warning": "Cycles d'attention", "metric_emergency": "Alertes critiques", "metric_commits": "Sauvegardes du tampon", "metric_model": "Moteur de vision", "metric_points": "Points de boite noire",
        },
        "es": {
        "title": "Centro de vision Edge Aura", "camera": "Supervision de camara en directo", "status": "Estado de amenaza", "metrics": "Metricas en directo", "alerts": "Registro de alertas", "telemetry": "Telemetria local", "distance_card": "Distancia de seguridad", "blackbox_card": "Estado de caja negra", "safe": "SEGURO", "warning": "ATENCION", "emergency": "PELIGRO CRITICO", "camera_online": "Camara conectada", "camera_retry": "Reconectando camara", "fallback": "Modo de camara auxiliar", "language": "Idioma", "english": "Ingles", "arabic": "Arabe estandar", "initializing": "Iniciando camara...", "privacy_ready": "Buffer circular 0.0 segundos | Privacidad activa", "local_processing": "Procesamiento local", "distance": "Distancia mas cercana", "no_value": "Sin datos", "distance_value": "{value:.1f} m", "points_summary": "{value} puntos", "seconds": "segundos", "pixels": "pixeles", "frame_error": "No se puede mostrar el fotograma", "pillow_error": "Se requiere Pillow", "warning_motion": "ATENCION: movimiento {value} pixeles", "emergency_alert": "PELIGRO CRITICO: {label}, confianza {confidence}", "buffer_saved": "Buffer guardado: {label}", "vision_online": "Motor de vision activo", "vision_fallback": "Modo de vision auxiliar", "camera_reconnecting": "Reconectando camara", "buffer_meta": "{state} | Buffer {seconds:.1f} segundos | Movimiento {motion:.1f} pixeles", "gateway": "Puerta local: 127.0.0.1:8765", "database": "Caja negra local: driver_tactical_log.db", "gnss_start": "Activar ubicacion", "gnss_stop": "Detener ubicacion", "metric_fps": "Fotogramas por segundo", "metric_objects": "Objetos seguidos", "metric_buffer": "Fotogramas del buffer", "metric_state": "Estado de amenaza", "metric_safe": "Ciclos seguros", "metric_warning": "Ciclos de atencion", "metric_emergency": "Eventos criticos", "metric_commits": "Guardados del buffer", "metric_model": "Motor de vision", "metric_points": "Puntos de caja negra",
        },
        "ru": {
        "title": "Центр зрения Edge Aura", "camera": "Прямая камера", "status": "Статус угрозы", "metrics": "Текущие показатели", "alerts": "Журнал тревог", "telemetry": "Локальная телеметрия", "distance_card": "Безопасная дистанция", "blackbox_card": "Статус черного ящика", "safe": "БЕЗОПАСНО", "warning": "ВНИМАНИЕ", "emergency": "КРИТИЧЕСКАЯ ОПАСНОСТЬ", "camera_online": "Камера подключена", "camera_retry": "Переподключение камеры", "fallback": "Резервный режим камеры", "language": "Язык", "english": "Английский", "arabic": "Литературный арабский", "initializing": "Запуск камеры...", "privacy_ready": "Кольцевой буфер 0.0 с | Защита приватности активна", "local_processing": "Локальная обработка", "distance": "Ближайшая дистанция", "no_value": "Нет данных", "distance_value": "{value:.1f} м", "points_summary": "{value} точек", "seconds": "секунд", "pixels": "пикселей", "frame_error": "Не удалось показать кадр", "pillow_error": "Требуется Pillow", "warning_motion": "ВНИМАНИЕ: движение {value} пикселей", "emergency_alert": "КРИТИЧЕСКАЯ ОПАСНОСТЬ: {label}, уверенность {confidence}", "buffer_saved": "Буфер сохранен: {label}", "vision_online": "Модуль зрения активен", "vision_fallback": "Резервный режим зрения", "camera_reconnecting": "Переподключение камеры", "buffer_meta": "{state} | Буфер {seconds:.1f} с | Движение {motion:.1f} пикс.", "gateway": "Локальный шлюз: 127.0.0.1:8765", "database": "Локальный черный ящик: driver_tactical_log.db", "gnss_start": "Включить геолокацию", "gnss_stop": "Остановить геолокацию", "metric_fps": "Кадров в секунду", "metric_objects": "Отслеживаемые объекты", "metric_buffer": "Кадры буфера", "metric_state": "Статус угрозы", "metric_safe": "Безопасные циклы", "metric_warning": "Циклы внимания", "metric_emergency": "Критические события", "metric_commits": "Сохранения буфера", "metric_model": "Модуль зрения", "metric_points": "Точки черного ящика",
        },
        "ko": {
        "title": "Edge Aura 비전 관제 센터", "camera": "실시간 카메라 감시", "status": "위협 상태", "metrics": "실시간 지표", "alerts": "즉시 경보 기록", "telemetry": "로컬 텔레메트리", "distance_card": "안전 거리", "blackbox_card": "블랙박스 상태", "safe": "안전", "warning": "주의", "emergency": "긴급 위험", "camera_online": "카메라 연결됨", "camera_retry": "카메라 재연결 중", "fallback": "카메라 대체 모드", "language": "언어", "english": "영어", "arabic": "현대 표준 아랍어", "initializing": "카메라 초기화 중...", "privacy_ready": "순환 버퍼 0.0초 | 개인정보 보호 활성", "local_processing": "로컬 처리", "distance": "최단 거리", "no_value": "데이터 없음", "distance_value": "{value:.1f} m", "points_summary": "{value}개 지점", "seconds": "초", "pixels": "픽셀", "frame_error": "카메라 프레임 표시 실패", "pillow_error": "Pillow가 필요합니다", "warning_motion": "주의: {value}픽셀 이동", "emergency_alert": "긴급 위험: {label}, 신뢰도 {confidence}", "buffer_saved": "버퍼 저장됨: {label}", "vision_online": "비전 엔진 작동 중", "vision_fallback": "비전 대체 모드", "camera_reconnecting": "카메라 재연결 중", "buffer_meta": "{state} | 순환 버퍼 {seconds:.1f}초 | 이동 {motion:.1f}픽셀", "gateway": "로컬 게이트웨이: 127.0.0.1:8765", "database": "로컬 블랙박스: driver_tactical_log.db", "gnss_start": "위치 서비스 시작", "gnss_stop": "위치 서비스 중지", "metric_fps": "초당 프레임", "metric_objects": "추적 객체", "metric_buffer": "버퍼 프레임", "metric_state": "위협 상태", "metric_safe": "안전 주기", "metric_warning": "주의 주기", "metric_emergency": "긴급 이벤트", "metric_commits": "버퍼 저장 횟수", "metric_model": "비전 엔진", "metric_points": "블랙박스 지점",
        },
        "zh": {
        "title": "Edge Aura 视觉控制中心", "camera": "实时摄像监控", "status": "威胁状态", "metrics": "实时指标", "alerts": "即时警报记录", "telemetry": "本地遥测", "distance_card": "安全距离", "blackbox_card": "黑匣子状态", "safe": "安全", "warning": "注意", "emergency": "紧急危险", "camera_online": "摄像头已连接", "camera_retry": "正在重连摄像头", "fallback": "摄像头备用模式", "language": "语言", "english": "英语", "arabic": "现代标准阿拉伯语", "initializing": "正在初始化摄像头...", "privacy_ready": "循环缓冲 0.0 秒 | 隐私保护已启用", "local_processing": "本地处理", "distance": "最近距离", "no_value": "暂无数据", "distance_value": "{value:.1f} 米", "points_summary": "{value} 个点", "seconds": "秒", "pixels": "像素", "frame_error": "无法显示摄像头画面", "pillow_error": "需要 Pillow", "warning_motion": "注意：移动 {value} 像素", "emergency_alert": "紧急危险：{label}，置信度 {confidence}", "buffer_saved": "缓冲已保存：{label}", "vision_online": "视觉引擎运行中", "vision_fallback": "视觉备用模式", "camera_reconnecting": "正在重连摄像头", "buffer_meta": "{state} | 循环缓冲 {seconds:.1f} 秒 | 移动 {motion:.1f} 像素", "gateway": "本地数据网关：127.0.0.1:8765", "database": "本地黑匣子：driver_tactical_log.db", "gnss_start": "启动定位服务", "gnss_stop": "停止定位服务", "metric_fps": "帧率", "metric_objects": "跟踪对象", "metric_buffer": "缓冲帧数", "metric_state": "威胁状态", "metric_safe": "安全周期", "metric_warning": "注意周期", "metric_emergency": "紧急事件", "metric_commits": "缓冲保存次数", "metric_model": "视觉引擎", "metric_points": "黑匣子点数",
        },
        "ja": {
        "title": "Edge Aura ビジョン管制センター", "camera": "ライブカメラ監視", "status": "脅威ステータス", "metrics": "ライブ指標", "alerts": "即時警報ログ", "telemetry": "ローカルテレメトリ", "distance_card": "安全距離", "blackbox_card": "ブラックボックス状態", "safe": "安全", "warning": "注意", "emergency": "緊急危険", "camera_online": "カメラ接続済み", "camera_retry": "カメラ再接続中", "fallback": "カメラ代替モード", "language": "言語", "english": "英語", "arabic": "現代標準アラビア語", "initializing": "カメラを初期化中...", "privacy_ready": "循環バッファ 0.0秒 | プライバシー保護有効", "local_processing": "ローカル処理", "distance": "最近距離", "no_value": "データなし", "distance_value": "{value:.1f} m", "points_summary": "{value}ポイント", "seconds": "秒", "pixels": "ピクセル", "frame_error": "カメラ映像を表示できません", "pillow_error": "Pillowが必要です", "warning_motion": "注意: {value}ピクセル移動", "emergency_alert": "緊急危険: {label}、信頼度 {confidence}", "buffer_saved": "バッファ保存済み: {label}", "vision_online": "ビジョンエンジン稼働中", "vision_fallback": "ビジョン代替モード", "camera_reconnecting": "カメラ再接続中", "buffer_meta": "{state} | 循環バッファ {seconds:.1f}秒 | 移動 {motion:.1f}ピクセル", "gateway": "ローカルゲートウェイ: 127.0.0.1:8765", "database": "ローカルブラックボックス: driver_tactical_log.db", "gnss_start": "測位サービス開始", "gnss_stop": "測位サービス停止", "metric_fps": "フレームレート", "metric_objects": "追跡対象", "metric_buffer": "バッファフレーム", "metric_state": "脅威状態", "metric_safe": "安全サイクル", "metric_warning": "注意サイクル", "metric_emergency": "緊急イベント", "metric_commits": "バッファ保存回数", "metric_model": "ビジョンエンジン", "metric_points": "ブラックボックスポイント",
        },
    }

    def __init__(self, parent: tk.Misc, database_path="driver_tactical_log.db"):
        super().__init__(parent, bg="#101415")
        self.language = "ar"
        self.ARABIC = self.LOCALIZATION["ar"]
        self._localized_widgets = {}
        self.colors = {"bg": "#101415", "panel": "#171d1e", "card": "#202829", "field": "#111718", "line": "#344345", "cyan": "#7df5d0", "green": "#91ec75", "orange": "#ffb14e", "red": "#ff5c62", "text": "#edf8f4", "muted": "#8da3a3"}
        self._stop_event = threading.Event()
        self._frame_queue: "queue.Queue[tuple]" = queue.Queue(maxsize=2)
        self._telemetry_queue: "queue.Queue[tuple]" = queue.Queue()
        self._prebuffer: Deque[Tuple[float, bytes]] = deque(maxlen=self.PREBUFFER_SECONDS * self.PREBUFFER_FPS)
        self._alert_log: Deque[str] = deque(maxlen=8)
        self._alert_events: Deque[tuple] = deque(maxlen=8)
        self._last_hazard_signature = None
        self._last_hazard_time = 0.0
        self._hazard_state = "SAFE"
        self._state_counts = {"SAFE": 0, "WARNING": 0, "EMERGENCY": 0}
        self._emergency_count = 0
        self._buffer_commit_count = 0
        self._summary_id = 0
        self._last_summary = 0
        self._status_flash_job = None
        self._gnss_reader: Optional[GNSSSerialReader] = None
        self._store = LocalTelemetryStore(database_path)
        self.privacy_guard = LocalPrivacyGuard()
        self.gps_filter = GPSLowPassFilter(initial=(33.5731, -7.5898))
        self.current_position = self.gps_filter.value
        self.last_speed = 0.0
        self._nearest_distance = None
        self._blackbox_count = None
        self.camera_worker = CameraWorker(self._frame_queue, self._stop_event, self.privacy_guard)
        self._server = None
        self._server_thread = None
        self._build_ui()
        self._start_telemetry_server()
        self.camera_worker.start()
        self.after(self.POLL_MS, self._poll_frames)
        self.after(self.TELEMETRY_MS, self._poll_telemetry)
        self.bind("<Destroy>", self._on_destroy)

    def _build_ui(self):
        c = self.colors
        self.header = tk.Frame(self, bg=c["bg"])
        self.header.pack(fill=tk.X, padx=22, pady=(18, 12))
        self.header_title = tk.Label(self.header, text=self._t("title"), bg=c["bg"], fg=c["cyan"], font=("Segoe UI", 16, "bold"), anchor="w")
        self.header_title.pack(side=tk.LEFT)
        self.header_status = tk.Label(self.header, text="المعالجة المحلية", bg=c["bg"], fg=c["muted"], font=("Consolas", 9, "bold"))
        self.header_status.pack(side=tk.RIGHT, pady=5)
        self.language_label = tk.Label(self.header, text=self._t("language"), bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9))
        self.language_label.pack(side=tk.RIGHT, padx=(18, 6), pady=5)
        self.language_selector = ttk.Combobox(self.header, state="readonly", width=20, values=tuple(label for _, label in self.LANGUAGE_OPTIONS))
        self.language_selector.current(0)
        self.language_selector.bind("<<ComboboxSelected>>", self._on_language_selected)
        self.language_selector.pack(side=tk.RIGHT, pady=3)
        tk.Frame(self, bg=c["cyan"], height=2).pack(fill=tk.X, padx=22)
        body = tk.Frame(self, bg=c["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=22, pady=16)
        viewport_card = tk.Frame(body, bg=c["card"], highlightthickness=1, highlightbackground=c["line"])
        viewport_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 14))
        self.camera_title = tk.Label(viewport_card, text=self._t("camera"), bg=c["card"], fg=c["cyan"], font=("Segoe UI", 10, "bold"), anchor="w")
        self.camera_title.pack(fill=tk.X, padx=14, pady=(12, 8))
        self.video_label = tk.Label(viewport_card, text=self._t("initializing"), bg="#080c0d", fg=c["muted"], font=("Consolas", 12), anchor="center")
        self.video_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.camera_meta = tk.Label(viewport_card, text=self._t("privacy_ready"), bg=c["card"], fg=c["muted"], font=("Consolas", 8), anchor="w")
        self.camera_meta.pack(fill=tk.X, padx=14, pady=(0, 10))
        sidebar = tk.Frame(body, bg=c["bg"], width=330)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)
        self.status_card = self._card(sidebar, self._t("status"), c["green"])
        self.status_card.pack(fill=tk.X, pady=(0, 10))
        self.status_dot = tk.Canvas(self.status_card, width=24, height=24, bg=c["card"], highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(14, 8), pady=14)
        self.status_dot_item = self.status_dot.create_oval(4, 4, 20, 20, fill=c["green"], outline="")
        self.status_label = tk.Label(self.status_card, text=self._t("safe"), bg=c["card"], fg=c["green"], font=("Segoe UI", 15, "bold"), anchor="w")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.distance_card = self._card(sidebar, self._t("distance_card"), c["cyan"])
        self.distance_card.pack(fill=tk.X, pady=(0, 10))
        self.distance_value = tk.Label(self.distance_card, text=self._t("no_value"), bg=c["card"], fg=c["cyan"], font=("Consolas", 18, "bold"), anchor="w")
        self.distance_value.pack(fill=tk.X, padx=14, pady=(0, 12))
        self.metrics = self._card(sidebar, self._t("metrics"), c["cyan"])
        self.metrics.pack(fill=tk.X, pady=(0, 10))
        self.metric_labels = {}
        metric_titles = (
            ("fps", "metric_fps"), ("objects", "metric_objects"),
            ("buffer", "metric_buffer"), ("state", "metric_state"),
            ("distance", "distance"),
            ("safe", "metric_safe"), ("warning", "metric_warning"),
            ("emergency", "metric_emergency"), ("commits", "metric_commits"),
            ("model", "metric_model"), ("points", "metric_points"),
        )
        for key, title in metric_titles:
            row = tk.Frame(self.metrics, bg=c["card"])
            row.pack(fill=tk.X, padx=14, pady=3)
            metric_title = tk.Label(row, text=self._t(title), bg=c["card"], fg=c["muted"], font=("Consolas", 8), anchor="w")
            metric_title.pack(side=tk.LEFT)
            self._localized_widgets[title] = metric_title
            label = tk.Label(row, text="--", bg=c["card"], fg=c["text"], font=("Consolas", 9, "bold"), anchor="e")
            label.pack(side=tk.RIGHT)
            self.metric_labels[key] = label
        tk.Label(self.metrics, text="", bg=c["card"]).pack(pady=2)
        self.blackbox_card = self._card(sidebar, self._t("blackbox_card"), c["green"])
        self.blackbox_card.pack(fill=tk.X, pady=(0, 10))
        self.blackbox_value = tk.Label(self.blackbox_card, text=self._t("no_value"), bg=c["card"], fg=c["green"], font=("Consolas", 11, "bold"), anchor="w")
        self.blackbox_value.pack(fill=tk.X, padx=14, pady=(0, 10))
        self.alert_card = self._card(sidebar, self._t("alerts"), c["orange"])
        self.alert_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.alert_text = tk.Text(self.alert_card, height=8, bg=c["field"], fg=c["orange"], insertbackground=c["text"], relief=tk.FLAT, bd=0, font=("Consolas", 8), state=tk.DISABLED)
        self.alert_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.telemetry_card = self._card(sidebar, self._t("telemetry"), c["green"])
        self.telemetry_card.pack(fill=tk.X)
        self.gateway_label = tk.Label(self.telemetry_card, text=self._t("gateway"), bg=c["card"], fg=c["muted"], font=("Consolas", 8), anchor="w")
        self.gateway_label.pack(fill=tk.X, padx=14, pady=(0, 3))
        self.database_label = tk.Label(self.telemetry_card, text=self._t("database"), bg=c["card"], fg=c["muted"], font=("Consolas", 8), anchor="w")
        self.database_label.pack(fill=tk.X, padx=14, pady=(0, 10))
        self.gnss_port = os.environ.get("EDGE_AURA_GNSS_PORT", "COM3")
        self.gnss_button = tk.Button(self.telemetry_card, text=f"{self._t('gnss_start')} // {self.gnss_port}", command=self.toggle_gnss, bg="#21684f", fg=c["text"], activebackground="#2b8968", activeforeground=c["text"], relief=tk.FLAT, bd=0, font=("Segoe UI", 8, "bold"), cursor="hand2")
        self.gnss_button.pack(fill=tk.X, padx=14, pady=(0, 10))

    def _t(self, key, **values):
        return self.LOCALIZATION[self.language][key].format(**values)

    def _on_language_selected(self, _event=None):
        index = self.language_selector.current()
        self.language = self.LANGUAGE_OPTIONS[index][0] if 0 <= index < len(self.LANGUAGE_OPTIONS) else "ar"
        self._apply_language()

    def _apply_language(self):
        self.header_title.config(text=self._t("title"))
        self.language_label.config(text=self._t("language"))
        self.language_selector.configure(values=tuple(label for _, label in self.LANGUAGE_OPTIONS))
        self.camera_title.config(text=self._t("camera"))
        self.distance_card.winfo_children()[0].config(text=self._t("distance_card"))
        self.blackbox_card.winfo_children()[0].config(text=self._t("blackbox_card"))
        self.gateway_label.config(text=self._t("gateway"))
        self.database_label.config(text=self._t("database"))
        self.status_card.winfo_children()[0].config(text=self._t("status"))
        self.metrics.winfo_children()[0].config(text=self._t("metrics"))
        self.alert_card.winfo_children()[0].config(text=self._t("alerts"))
        self.telemetry_card.winfo_children()[0].config(text=self._t("telemetry"))
        for key in ("fps", "objects", "buffer", "state", "safe", "warning", "emergency", "commits", "model", "points"):
            self._localized_widgets[f"metric_{key}"].config(text=self._t(f"metric_{key}"))
        self._localized_widgets["distance"].config(text=self._t("distance"))
        self.status_label.config(text=self._t(self._hazard_state.lower()))
        self.distance_value.config(text=self._t("distance_value", value=self._nearest_distance) if self._nearest_distance is not None else self._t("no_value"))
        self.blackbox_value.config(text=self._t("points_summary", value=self._blackbox_count) if self._blackbox_count is not None else self._t("no_value"))
        self.gnss_button.config(text=f"{self._t('gnss_start')} // {self.gnss_port}")
        self.video_label.config(text=self._t("initializing")) if not hasattr(self, "_photo") else None
        self.camera_meta.config(text=self._t("buffer_meta", state=self._t(self._hazard_state.lower()), seconds=len(self._prebuffer) / self.PREBUFFER_FPS, motion=0.0))
        self._write_alert_log()

    def _card(self, parent, title, accent):
        frame = tk.Frame(parent, bg=self.colors["card"], highlightthickness=1, highlightbackground=self.colors["line"])
        tk.Label(frame, text=title, bg=self.colors["card"], fg=accent, font=("Segoe UI", 9, "bold"), anchor="w").pack(fill=tk.X, padx=14, pady=(10, 9))
        return frame

    def _start_telemetry_server(self):
        server = ThreadingHTTPServer(("127.0.0.1", 8765), TelemetryRequestHandler)
        server.telemetry_queue = self._telemetry_queue
        self._server = server
        self._server_thread = threading.Thread(target=server.serve_forever, name="local-camera-telemetry", daemon=True)
        self._server_thread.start()

    def _poll_frames(self):
        latest = None
        while True:
            try:
                latest = self._frame_queue.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            try:
                jpeg_bytes, detections, fps, model_status, motion_score = latest
                self._prebuffer.append((time.monotonic(), jpeg_bytes))
                self._render_jpeg(jpeg_bytes)
                hazards = [d for d in detections if d.label in CameraWorker.HAZARD_LABELS]
                self._update_detection_state(detections, hazards, fps, model_status, motion_score)
            except Exception:
                self._alert_events.appendleft(("error",))
                self._write_alert_log()
        if self.winfo_exists():
            self.after(self.POLL_MS, self._poll_frames)

    def toggle_gnss(self):
        if self._gnss_reader is not None:
            self._gnss_reader.stop()
            self._gnss_reader = None
            self.gnss_button.config(text=f"{self._t('gnss_start')} // {self.gnss_port}")
            return
        self._gnss_reader = GNSSSerialReader(self.gnss_port, self._telemetry_queue)
        self._gnss_reader.start()
        self.gnss_button.config(text=f"{self._t('gnss_stop')} // {self.gnss_port}")

    def _render_jpeg(self, jpeg_bytes):
        if Image is None or ImageTk is None:
            self.video_label.config(text=self._t("pillow_error"))
            return
        try:
            image = Image.open(__import__("io").BytesIO(jpeg_bytes))
            image.thumbnail((self.video_label.winfo_width() - 20, self.video_label.winfo_height() - 20))
            self._photo = ImageTk.PhotoImage(image)
            self.video_label.config(image=self._photo, text="")
        except Exception:
            self.video_label.config(text=self._t("frame_error"))

    def _update_detection_state(self, detections, hazards, fps, model_status, motion_score):
        c = self.colors
        self.metric_labels["fps"].config(text=f"{fps:.1f}")
        self.metric_labels["objects"].config(text=str(len(detections)))
        self.metric_labels["buffer"].config(text=str(len(self._prebuffer)))
        self.metric_labels["model"].config(text=model_status)
        distances = [d.distance_m for d in detections if d.distance_m is not None]
        nearest_distance = min(distances, default=None)
        self._nearest_distance = nearest_distance
        if "distance" in self.metric_labels:
            self.metric_labels["distance"].config(
                text=f"{nearest_distance:.1f}m" if nearest_distance is not None else "--"
            )
        self.distance_value.config(
            text=self._t("distance_value", value=nearest_distance) if nearest_distance is not None else self._t("no_value")
        )
        previous_state = self._hazard_state
        if hazards or (nearest_distance is not None and nearest_distance <= self.EMERGENCY_DISTANCE_M):
            next_state = "EMERGENCY"
        elif (
            nearest_distance is not None and nearest_distance <= self.WARNING_DISTANCE_M
        ) or motion_score >= self.MOTION_WARNING_PIXELS:
            next_state = "WARNING"
        else:
            next_state = "SAFE"
        self._state_counts[next_state] += 1
        self._hazard_state = next_state
        for key in ("safe", "warning", "emergency"):
            self.metric_labels[key].config(text=str(self._state_counts[key.upper()]))
        self.metric_labels["state"].config(text=next_state)
        state_text = self._t(next_state.lower())
        if next_state == "EMERGENCY":
            signature = ", ".join(sorted({d.label for d in hazards})) or "CLOSE PROXIMITY"
            now = time.monotonic()
            if signature != self._last_hazard_signature or now - self._last_hazard_time > 3:
                self._last_hazard_signature, self._last_hazard_time = signature, now
                confidence = max((d.confidence for d in hazards), default=0.0)
                timestamp = datetime.now().strftime("%H:%M:%S")
                self._alert_events.appendleft(("emergency", timestamp, signature.upper(), f"{confidence:.0%}"))
                self._write_alert_log()
                self._store.log_hazard((datetime.now(timezone.utc).isoformat(), "EMERGENCY", signature, confidence, "pre-buffer retained"))
            if previous_state != "EMERGENCY":
                self._commit_emergency(signature)
            self.status_label.config(text=state_text, fg=c["red"])
            self.status_dot.itemconfig(self.status_dot_item, fill=c["red"])
            if self._status_flash_job is None:
                self._flash_status()
        elif next_state == "WARNING":
            if previous_state != "WARNING":
                self._alert_events.appendleft(("warning", datetime.now().strftime("%H:%M:%S"), f"{motion_score:.1f}"))
                self._write_alert_log()
            self.status_label.config(text=state_text, fg=c["orange"])
            self.status_dot.itemconfig(self.status_dot_item, fill=c["orange"])
            if self._status_flash_job is None:
                self._flash_status()
        else:
            if self._status_flash_job is not None:
                self.after_cancel(self._status_flash_job)
                self._status_flash_job = None
            self.status_label.config(text=state_text, fg=c["green"])
            self.status_dot.itemconfig(self.status_dot_item, fill=c["green"])
        runtime_status = self._t("vision_online") if "ONLINE" in model_status else self._t("vision_fallback")
        if "RECOVERING" in model_status or "RETRY" in model_status:
            runtime_status = self._t("camera_reconnecting")
        self.header_status.config(text=runtime_status)
        self.camera_meta.config(text=self._t("buffer_meta", state=state_text, seconds=len(self._prebuffer) / self.PREBUFFER_FPS, motion=motion_score))

    def _commit_emergency(self, signature: str):
        self._emergency_count += 1
        self._buffer_commit_count += 1
        self.metric_labels["emergency"].config(text=str(self._emergency_count))
        self.metric_labels["commits"].config(text=str(self._buffer_commit_count))
        self._store.commit_prebuffer(
            list(self._prebuffer), self.current_position, self.last_speed
        )
        self._alert_events.appendleft(("commit", datetime.now().strftime("%H:%M:%S"), signature.upper()))
        self._write_alert_log()
        self.bell()

    def _flash_status(self):
        if not self.winfo_exists() or self._hazard_state == "SAFE":
            self._status_flash_job = None
            return
        current = self.status_label.cget("fg")
        base_color = self.colors["red"] if self._hazard_state == "EMERGENCY" else self.colors["orange"]
        next_color = self.colors["orange"] if current == base_color else base_color
        self.status_label.config(fg=next_color)
        self.status_dot.itemconfig(self.status_dot_item, fill=next_color)
        self._status_flash_job = self.after(450, self._flash_status)

    def _write_alert_log(self):
        self.alert_text.config(state=tk.NORMAL)
        self.alert_text.delete("1.0", tk.END)
        rendered = []
        for event in self._alert_events:
            if event[0] == "error":
                rendered.append(self._t("frame_error"))
            elif event[0] == "warning":
                rendered.append(f"{event[1]}  {self._t('warning_motion', value=event[2])}")
            elif event[0] == "emergency":
                rendered.append(f"{event[1]}  {self._t('emergency_alert', label=event[2], confidence=event[3])}")
            else:
                rendered.append(f"{event[1]}  {self._t('buffer_saved', label=event[2])}")
        empty = "لا توجد تنبيهات نشطة" if self.language == "ar" else "No active alerts"
        self.alert_text.insert("1.0", "\n".join(rendered) or empty)
        self.alert_text.config(state=tk.DISABLED)

    def _poll_telemetry(self):
        try:
            while True:
                try:
                    latitude, longitude, speed, recorded_at, source = self._telemetry_queue.get_nowait()
                except queue.Empty:
                    break
                if latitude is None or longitude is None:
                    continue
                self.current_position = self.gps_filter.update((latitude, longitude))
                self.last_speed = speed
                self._store.log((self.current_position[0], self.current_position[1], speed, 0.0, recorded_at, source, 0.0))
            self._summary_id += 1
            self._last_summary = self._summary_id
            self._store.request_summary(self._last_summary)
            for result in self._store.get_results():
                if result[0] == self._last_summary:
                    self._blackbox_count = result[1]
                    self.metric_labels["points"].config(text=str(result[1]))
                    self.blackbox_value.config(text=self._t("points_summary", value=result[1]))
        except Exception:
            pass
        if self.winfo_exists():
            self.after(self.TELEMETRY_MS, self._poll_telemetry)

    def _on_destroy(self, event=None):
        if event is not None and event.widget is not self:
            return
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        if self._status_flash_job is not None:
            self.after_cancel(self._status_flash_job)
            self._status_flash_job = None
        if self._gnss_reader is not None:
            self._gnss_reader.stop()
            self._gnss_reader = None
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._store.close()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("EdgeControl // Vision Ops")
    root.geometry("1420x820")
    root.minsize(1080, 680)
    dashboard = EdgeCameraDashboard(root)
    dashboard.pack(fill=tk.BOTH, expand=True)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
