#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

echo "[deps] Installing system packages..."
$SUDO apt update
$SUDO apt install -y \
  python3-tk \
  python3-picamera2 \
  python3-pil.imagetk \
  ffmpeg \
  rpicam-apps \
  python3-venv \
  siril

if [[ ! -d ".venv" ]]; then
  echo "[deps] Creating virtual environment..."
  python3 -m venv --system-site-packages .venv
fi

source .venv/bin/activate

echo "[deps] Installing Python dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo
echo "[deps] Done."
echo "Run the app with:"
echo "  ./run_solarcamera.sh"

