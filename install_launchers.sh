#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/petecodes/share/solarcamera"
DESKTOP_DIR="/home/petecodes/Desktop"
APPS_DIR="/home/petecodes/.local/share/applications"

mkdir -p "$DESKTOP_DIR" "$APPS_DIR"

cat > "$DESKTOP_DIR/Solar Camera.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Solar Camera
Comment=Start the Solar Eclipse Timelapse Camera app
Exec=/bin/bash -lc "cd $APP_DIR && ./run_solarcamera.sh"
Path=$APP_DIR
Terminal=true
Categories=Utility;
EOF

cat > "$APPS_DIR/solar-camera.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Solar Camera
Comment=Solar eclipse timelapse camera
Exec=/bin/bash -lc "cd $APP_DIR && ./run_solarcamera.sh"
Path=$APP_DIR
Terminal=true
Categories=Utility;
EOF

chmod +x "$DESKTOP_DIR/Solar Camera.desktop" "$APPS_DIR/solar-camera.desktop"
echo "Created launchers:"
echo "  $DESKTOP_DIR/Solar Camera.desktop"
echo "  $APPS_DIR/solar-camera.desktop"
