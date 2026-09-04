# Edge Aura Eye 🛡️👁️

> A production-grade, 100% offline-first tactical Edge AI dashcam and vision safety system designed for high-precision, zero-latency monitoring without cloud dependencies.

---

## 🚀 Overview
**Edge Aura Eye** is an advanced local-first computer vision and driver/industrial safety system. Built with performance and data sovereignty in mind, it operates entirely on-device (`Zero-Cloud`), making it ideal for vehicular and industrial environments where privacy, reliability, and real-time responsiveness are critical.

## 🌟 Key Features
* **100% Offline & Private (Zero-Cloud):** All video frames, inference, and telemetry data stay strictly on your local hardware via `LocalPrivacyGuard`.
* **Dynamic Multilingual HUD:** Instant, full-UI runtime language switching supporting 9 languages (Arabic, English, Amazigh, French, Spanish, Russian, Korean, Chinese, Japanese).
* **Distance-Based Safety Thresholds:**
  * 🟢 **Safe:** > 7.0 meters
  * 🟡 **Warning:** 5.0 - 7.0 meters
  * 🔴 **Critical Emergency:** <= 5.0 meters, **or** an instant critical hazard (fire, smoke, knife, weapon, fall, intrusion, accident) at any distance — triggers automated proactive pre-buffer recording.
  * A detected **person is not, by itself, a hazard label** — a person only escalates the state through the distance/motion thresholds above, so normal foot traffic in an industrial scene does not falsely trip EMERGENCY.
* **Manual Reset / LOTO Discipline:** Once EMERGENCY is triggered, the dashboard **latches** in that state — it does **not** auto-clear when the hazard/proximity condition disappears. An operator must press **"Manual Reset (LOTO)"** to acknowledge and return to SAFE, mirroring lockout-tagout practice.
* **Authenticated Local Telemetry Endpoint:** The `/telemetry` HTTP endpoint (port 8765) requires a bearer token — no device on the local network can inject GPS/speed data without it.
* **Non-Blocking SQLite Blackbox:** Multi-threaded architecture separating camera capture, AI inference, and database commits to maintain a high, stable FPS.
* **Smart Auto-Reconnection:** Resilient camera worker handling disconnections gracefully without freezing the graphical user interface.

## 🛠️ Tech Stack
* **Language:** Python
* **Computer Vision & AI:** OpenCV, Monocular distance estimation logic, YOLO-compatible inference adapters.
* **GUI / HUD:** Modern Tkinter / CustomTkinter Tactical Dashboard.
* **Data Storage:** SQLite3 (Local non-blocking background queue).

## 📋 Installation & Setup
1. **Clone the repository:**
   ```bash
   git clone https://github.com/hajousfn-web/EdgeAuraEye.git
   cd EdgeAuraEye
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python edge_aura_camera_core.py
   ```
   On first launch, the console prints an authorization token for the local
   telemetry endpoint:
   ```
   [edge-aura-eye] /telemetry auth token (send as 'Authorization: Bearer <token>'): <token>
   ```
   Any client posting GPS/speed data to `http://127.0.0.1:8765/telemetry` must
   include that header, or the request is rejected with `401`.

## ⚙️ Configuration (environment variables)
| Variable | Default | Purpose |
|---|---|---|
| `YOLO_MODEL` | `yolov8n.pt` | Path to the YOLO weights file. The stock COCO-pretrained model does **not** include fire/smoke/knife/weapon/fall/intrusion/accident classes — a custom-trained model is required for those to be detected at all. |
| `YOLO_DEVICE` | `cpu` | Inference device passed to Ultralytics (e.g. `cuda:0` on a Jetson/GPU-equipped edge box). |
| `EDGE_AURA_FOCAL_LENGTH_PX` | `700.0` | Camera focal length constant used for monocular distance estimation. **Must be calibrated per camera/lens** — measure a known real-world distance and solve for this value; an uncalibrated default can meaningfully skew the 5m/7m safety thresholds. |
| `EDGE_AURA_TELEMETRY_TOKEN` | (random, printed at startup) | Pin a stable bearer token for `/telemetry` instead of a fresh random one per run — needed if a separate GPS relay device is configured ahead of time. |
| `EDGE_AURA_GNSS_PORT` | `COM3` | Serial port for the optional local GNSS receiver. |

## ⚠️ Known Limitations
* This is a **soft real-time** system (Python/Tkinter, adaptive frame-skip under load, CPU inference by default). It does not provide deterministic, bounded worst-case latency guarantees suitable for a certified hard-real-time safety claim.
* Critical hazard classes (fire, smoke, knife, weapon, fall, intrusion, accident) require a custom-trained detection model; they are not present in the default `yolov8n.pt` weights.

## 📜 License
Distributed under the MIT License. See `LICENSE` for more information.
