from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


StatusCallback = Callable[[str], None]


@dataclass(frozen=True)
class StackResult:
    success: bool
    output_path: Path | None
    log_path: Path
    error: str | None = None
    preview_path: Path | None = None


class StackingService:
    """Runs on-device starfield stacking with Siril CLI."""

    def __init__(self) -> None:
        self._cached_siril_path: str | None = None

    def check_siril_available(self) -> tuple[bool, str]:
        if self._cached_siril_path is None:
            self._cached_siril_path = shutil.which("siril-cli") or shutil.which("siril")
        if self._cached_siril_path is None:
            return False, "Siril CLI is not installed. Install with: sudo apt install -y siril"
        return True, self._cached_siril_path

    def count_jpg_frames(self, session_dir: Path) -> int:
        return len(list(session_dir.glob("astro_frame_*.jpg")))

    def stack_starfield(
        self,
        session_dir: Path,
        *,
        min_frames: int = 3,
        status_callback: StatusCallback | None = None,
    ) -> StackResult:
        def emit(message: str) -> None:
            if status_callback is not None:
                status_callback(message)

        available, siril = self.check_siril_available()
        stacked_dir = session_dir / "stacked"
        stacked_dir.mkdir(parents=True, exist_ok=True)
        log_path = stacked_dir / "stack.log"
        # Siril outputs FITS by default; we look for .fit
        output_fit = stacked_dir / "stacked_starfield.fit"

        if not available:
            return StackResult(False, None, log_path, error=siril)
        if not session_dir.exists():
            return StackResult(False, None, log_path, error=f"Session directory not found: {session_dir}")

        frame_count = self.count_jpg_frames(session_dir)
        if frame_count < min_frames:
            return StackResult(
                False,
                None,
                log_path,
                error=f"Need at least {min_frames} astro JPG frames to stack (found {frame_count}).",
            )

        # Copy only JPEGs into a dedicated lights/ subdir so Siril does not pick
        # up DNG/RAW files alongside them (mixed formats break CFA detection).
        lights_dir = stacked_dir / "lights"
        lights_dir.mkdir(exist_ok=True)
        for jpg in sorted(session_dir.glob("astro_frame_*.jpg")):
            dest = lights_dir / jpg.name
            if not dest.exists():
                shutil.copy2(jpg, dest)

        emit("Stacking: building Siril script...")
        script_path = stacked_dir / "stack.ssf"
        # 'convert' takes the output basename as its only positional argument;
        # it converts every supported image in the CWD whose name starts with
        # that prefix.  We cd into lights_dir to avoid picking up .dng files.
        sequence_name = "astro_frame_"
        registered_name = "r_astro_frame_"
        # Use -norm=no for robustness: addscale normalisation fails when MAD is
        # near-zero (flat test shots).  Real dark-sky frames work with either.
        script = "\n".join(
            [
                "requires 1.2.0",
                f"cd {lights_dir}",
                f"convert {sequence_name}",
                # Use shift-only registration: more robust with few stars/frames,
                # avoids over-fitting rotations that cause blur.
                f"register {sequence_name} -transf=shift",
                f"stack {registered_name} rej 3 3 -norm=no -out={stacked_dir}/stacked_starfield",
                "close",
                "",
            ]
        )
        script_path.write_text(script, encoding="utf-8")

        emit("Stacking: running Siril alignment + integration...")
        cmd = [siril, "-s", str(script_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        log_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        log_path.write_text(log_text, encoding="utf-8")

        if proc.returncode != 0:
            return StackResult(
                False,
                None,
                log_path,
                error=f"Siril failed (exit {proc.returncode}). See {log_path}",
            )

        if not output_fit.exists():
            return StackResult(False, None, log_path, error=f"Siril completed but no output found at {output_fit}")

        # Auto-export: load the stacked FITS, apply asinh stretch, save JPEG.
        emit("Stacking: exporting preview JPEG...")
        preview_jpg = stacked_dir / "stacked_starfield_preview.jpg"
        preview_script = "\n".join(
            [
                "requires 1.2.0",
                f"load {stacked_dir}/stacked_starfield",
                # Linked stretch keeps RGB ratios intact (no colour shift).
                "autostretch -linked",
                f"savejpg {stacked_dir}/stacked_starfield_preview 95",
                "close",
                "",
            ]
        )
        preview_script_path = stacked_dir / "export.ssf"
        preview_script_path.write_text(preview_script, encoding="utf-8")
        export_proc = subprocess.run([siril, "-s", str(preview_script_path)], capture_output=True, text=True)
        log_path.write_text(log_text + "\n" + (export_proc.stdout or "") + "\n" + (export_proc.stderr or ""), encoding="utf-8")

        emit("Stacking: complete.")
        return StackResult(True, output_fit, log_path, preview_path=preview_jpg if preview_jpg.exists() else None)

