# Solar Eclipse Timelapse Camera

Tkinter fullscreen landscape app for Raspberry Pi 5 + 7" Touch Display 2 + HQ Camera.

Features:
- live camera preview
- timelapse start/stop
- YouTube livestream start/stop
- exposure and ISO controls
- USB destination selection for timelapse output
- saved stream/camera settings

## Hardware
- Raspberry Pi 5
- Raspberry Pi HQ Camera
- Telephoto lens
- 7" Touch Display 2
- USB memory stick for timelapse storage

## Screen layout
The app is designed for a **720x1280 panel mounted in landscape**, so the UI targets an effective **1280x720** landscape layout.

## Install

1. Update packages:
   ```bash
   sudo apt update
   ```
2. Install required system packages:
   ```bash
   sudo apt install -y python3-tk python3-picamera2 python3-pil.imagetk ffmpeg rpicam-apps python3-venv
   ```
3. Go to the project folder:
   ```bash
   cd /home/petecodes/share/solarcamera
   ```
4. Install Python dependencies in the app virtual environment:
   ```bash
   ./run_solarcamera.sh
   ```
   The launcher will create `.venv` automatically if needed and install Python packages from `requirements.txt`.

## First boot checklist

1. Boot the Raspberry Pi into Raspberry Pi OS with the HQ camera connected.
2. Confirm the display is mounted in **landscape** orientation.
3. Plug in the USB memory stick you want to use for timelapse storage.
4. Confirm the camera works in the desktop environment if needed.
5. Open the app using `./run_solarcamera.sh` or the desktop shortcut.
6. In the app, select the USB destination before starting a timelapse.
7. Open **Configure YouTube Stream** and save your RTMP URL and stream key before streaming.

## Run

```bash
cd /home/petecodes/share/solarcamera
./run_solarcamera.sh
```

You can also start it from the desktop shortcut:

```bash
~/Desktop/Solar\ Camera.desktop
```

## Create launchers

To create both the desktop shortcut and the start-menu entry:

```bash
cd /home/petecodes/share/solarcamera
./install_launchers.sh
```

This creates:
- `~/Desktop/Solar Camera.desktop`
- `~/.local/share/applications/solar-camera.desktop`

## Stop

```bash
cd /home/petecodes/share/solarcamera
./stop_solarcamera.sh
```

## Notes
- The app starts fullscreen.
- Press **Esc** or use **Quit App** to exit.
- Timelapse output is saved to the selected USB drive.
- YouTube stream settings are saved in `~/.config/solarcamera/settings.json`.
- Livestreaming uses the app preview frames, so the preview stays visible while streaming.

## Troubleshooting
- If the camera is unavailable, verify `python3-picamera2` is installed.
- If Pillow’s Tk bindings are missing, install `python3-pil.imagetk`.
- If the app fails to stream, check the on-screen status text and console logs for `[stream]` messages.
