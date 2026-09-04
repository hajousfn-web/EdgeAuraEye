# Edge Aura Eye 🛡️👁️

> A production-grade, 100% offline-first tactical Edge AI dashcam and vision safety system designed for high-precision, zero-latency monitoring without cloud dependencies.

---

## 🚀 Overview
**Edge Aura Eye** is an advanced local-first computer vision and driver/industrial safety system. Built with performance and data sovereignty in mind, it operates entirely on-device (`Zero-Cloud`), making it ideal for vehicular and industrial environments where privacy, reliability, and real-time responsiveness are critical.

## 🌟 Key Features
* **100% Offline & Private (Zero-Cloud):** All video frames, inference, and telemetry data stay strictly on your local hardware via `LocalPrivacyGuard`.
* **Dynamic Multilingual HUD:** Instant, full-UI runtime language switching supporting 9 languages (Arabic, English, Amazigh, French, Spanish, Russian, Korean, Chinese, Japanese).
* **Moroccan Legal Safety Thresholds:** 
  * 🟢 **Safe:** > 7.0 meters
  * 🟡 **Warning:** 5.0 - 7.0 meters
  * 🔴 **Critical Emergency:** <= 5.0 meters (triggers automated proactive pre-buffer recording).
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
   git clone [https://github.com/hajousfn-web/EdgeAuraEye.git](https://github.com/hajousfn-web/EdgeAuraEye.git)
   cd EdgeAuraEye
```

1. **Install dependencies:**

Bash

```
pip install -r requirements.txt
```
2. **Run the application:**

Bash

```
python edge_aura_camera_core.py
```

## 📜 License
Distributed under the MIT License. See `LICENSE` for more information.
