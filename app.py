import os
import sqlite3
import time
from datetime import datetime, timezone

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request

from language_utils import LanguageDetectorEngine

app = Flask(__name__)
LANGUAGE_DETECTOR = LanguageDetectorEngine()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ego_database.db')
SYSTEM_NAME = 'Ego'


def utc_now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS zone_alert_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zone TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            event_time TEXT NOT NULL,
            system_name TEXT NOT NULL DEFAULT 'Ego'
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


def record_alert(zone, status, message):
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO zone_alert_logs (zone, status, message, event_time, system_name) VALUES (?, ?, ?, ?, ?)',
        (zone, status, message, utc_now_iso(), SYSTEM_NAME),
    )
    conn.commit()
    conn.close()


ZONE_ALIASES = {
    'gate-a': 'Zone A - Main Corridor',
    'zone-a-main-corridor': 'Zone A - Main Corridor',
    'zone a - main corridor': 'Zone A - Main Corridor',
    'zone a': 'Zone A - Main Corridor',
    'zone-b-loading-dock': 'Zone B - Loading Dock',
    'zone b - loading dock': 'Zone B - Loading Dock',
    'zone b': 'Zone B - Loading Dock',
    'zone-c-storage-warehouse': 'Zone C - Storage Warehouse',
    'zone c - storage warehouse': 'Zone C - Storage Warehouse',
    'zone c': 'Zone C - Storage Warehouse',
    'zone-d-assembly-line': 'Zone D - Assembly Line',
    'zone d - assembly line': 'Zone D - Assembly Line',
    'zone d': 'Zone D - Assembly Line',
    'loading-bay': 'Zone B - Loading Dock',
    'assembly': 'Zone D - Assembly Line',
    'warehouse': 'Zone C - Storage Warehouse',
}

ZONE_TELEMETRY = {
    'Zone A - Main Corridor': {'title': 'Zone A - Main Corridor', 'status': 'Secure', 'threat': 'Low', 'occupancy': 12, 'latency': 24},
    'Zone B - Loading Dock': {'title': 'Zone B - Loading Dock', 'status': 'Under Watch', 'threat': 'Medium', 'occupancy': 27, 'latency': 36},
    'Zone C - Storage Warehouse': {'title': 'Zone C - Storage Warehouse', 'status': 'Alert', 'threat': 'High', 'occupancy': 9, 'latency': 41},
    'Zone D - Assembly Line': {'title': 'Zone D - Assembly Line', 'status': 'Secure', 'threat': 'Low', 'occupancy': 18, 'latency': 19},
}


def normalize_zone(zone):
    if zone is None:
        return 'Zone A - Main Corridor'
    zone_name = str(zone).strip()
    lowered = zone_name.lower()
    return ZONE_ALIASES.get(lowered, zone_name)


SPATIAL_ALERT_STATE = {
    'alert_mode': False,
    'active_zone': 'Zone A - Main Corridor',
    'last_alert': 'No active hazard observed',
    'last_updated': utc_now_iso(),
}

STALE_THRESHOLD_SECONDS = 15
LIVE_POSITIONS = {}


