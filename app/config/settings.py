from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    stream_url: str = "rtmp://a.rtmp.youtube.com/live2"
    stream_key: str = ""
    default_interval_seconds: int = 2
    default_exposure_us: int = 8000
    default_iso: int = 100
    frame_width: int = 1280
    frame_height: int = 720
    framerate: int = 30
    bitrate: str = "4500k"
    default_astro_exposure_seconds: int = 15
    default_astro_gain: float = 8.0
    default_astro_gap_seconds: int = 2


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return AppSettings(**data)

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
