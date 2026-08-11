#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

create_venv() {
  rm -rf .venv
  python3 -m venv --system-site-packages .venv
}

if [[ ! -d ".venv" ]]; then
  create_venv
fi

source .venv/bin/activate

if ! python -c "import picamera2" >/dev/null 2>&1; then
  create_venv
  source .venv/bin/activate
fi

if ! python -c "import picamera2" >/dev/null 2>&1; then
  echo "picamera2 is not available system-wide."
  echo "Install it with:"
  echo "  sudo apt update && sudo apt install -y python3-picamera2 rpicam-apps"
  exit 1
fi

if ! python -c "from PIL import ImageTk" >/dev/null 2>&1; then
  echo "PIL.ImageTk is not available."
  echo "Install it with:"
  echo "  sudo apt update && sudo apt install -y python3-pil.imagetk"
  exit 1
fi

python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt
python -m app.main
