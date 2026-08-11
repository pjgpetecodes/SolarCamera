# Solar Eclipse Timelapse Camera (Raspberry Pi 5)

Tkinter fullscreen landscape application for Raspberry Pi 5 + 7" Touch Display 2 + HQ Camera, with:

- live camera preview
- timelapse start/stop
- livestream start/stop (YouTube RTMP)
- exposure controls
- USB destination selection for timelapse output

## Runtime prerequisites on Raspberry Pi OS

1. Install system packages:
   - `python3-picamera2`
   - `python3-tk`
   - `python3-pil.imagetk`
   - `ffmpeg`
   - `rpicam-apps`
2. Install Python dependency:
   - `pip install -r requirements.txt`

## Run

```bash
python -m app.main
```

The app starts fullscreen and uses a landscape 1280x720 UI layout (for a 720x1280 panel mounted in landscape mode).
