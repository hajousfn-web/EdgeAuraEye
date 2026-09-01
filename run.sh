#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR" || exit 1

if [ -d "$ROOT_DIR/venv" ] && [ -f "$ROOT_DIR/venv/bin/activate" ]; then
  echo "Activating venv..."
  . "$ROOT_DIR/venv/bin/activate"
elif [ -d "$ROOT_DIR/.venv" ] && [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
  echo "Activating .venv..."
  . "$ROOT_DIR/.venv/bin/activate"
else
  echo "No virtual environment detected. Using system Python runtime."
fi

if ! command -v python >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "ERROR: Python is not installed or not available on PATH."
    exit 1
  fi
else
  PYTHON_BIN="python"
fi

for pkg in flask cv2 numpy; do
  if ! "$PYTHON_BIN" -c "import $pkg" >/dev/null 2>&1; then
    echo "Installing missing dependency: $pkg"
    "$PYTHON_BIN" -m pip install flask opencv-python numpy
  fi
done

PORT_URL="http://127.0.0.1:5000"
nohup "$PYTHON_BIN" app.py >/tmp/ego_dashboard.log 2>&1 &

sleep 2

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$PORT_URL" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
  open "$PORT_URL" >/dev/null 2>&1 || true
fi

echo "=================================================="
echo "Ego dashboard is launching in the background."
echo "Open: $PORT_URL"
echo "=================================================="
