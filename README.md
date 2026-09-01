# Ego

Ego is a local, offline-first industrial safety dashboard and spatial monitoring system. It combines a Flask-based web dashboard, live camera feed, local SQLite logging, and real-time telemetry tracking for Android devices and in-factory assets.

## Overview

The project provides:
- A live camera dashboard with industrial safety HUD styling
- A map view for factory zones and live device position tracking
- Local telemetry ingestion from Android clients
- Offline-first storage and event logging
- Multilingual UI support for several language variants
- Hazard capture and active-zone awareness

## Current capabilities

- Flask web app serving the dashboard from `app.py`
- Video feed from `/video_feed`
- Local DB-backed alert logging via SQLite
- Spatial zone telemetry and hazard state management
- Live Android telemetry ingestion at `/api/telemetry`
- Real-time active device list at `/api/live_positions`
- Dashboard polling via `/api/state` every second
- Moving map markers for active devices
- Fullscreen video toggle in the dashboard UI

## Project structure

- `app.py` – main Flask backend and telemetry service
- `templates/index.html` – dashboard UI, map, camera feed, and front-end logic
- `language_utils.py` – language detection support
- `app/` – Android project files and native app code
- `flutter/` – Flutter integration and local dashboard components
- `ego_database.db` – local SQLite database generated at runtime

## Main routes

- `/` – dashboard home page
- `/video_feed` – MJPEG camera stream
- `/api/state` – current system state and live device positions
- `/api/live_positions` – active live telemetry devices after stale filtering
- `/api/telemetry` – POST telemetry from Android clients
- `/api/spatial_alert` – set/update hazard state
- `/api/toggle_capture` – enable/disable capture mode
- `/api/zones` – zone telemetry data

## Telemetry payload format

Android clients can send POST data like this:

```json
{
  "device_id": "android-device-01",
  "lat": 33.5892,
  "lon": -7.6038,
  "speed": 12.5,
  "distance": 40.2
}
```

Expected keys:
- `device_id` (optional, defaults to `android-device`)
- `lat` (required)
- `lon` (required)
- `speed` (optional)
- `distance` (optional)

## Stale-device handling

The system keeps only fresh live positions for a short threshold window:
- `STALE_THRESHOLD_SECONDS = 15`

Any device older than this window is removed from the live positions registry and no longer shown on the map.

## Run locally

1. Open a terminal in the project root.
2. Install dependencies if needed.
3. Start the Flask app:

```bash
python app.py
```

Then open:

```text
http://localhost:5000/
```

## Notes

- This is designed as an offline-first, local-only operational dashboard.
- Camera access may fall back to a synthetic frame when no webcam is available.
- Map tiles are configured for local dark industrial display and attribution remains visible in a subtle style.
- The dashboard is suitable for edge-device or local workstation deployment.

## Status

Current project status is mixed:
- local dashboard foundation is working
- live stream, telemetry ingestion, state API, and map markers are active
- warning/hazard logic and local persistence are in place
- Android build has not been confirmed yet
- JDK 17 has not been installed successfully on this machine yet, so Android native validation remains pending

Next work should focus on completing the Android toolchain setup, verifying the build environment, and then continuing device synchronization and deployment cleanup.
