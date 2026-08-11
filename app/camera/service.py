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
        self._preview_paused = threading.Event()
        self._astro_colour_gains: tuple[float, float] | None = None

        self._preview_config = self._picam.create_preview_configuration(
            main={"size": (width, height), "format": "RGB888"},
            controls={"FrameRate": framerate},
        )
        self._picam.configure(self._preview_config)
        self._picam.start()

    def start_preview(self, frame_callback: FrameCallback) -> None:
        if self._running:
            return
        self._running = True

        def worker() -> None:
            while self._running:
                if self._preview_paused.is_set():
                    self._preview_paused.wait(timeout=0.5)
                    continue
                with self._lock:
                    if self._preview_paused.is_set():
                        continue
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

    def reset_astro_white_balance_lock(self) -> None:
        """Force astro captures to pick and lock fresh colour gains next time."""
        self._astro_colour_gains = None

    def _resolve_astro_colour_gains(self) -> tuple[float, float]:
        if self._astro_colour_gains is not None:
            return self._astro_colour_gains
        metadata = self._picam.capture_metadata()
        gains = metadata.get("ColourGains")
        if isinstance(gains, (tuple, list)) and len(gains) >= 2:
            red = float(gains[0])
            blue = float(gains[1])
        else:
            # Stable fallback if metadata doesn't contain colour gains yet.
            red, blue = 2.0, 2.0
        self._astro_colour_gains = (red, blue)
        return self._astro_colour_gains

    def capture_still(self, output_path: Path) -> None:
        with self._lock:
            self._picam.capture_file(str(output_path))

    def capture_long_exposure(
        self,
        jpg_path: Path,
        dng_path: Path,
        exposure_seconds: float,
        gain: float,
    ) -> None:
        """Pause the preview, switch to a still+raw config, and take one long exposure.

        Saves a JPEG (for quick review) and a raw DNG (for stacking) to the given
        paths, then restores the previous preview configuration and controls.
        """
        exposure_us = max(1_000_000, int(exposure_seconds * 1_000_000))
        # Give the sensor a little headroom over the requested exposure time.
        frame_duration_limit = exposure_us + 200_000

        self._preview_paused.set()
        with self._lock:
            try:
                colour_gains = self._resolve_astro_colour_gains()
                still_config = self._picam.create_still_configuration(
                    main={"size": (self.width, self.height)},
                    raw={},
                    controls={
                        "FrameDurationLimits": (frame_duration_limit, frame_duration_limit),
                        "AeEnable": False,
                        "AwbEnable": False,
                        "ColourGains": colour_gains,
                        "ExposureTime": exposure_us,
                        "AnalogueGain": float(gain),
                    },
                )
                self._picam.switch_mode(still_config)
                request = self._picam.capture_request()
                try:
                    request.save("main", str(jpg_path))
                    request.save_dng(str(dng_path))
                finally:
                    request.release()
            finally:
                self._picam.switch_mode(self._preview_config)
                self._picam.set_controls(
                    {
                        "AeEnable": False,
                        "AwbEnable": True,
                        "ExposureTime": int(self._manual_exposure_us),
                        "AnalogueGain": float(self._manual_analogue_gain),
                    }
                )
                self._preview_paused.clear()

    def close(self) -> None:
        self.stop_preview()
        with self._lock:
            self._picam.stop()