def get_fresh_live_positions():
    now = datetime.now(timezone.utc)
    fresh_positions = {}
    for device_id, position in list(LIVE_POSITIONS.items()):
        last_updated = position.get('last_updated')
        if not last_updated:
            continue
        try:
            last_dt = datetime.strptime(last_updated, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if (now - last_dt).total_seconds() <= STALE_THRESHOLD_SECONDS:
            fresh_positions[device_id] = position

    LIVE_POSITIONS.clear()
    LIVE_POSITIONS.update(fresh_positions)
    return list(fresh_positions.values())


DEFAULT_CAMERA_INDEXES = [0, 2, 1]


def create_camera():
    for index in DEFAULT_CAMERA_INDEXES:
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            try:
                camera = cv2.VideoCapture(index, backend)
            except Exception:
                continue
            if camera is not None and camera.isOpened():
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                camera.set(cv2.CAP_PROP_FPS, 15)
                return camera, index
            try:
                camera.release()
            except Exception:
                pass
    return None, 0


camera, camera_index = create_camera()


def make_synthetic_frame(message='Camera Offline / Synthetic fallback active'):
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:] = (10, 15, 22)
    cv2.rectangle(frame, (120, 120), (1160, 600), (26, 38, 66), 2)
    cv2.line(frame, (160, 520), (1120, 520), (0, 240, 255), 2)
    cv2.circle(frame, (640, 330), 120, (0, 240, 255), 2)
    cv2.putText(frame, 'Ego', (520, 280), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.putText(frame, 'LOCAL MONITORING', (420, 340), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (56, 189, 248), 2, cv2.LINE_AA)
    cv2.putText(frame, message, (160, 430), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (248, 113, 113), 2, cv2.LINE_AA)
    cv2.putText(frame, 'Synthetic feed / camera fallback active', (280, 500), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def make_placeholder_frame(message='Camera Offline / Live fallback active'):
    return make_synthetic_frame(message)


def read_camera_frame():
    global camera, camera_index

    if camera is None:
        camera, camera_index = create_camera()

    if camera is not None and camera.isOpened():
        try:
            success, frame = camera.read()
            if success and frame is not None and frame.size > 0:
                return frame
        except Exception as exc:
            print(f'Camera read failed: {exc}')

        try:
            camera.release()
        except Exception:
            pass
        camera = None
        camera, camera_index = create_camera()
        if camera is not None and camera.isOpened():
            return make_placeholder_frame('Camera reconnected - live stream restored')

    return make_synthetic_frame('Camera unavailable - synthetic fallback active')


def append_hud(frame):
    text = f"Ego • LIVE • CAM {camera_index} • {datetime.now().strftime('%H:%M:%S')}"
    cv2.putText(frame, text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(frame, f"Active Zone: {SPATIAL_ALERT_STATE['active_zone']}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1, cv2.LINE_AA)
    return frame


def generate_frames():
    target_fps = 15
    frame_interval = 1.0 / target_fps
    last_time = time.time()

    while True:
        frame = read_camera_frame()
        current_time = time.time()
        elapsed = current_time - last_time
        if elapsed >= frame_interval:
            last_time = current_time
            frame = append_hud(frame)
            ok, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
            if not ok:
                continue
            frame_bytes = buffer.tobytes()
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
            )
        time.sleep(0.025)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/telemetry', methods=['POST'])
def api_telemetry():
    payload = request.get_json(silent=True) or {}
    device_id = payload.get('device_id') or payload.get('deviceId') or 'android-device'
    try:
        lat = float(payload.get('lat', 33.5892))
        lon = float(payload.get('lon', -7.6038))
        speed = float(payload.get('speed', 0.0))
        distance = float(payload.get('distance', 0.0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid telemetry payload'}), 400

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({'success': False, 'error': 'lat/lon out of range'}), 400

    LIVE_POSITIONS[device_id] = {
        'device_id': device_id,
        'lat': lat,
        'lon': lon,
        'speed': speed,
        'distance': distance,
        'last_updated': utc_now_iso(),
    }

    return jsonify({
        'success': True,
        'device_id': device_id,
        'lat': lat,
        'lon': lon,
        'speed': speed,
        'distance': distance,
        'updated_at': LIVE_POSITIONS[device_id]['last_updated'],
    })


@app.route('/api/live_positions')
def api_live_positions():
    fresh_positions = get_fresh_live_positions()
    return jsonify({
        'count': len(fresh_positions),
        'devices': fresh_positions,
    })


@app.route('/api/state')
def api_state():
    if SPATIAL_ALERT_STATE['alert_mode']:
        status = 'HAZARD_ACTIVE'
    elif SPATIAL_ALERT_STATE['active_zone']:
        status = 'TRACKING'
    else:
        status = 'IDLE'

    return jsonify(
        {
            'system': SYSTEM_NAME,
            'mode': 'Offline-First Spatial AI',
            'status': status,
            'camera_index': camera_index,
            'camera_ready': bool(camera is not None and camera.isOpened()),
            'fps': 15,
            'edge_latency_ms': 8.4,
            'storage_status': 'Safe' if not SPATIAL_ALERT_STATE['alert_mode'] else 'Warning',
            'db': 'Ego SQLite Local DB',
            'network': 'Zero-Cloud / Local Only',
            'updated_at': utc_now_iso(),
            'alert_mode': SPATIAL_ALERT_STATE['alert_mode'],
            'active_zone': SPATIAL_ALERT_STATE['active_zone'],
            'last_alert': SPATIAL_ALERT_STATE['last_alert'],
            'fsm_state': status,
            'live_positions': get_fresh_live_positions(),
            'coordinates': {
                'Zone A - Main Corridor': [33.6065, -7.6400],
                'Zone B - Loading Dock': [33.5870, -7.6300],
                'Zone C - Storage Warehouse': [33.5785, -7.5970],
                'Zone D - Assembly Line': [33.5998, -7.5880],
            }.get(SPATIAL_ALERT_STATE['active_zone'], [33.5892, -7.6038]),
        }
    )


@app.route('/api/zones')
def api_zones():
    zone = request.args.get('zone')
    zone_name = normalize_zone(zone)
    if zone_name in ZONE_TELEMETRY:
        data = ZONE_TELEMETRY[zone_name]
        return jsonify({**data, 'zone': zone_name})
    return jsonify({}), 404


@app.route('/api/spatial_alert', methods=['POST'])
def spatial_alert():
    payload = request.get_json(silent=True) or {}
    zone = normalize_zone(payload.get('zone', 'Zone A - Main Corridor'))
    message = payload.get('message', f'Active hazard in {zone}')

    SPATIAL_ALERT_STATE['alert_mode'] = True
    SPATIAL_ALERT_STATE['active_zone'] = zone
    SPATIAL_ALERT_STATE['last_alert'] = message
    SPATIAL_ALERT_STATE['last_updated'] = utc_now_iso()
    record_alert(zone, 'Alert', message)

    return jsonify({
        'success': True,
        'alert_mode': True,
        'active_zone': zone,
        'last_alert': message,
        'updated_at': SPATIAL_ALERT_STATE['last_updated'],
    })


@app.route('/api/spatial_state')
def spatial_state():
    return jsonify(SPATIAL_ALERT_STATE)


@app.route('/api/toggle_capture')
def toggle_capture():
    status_str = request.args.get('status', 'false')
    zone = normalize_zone(request.args.get('zone', SPATIAL_ALERT_STATE['active_zone']))
    is_capturing_active = (status_str.lower() == 'true')
    SPATIAL_ALERT_STATE['active_zone'] = zone
    if is_capturing_active:
        SPATIAL_ALERT_STATE['alert_mode'] = True
        SPATIAL_ALERT_STATE['last_alert'] = f'Hazard Capture activated on {zone}.'
        record_alert(zone, 'Capture Active', SPATIAL_ALERT_STATE['last_alert'])
    else:
        SPATIAL_ALERT_STATE['alert_mode'] = False
        SPATIAL_ALERT_STATE['last_alert'] = f'Hazard Capture paused for {zone}.'
        record_alert(zone, 'Capture Paused', SPATIAL_ALERT_STATE['last_alert'])
    SPATIAL_ALERT_STATE['last_updated'] = utc_now_iso()
    return jsonify({"success": True, "capturing": is_capturing_active, "zone": zone, "alert_mode": SPATIAL_ALERT_STATE['alert_mode']})


@app.route('/api/logs', methods=['GET'])
def api_logs():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, zone, status, message, event_time, system_name FROM zone_alert_logs ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    logs = [dict(row) for row in rows]
    return jsonify({'system': SYSTEM_NAME, 'logs': logs})


@app.route('/api/detect-language', methods=['POST'])
def detect_language():
    payload = request.get_json(silent=True) or {}
    text = payload.get('text', '')
    result = LANGUAGE_DETECTOR.detect(text)
    return jsonify(result)


@app.route('/health')
def health():
    return jsonify({'ok': True, 'camera_ready': bool(camera is not None and camera.isOpened())})


if __name__ == '__main__':
    print('Launching Ego dashboard on http://127.0.0.1:5000')
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
