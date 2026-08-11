from __future__ import annotations

import datetime as dt
import shlex
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable


CaptureFunc = Callable[[Path], None]


class TimelapseService:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._session_dir: Path | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    def start(self, capture_func: CaptureFunc, output_root: Path, interval_seconds: int) -> Path:
        if self.is_running:
            raise RuntimeError("Timelapse is already running.")
        if interval_seconds <= 0:
            raise ValueError("Interval must be greater than zero.")

        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_dir = output_root / f"session_{timestamp}"
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()

        def run() -> None:
            frame_number = 0
            while not self._stop_event.is_set():
                frame_path = self._session_dir / f"frame_{frame_number:06d}.jpg"
                capture_func(frame_path)
                frame_number += 1
                self._stop_event.wait(interval_seconds)

        self._thread = threading.Thread(target=run, name="timelapse-capture", daemon=True)
        self._thread.start()
        return self._session_dir

    def stop(self) -> None:
        if not self.is_running:
            return
        self._stop_event.set()
        assert self._thread is not None
        self._thread.join(timeout=10)
        self._thread = None

    def render_mp4(self, session_dir: Path, fps: int = 30) -> Path:
        output_path = session_dir / "timelapse.mp4"
        frame_glob = session_dir / "frame_*.jpg"
        cmd = (
            "ffmpeg -hide_banner -loglevel error -y "
            f"-framerate {fps} -pattern_type glob -i {shlex.quote(str(frame_glob))} "
            "-c:v libx264 -pix_fmt yuv420p "
            f"{shlex.quote(str(output_path))}"
        )
        subprocess.run(["bash", "-lc", cmd], check=True)
        return output_path
