from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PIL import Image

try:
    from picamera2 import Picamera2
except ImportError:  # pragma: no cover - only on non-Pi hosts
    Picamera2 = None


FrameCallback = Callable[[Image.Image], None]


class CameraUnavailableError(RuntimeError):
    pass


class CameraService:
    def __init__(self, width: int, height: int, framerate: int) -> None:
        if Picamera2 is None:
            raise CameraUnavailableError("picamera2 is not installed.")
        self.width = width
        self.height = height
        self.framerate = framerate
        self._picam = Picamera2()
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._manual_exposure_us = 8000
        self._manual_analogue_gain = 1.0

        config = self._picam.create_preview_configuration(
            main={"size": (width, height), "format": "RGB888"},
            controls={"FrameRate": framerate},
        )
        self._picam.configure(config)
        self._picam.start()

    def start_preview(self, frame_callback: FrameCallback) -> None:
        if self._running:
            return
        self._running = True

        def worker() -> None:
            while self._running:
                with self._lock:
                    frame_array = self._picam.capture_array()
                # picamera2 preview arrays can arrive as BGR; remap to RGB for Tk display.
                frame_image = Image.fromarray(frame_array[:, :, ::-1], mode="RGB")
                frame_callback(frame_image)

        self._thread = threading.Thread(target=worker, name="preview-worker", daemon=True)
        self._thread.start()

    def stop_preview(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _apply_manual_controls(self) -> None:
        with self._lock:
            self._picam.set_controls(
                {
                    "AeEnable": False,
                    "ExposureTime": int(self._manual_exposure_us),
                    "AnalogueGain": float(self._manual_analogue_gain),
                }
            )

    def set_exposure_us(self, exposure_us: int) -> None:
        self._manual_exposure_us = max(100, int(exposure_us))
        self._apply_manual_controls()

    def set_iso(self, iso: int) -> None:
        clamped_iso = max(100, min(1600, int(iso)))
        self._manual_analogue_gain = clamped_iso / 100.0
        self._apply_manual_controls()

    def set_auto_exposure(self) -> None:
        with self._lock:
            self._picam.set_controls({"AeEnable": True})

    def capture_still(self, output_path: Path) -> None:
        with self._lock:
            self._picam.capture_file(str(output_path))

    def close(self) -> None:
        self.stop_preview()
        with self._lock:
            self._picam.stop()
