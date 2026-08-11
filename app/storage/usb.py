from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UsbMount:
    device: str
    mount_point: Path
    fstype: str


class UsbStorageService:
    def list_mounts(self) -> list[UsbMount]:
        mounts: list[UsbMount] = []
        for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            device, mount, fstype = parts[0], parts[1], parts[2]
            if not device.startswith("/dev/sd"):
                continue
            mount_path = Path(mount)
            if mount_path.exists():
                mounts.append(UsbMount(device=device, mount_point=mount_path, fstype=fstype))
        return mounts

    def ensure_writable(self, mount_point: Path) -> bool:
        test_path = mount_point / ".write_test"
        try:
            test_path.write_text("ok", encoding="utf-8")
            test_path.unlink()
        except OSError:
            return False
        return True

    def session_root(self, mount_point: Path, folder_name: str = "solar_timelapse") -> Path:
        target = mount_point / folder_name
        target.mkdir(parents=True, exist_ok=True)
        return target
