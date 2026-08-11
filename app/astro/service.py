from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path
from typing import Callable, Literal

# Called with (jpg_path, dng_path) for each long-exposure frame to capture.
CaptureFunc = Callable[[Path, Path], None]
CaptureEvent = Literal["capturing", "saved"]
CaptureEventCallback = Callable[[CaptureEvent, int, Path], None]


class AstroService:
    """Handles single and sequential long-exposure astrophotography captures.

    Frames are numbered so they can be fed into external stacking tools
    (e.g. Siril, DeepSkyStacker, Sequator) for Milky Way stacks, meteor
    composites, or star trails.
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._session_dir: Path | None = None
        self._frame_count = 0

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def _new_session_dir(self, output_root: Path) -> Path:
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = output_root / f"astro_session_{timestamp}"
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def capture_single(self, capture_func: CaptureFunc, output_root: Path) -> Path:
        if self.is_running:
            raise RuntimeError("An astro sequence is already running.")
        session_dir = self._new_session_dir(output_root)
        jpg_path = session_dir / "astro_frame_000001.jpg"
        dng_path = session_dir / "astro_frame_000001.dng"
        capture_func(jpg_path, dng_path)
        self._session_dir = session_dir
        self._frame_count = 1
        return jpg_path

    def start(
        self,
        capture_func: CaptureFunc,
        output_root: Path,
        gap_seconds: float,
        on_capture_event: CaptureEventCallback | None = None,
    ) -> Path:
        if self.is_running:
            raise RuntimeError("Astro sequence is already running.")
        if gap_seconds < 0:
            raise ValueError("Gap seconds must be zero or greater.")

        self._session_dir = self._new_session_dir(output_root)
        self._frame_count = 0
        self._stop_event.clear()

        def run() -> None:
            frame_number = 1
            while not self._stop_event.is_set():
                jpg_path = self._session_dir / f"astro_frame_{frame_number:06d}.jpg"
                dng_path = self._session_dir / f"astro_frame_{frame_number:06d}.dng"
                if on_capture_event is not None:
                    on_capture_event("capturing", frame_number, jpg_path)
                capture_func(jpg_path, dng_path)
                self._frame_count = frame_number
                if on_capture_event is not None:
                    on_capture_event("saved", frame_number, jpg_path)
                frame_number += 1
                if gap_seconds > 0:
                    self._stop_event.wait(gap_seconds)

        self._thread = threading.Thread(target=run, name="astro-capture", daemon=True)
        self._thread.start()
        return self._session_dir

    def stop(self) -> None:
        if not self.is_running:
            return
        self._stop_event.set()
        assert self._thread is not None
        self._thread.join()
        self._thread = None
