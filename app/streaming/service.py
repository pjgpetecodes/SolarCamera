from __future__ import annotations

from collections import deque
import os
import queue
import shlex
import signal
import subprocess
import threading
import time
from PIL import Image


class StreamingService:
    def __init__(self) -> None:
        self.stream_url: str = "rtmp://a.rtmp.youtube.com/live2"
        self.stream_key: str = ""
        self._process: subprocess.Popen[bytes] | None = None
        self._writer_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._frame_queue: queue.Queue[bytes] = queue.Queue(maxsize=2)
        self._stderr_lines: deque[str] = deque(maxlen=60)
        self._width = 1280
        self._height = 720
        self._frames_written = 0

    @property
    def is_streaming(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def configure(self, stream_url: str, stream_key: str) -> None:
        self.stream_url = stream_url.strip()
        self.stream_key = stream_key.strip()

    def start(self, width: int, height: int, fps: int, bitrate: str) -> None:
        if self.is_streaming:
            return
        if not self.stream_key:
            raise ValueError("Stream key is required before starting livestream.")

        self._width = int(width)
        self._height = int(height)
        destination = f"{self.stream_url}/{self.stream_key}"
        cmd = (
            "ffmpeg -hide_banner -loglevel warning "
            f"-f rawvideo -pix_fmt rgb24 -s {self._width}x{self._height} -r {int(fps)} -i - "
            "-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 "
            "-map 0:v:0 -map 1:a:0 "
            f"-c:v libx264 -preset veryfast -tune zerolatency -g {int(fps) * 2} -pix_fmt yuv420p "
            f"-b:v {shlex.quote(bitrate)} -c:a aac -b:a 128k -ar 44100 "
            "-flvflags no_duration_filesize -rtmp_live live "
            f"-f flv {shlex.quote(destination)}"
        )
        print(f"[stream] starting ffmpeg pipeline to {self.stream_url}/<stream-key-hidden>")
        self._stop_event.clear()
        self._stderr_lines.clear()
        self._frames_written = 0
        self._process = subprocess.Popen(
            ["bash", "-lc", cmd],
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=False,
            preexec_fn=os.setsid,
        )
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True, name="stream-stderr")
        self._stderr_thread.start()
        self._writer_thread = threading.Thread(target=self._write_frames, daemon=True, name="stream-writer")
        self._writer_thread.start()
        time.sleep(0.8)
        if self._process.poll() is not None:
            err = self.failure_reason()
            self.stop()
            raise ValueError(f"Livestream failed to start. {err}")

    def push_frame(self, frame: Image.Image) -> None:
        if not self.is_streaming:
            return
        resized = frame.convert("RGB").resize((self._width, self._height))
        payload = resized.tobytes()
        try:
            self._frame_queue.put_nowait(payload)
        except queue.Full:
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frame_queue.put_nowait(payload)
            except queue.Full:
                pass

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while not self._stop_event.is_set():
            line = process.stderr.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded:
                self._stderr_lines.append(decoded)
                print(f"[stream] {decoded}")

    def _write_frames(self) -> None:
        while not self._stop_event.is_set():
            try:
                payload = self._frame_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if not self.is_streaming or self._process is None or self._process.stdin is None:
                continue
            try:
                self._process.stdin.write(payload)
                self._process.stdin.flush()
                self._frames_written += 1
                if self._frames_written % 60 == 0:
                    print(f"[stream] sent {self._frames_written} frames")
            except (BrokenPipeError, OSError):
                self._stop_event.set()
                break

    def failure_reason(self) -> str:
        if not self._stderr_lines:
            return "No FFmpeg error output was captured."
        return " | ".join(list(self._stderr_lines)[-3:])

    def stop(self) -> None:
        self._stop_event.set()
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=2)
            self._writer_thread = None
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=2)
            self._stderr_thread = None

        if not self.is_streaming:
            self._process = None
            return
        assert self._process is not None
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except OSError:
                pass
        try:
            os.killpg(self._process.pid, signal.SIGTERM)
        except ProcessLookupError:
            self._process = None
            return
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self._process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._process.wait(timeout=5)
        print("[stream] stopped ffmpeg pipeline")
        self._process = None
