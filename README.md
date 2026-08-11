# Solar Eclipse Timelapse Camera

Tkinter fullscreen landscape app for Raspberry Pi 5 + 7" Touch Display 2 + HQ Camera.

Features:
- live camera preview
- timelapse start/stop
- long-exposure astrophotography mode (Milky Way stills, meteor shower sequences)
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

## Astro Mode

Use the **Timelapse Mode / Astro Mode** toggle at the top of the controls panel to
switch between the two capture workflows. Astro Mode is designed for long-exposure
shots such as the Milky Way or Perseid meteor showers, where the standard timelapse
exposure range (up to 60ms) isn't long enough.

- **Exposure**: 1–239 seconds (the maximum supported by the HQ Camera's IMX477 sensor).
  Default: **20 seconds** (a good starting point for Perseids — the standard advice is 15–25s).
- **Gain (ISO 100–3200)**: 1.0–32.0 analogue gain, shown with its ISO equivalent.
  Default: **Gain 16.0 (ISO 1600)**. For Perseids, ISO 1600–3200 (gain 16–32) is recommended;
  raise gain if the sky is dark enough to avoid too much noise.
- **Gap between frames**: pause between shots in sequence mode, to let the sensor cool
  and give storage time to catch up.
- **Capture Single Frame**: takes one long exposure and saves it immediately.
- **Start Astro Sequence / Stop Astro Sequence**: one toggle button starts and stops
  repeated long-exposure capture, useful for catching meteors or building a stack of
  Milky Way frames.

Each capture saves both a JPEG (for quick preview) and a raw DNG (for stacking in
external tools like Siril, DeepSkyStacker, or Sequator). Frames are saved to a
`solar_astro/astro_session_<timestamp>/` folder on the selected USB destination, numbered
`astro_frame_000001.jpg` / `.dng`, etc.

Notes:
- The live preview pauses automatically during each long exposure and resumes
  afterward.
- Timelapse and Astro Mode share the camera, so you can't run both at once — switching
  modes is blocked while either a timelapse or an astro sequence is running.
- Timelapse also uses a single toggle button (`Start Timelapse` / `Stop Timelapse`).
- Livestream also uses a single toggle button (`Start Livestream` / `Stop Livestream`).
- While Timelapse or Astro sequence is running, status text now reports progress:
  each saved frame is announced once, and countdowns show time until the next
  capture (Timelapse) or remaining exposure/next exposure gap (Astro).
- Astro captures lock white balance for each run (single shot or sequence), which
  reduces frame-to-frame colour shifts in night sky scenes.
- Stopping an Astro sequence waits for the current exposure to finish gracefully:
  the button enters a temporary stopping state, then returns to `Start Astro Sequence`
  when shutdown completes.
- No autofocus or star-tracking is provided; for the sharpest Milky Way/meteor shots,
  use a fast wide lens, a solid tripod, and keep exposures short enough to avoid visible
  star trailing for your focal length (the "500 rule" is a good starting point).

## Troubleshooting
- If the camera is unavailable, verify `python3-picamera2` is installed.
- If Pillow’s Tk bindings are missing, install `python3-pil.imagetk`.
- If the app fails to stream, check the on-screen status text and console logs for `[stream]` messages.
