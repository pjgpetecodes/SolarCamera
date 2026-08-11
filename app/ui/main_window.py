from __future__ import annotations

import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import ImageTk

from app.astro.service import AstroService
from app.camera.service import CameraService, CameraUnavailableError
from app.config.settings import AppSettings, SettingsStore
from app.storage.usb import UsbStorageService
from app.streaming.service import StreamingService
from app.timelapse.service import TimelapseService


class MainWindow:
    def __init__(self, root: tk.Tk, settings_store: SettingsStore) -> None:
        self.root = root
        self.settings_store = settings_store
        self.settings: AppSettings = settings_store.load()
        self.streaming = StreamingService()
        self.streaming.configure(self.settings.stream_url, self.settings.stream_key)
        self.timelapse = TimelapseService()
        self.astro = AstroService()
        self.storage = UsbStorageService()
        self.camera: CameraService | None = None
        self.preview_image: ImageTk.PhotoImage | None = None
        self.selected_usb: Path | None = None
        self.last_session_dir: Path | None = None
        self._usb_mounts = []
        self.auto_exposure_enabled = False
        self._closing = False
        self.panel_visible = True
        self.capture_mode = "timelapse"
        self._status_hold_until = 0.0
        self._status_after_id: str | None = None
        self._timelapse_interval_seconds = 0
        self._timelapse_next_capture_at = 0.0
        self._astro_capture_phase = "idle"
        self._astro_current_frame = 0
        self._astro_capture_started_at = 0.0
        self._astro_gap_seconds = 0
        self._astro_next_capture_at = 0.0
        self._astro_stopping = False

        self._build_window()
        self._build_layout()
        self._init_camera()
        self.refresh_usb_mounts()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_window(self) -> None:
        self.root.title("Solar Eclipse Camera")
        self.root.configure(bg="#111")
        self.root.attributes("-fullscreen", True)
        self.root.geometry("1280x720")
        self.root.bind("<Escape>", lambda _: self.on_close())
        self.root.bind("q", lambda _: self.on_close())
        self.root.report_callback_exception = self._report_callback_exception

    def _build_layout(self) -> None:
        self.root.grid_columnconfigure(0, weight=5)
        self.root.grid_columnconfigure(1, weight=2)
        self.root.grid_rowconfigure(0, weight=1)

        preview_frame = tk.Frame(self.root, bg="black")
        preview_frame.grid(row=0, column=0, sticky="nsew")
        self.preview_label = tk.Label(preview_frame, bg="black")
        self.preview_label.pack(fill="both", expand=True)
        self.preview_label.bind("<Button-1>", self.on_preview_click)

        controls_container = tk.Frame(self.root, bg="#1b1b1b")
        controls_container.grid(row=0, column=1, sticky="nsew")
        self.controls_container = controls_container
        controls_container.grid_rowconfigure(0, weight=1)
        controls_container.grid_columnconfigure(0, weight=1)

        controls_canvas = tk.Canvas(controls_container, bg="#1b1b1b", highlightthickness=0)
        controls_canvas.grid(row=0, column=0, sticky="nsew")
        controls_scrollbar = tk.Scrollbar(controls_container, orient="vertical", command=controls_canvas.yview)
        controls_scrollbar.grid(row=0, column=1, sticky="ns")
        controls_canvas.configure(yscrollcommand=controls_scrollbar.set)

        controls = tk.Frame(controls_canvas, bg="#1b1b1b", padx=16, pady=16)
        controls_window = controls_canvas.create_window((0, 0), window=controls, anchor="nw")

        def update_scrollregion(_event=None) -> None:
            controls_canvas.configure(scrollregion=controls_canvas.bbox("all"))

        def update_canvas_width(event) -> None:
            controls_canvas.itemconfigure(controls_window, width=event.width)

        controls.bind("<Configure>", update_scrollregion)
        controls_canvas.bind("<Configure>", update_canvas_width)

        title = tk.Label(
            controls,
            text="Solar Timelapse Controller",
            fg="white",
            bg="#1b1b1b",
            font=("TkDefaultFont", 14, "bold"),
        )
        title.pack(fill="x", pady=(0, 10))

        self.status_var = tk.StringVar(value="Ready")
        status_label = tk.Label(
            controls,
            textvariable=self.status_var,
            fg="#9ad1ff",
            bg="#1b1b1b",
            wraplength=320,
            justify="left",
        )
        status_label.pack(fill="x", pady=(0, 12))

        mode_frame = tk.Frame(controls, bg="#1b1b1b")
        mode_frame.pack(fill="x", pady=(0, 12))
        self.timelapse_mode_btn = tk.Button(
            mode_frame,
            text="Timelapse Mode",
            command=lambda: self.set_capture_mode("timelapse"),
            height=2,
        )
        self.timelapse_mode_btn.pack(side="left", fill="x", expand=True)
        self.astro_mode_btn = tk.Button(
            mode_frame,
            text="Astro Mode",
            command=lambda: self.set_capture_mode("astro"),
            height=2,
        )
        self.astro_mode_btn.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.timelapse_frame = tk.Frame(controls, bg="#1b1b1b")
        self.astro_frame = tk.Frame(controls, bg="#1b1b1b")

        self._build_timelapse_controls(self.timelapse_frame)
        self._build_astro_controls(self.astro_frame)

        self.timelapse_frame.pack(fill="x")

        stream_btn_frame = tk.Frame(controls, bg="#1b1b1b")
        stream_btn_frame.pack(fill="x", pady=(14, 4))
        self.livestream_toggle_btn = tk.Button(
            stream_btn_frame,
            text="Start Livestream",
            command=self.toggle_stream,
            height=2,
        )
        self.livestream_toggle_btn.pack(fill="x")

        usb_frame = tk.Frame(controls, bg="#1b1b1b")
        usb_frame.pack(fill="x", pady=(14, 0))
        tk.Label(usb_frame, text="USB destination", fg="white", bg="#1b1b1b").pack(anchor="w")
        self.usb_combo = ttk.Combobox(usb_frame, state="readonly")
        self.usb_combo.pack(fill="x", pady=(2, 0))
        self.usb_combo.bind("<<ComboboxSelected>>", self.on_usb_selected)
        usb_btn_row = tk.Frame(usb_frame, bg="#1b1b1b")
        usb_btn_row.pack(fill="x", pady=(8, 0))
        tk.Button(usb_btn_row, text="Refresh USB", command=self.refresh_usb_mounts).pack(
            side="left", fill="x", expand=True
        )
        tk.Button(usb_btn_row, text="Quit App", command=self.on_close, bg="#8b1f1f", fg="white").pack(
            side="left", fill="x", expand=True, padx=(8, 0)
        )

        tk.Button(controls, text="Configure YouTube Stream", command=self.open_stream_config).pack(
            fill="x", pady=(14, 0)
        )

    def _set_status(self, message: str, hold_seconds: float = 0.0) -> None:
        self.status_var.set(message)
        if hold_seconds > 0:
            self._status_hold_until = time.time() + hold_seconds

    def _set_status_threadsafe(self, message: str, hold_seconds: float = 0.0) -> None:
        self.root.after(0, lambda: self._set_status(message, hold_seconds=hold_seconds))

    def _start_capture_status_updates(self) -> None:
        if self._status_after_id is not None:
            self.root.after_cancel(self._status_after_id)
            self._status_after_id = None
        self._status_after_id = self.root.after(250, self._refresh_capture_status)

    def _stop_capture_status_updates(self) -> None:
        if self._status_after_id is not None:
            self.root.after_cancel(self._status_after_id)
            self._status_after_id = None

    def _refresh_capture_status(self) -> None:
        self._status_after_id = None
        if self._closing:
            return
        if time.time() < self._status_hold_until:
            self._status_after_id = self.root.after(250, self._refresh_capture_status)
            return

        if self._astro_stopping:
            if self._astro_capture_phase == "capturing":
                elapsed = time.time() - self._astro_capture_started_at
                remaining = max(0, self.astro_exposure_value.get() - elapsed)
                self.status_var.set(
                    f"Astro: Stop requested. Finishing current exposure ({remaining:.0f}s remaining)..."
                )
            else:
                self.status_var.set("Astro: Stop requested. Finalizing shutdown...")
            self._status_after_id = self.root.after(250, self._refresh_capture_status)
            return

        if self.astro.is_running:
            if self._astro_capture_phase == "capturing":
                elapsed = time.time() - self._astro_capture_started_at
                remaining = max(0, self.astro_exposure_value.get() - elapsed)
                self.status_var.set(
                    f"Astro: Capturing frame {self._astro_current_frame} ({remaining:.0f}s remaining)"
                )
            elif self._astro_capture_phase == "waiting" and self._astro_gap_seconds > 0:
                remaining = max(0, self._astro_next_capture_at - time.time())
                self.status_var.set(
                    f"Astro: {self.astro.frame_count} frame(s) saved. Next exposure in {remaining:.0f}s"
                )
            else:
                self.status_var.set(f"Astro: Running, {self.astro.frame_count} frame(s) saved")
            self._status_after_id = self.root.after(250, self._refresh_capture_status)
            return

        if self.timelapse.is_running:
            remaining = max(0, self._timelapse_next_capture_at - time.time())
            self.status_var.set(
                f"Timelapse: {self.timelapse.frame_count} frame(s) saved. Next capture in {remaining:.0f}s"
            )
            self._status_after_id = self.root.after(500, self._refresh_capture_status)
            return

    def _on_timelapse_frame_captured(self, frame_number: int, frame_path: Path) -> None:
        def apply() -> None:
            self._timelapse_next_capture_at = time.time() + self._timelapse_interval_seconds
            self._set_status(f"Timelapse: Image {frame_number} saved ({frame_path.name})", hold_seconds=1.5)

        self.root.after(0, apply)

    def _on_astro_capture_event(self, phase: str, frame_number: int, jpg_path: Path) -> None:
        def apply() -> None:
            if phase == "capturing":
                self._astro_capture_phase = "capturing"
                self._astro_current_frame = frame_number
                self._astro_capture_started_at = time.time()
                return

            self._astro_capture_phase = "waiting" if self._astro_gap_seconds > 0 else "capturing"
            self._astro_current_frame = frame_number + 1
            self._astro_next_capture_at = time.time() + self._astro_gap_seconds
            self._set_status(f"Astro: Image {frame_number} saved ({jpg_path.name})", hold_seconds=1.5)

        self.root.after(0, apply)

    def _build_timelapse_controls(self, controls: tk.Frame) -> None:
        btn_frame = tk.Frame(controls, bg="#1b1b1b")
        btn_frame.pack(fill="x", pady=4)
        self.timelapse_toggle_btn = tk.Button(
            btn_frame,
            text="Start Timelapse",
            command=self.toggle_timelapse,
            height=2,
        )
        self.timelapse_toggle_btn.pack(fill="x")

        exp_label = tk.Label(controls, text="Exposure (microseconds)", fg="white", bg="#1b1b1b")
        exp_label.pack(anchor="w", pady=(14, 2))
        self.exposure_value = tk.IntVar(value=self.settings.default_exposure_us)
        self.exposure_display_var = tk.StringVar(value=f"{self.exposure_value.get()} us")
        exposure_slider = tk.Scale(
            controls,
            from_=100,
            to=60000,
            orient="horizontal",
            variable=self.exposure_value,
            command=self.on_exposure_change,
            bg="#1b1b1b",
            fg="white",
            highlightthickness=0,
            troughcolor="#333",
        )
        exposure_slider.pack(fill="x")
        tk.Label(controls, textvariable=self.exposure_display_var, fg="#d8d8d8", bg="#1b1b1b").pack(anchor="w")
        self.auto_exp_btn = tk.Button(controls, command=self.toggle_auto_exposure)
        self.auto_exp_btn.pack(fill="x", pady=(8, 0))
        self._update_auto_exposure_button_text()

        iso_label = tk.Label(controls, text="ISO", fg="white", bg="#1b1b1b")
        iso_label.pack(anchor="w", pady=(12, 2))
        self.iso_value = tk.IntVar(value=self.settings.default_iso)
        self.iso_display_var = tk.StringVar(value=f"ISO {self.iso_value.get()}")
        iso_slider = tk.Scale(
            controls,
            from_=100,
            to=1600,
            resolution=50,
            orient="horizontal",
            variable=self.iso_value,
            command=self.on_iso_change,
            bg="#1b1b1b",
            fg="white",
            highlightthickness=0,
            troughcolor="#333",
        )
        iso_slider.pack(fill="x")
        tk.Label(controls, textvariable=self.iso_display_var, fg="#d8d8d8", bg="#1b1b1b").pack(anchor="w")

        interval_label = tk.Label(controls, text="Timelapse interval (seconds)", fg="white", bg="#1b1b1b")
        interval_label.pack(anchor="w", pady=(14, 2))
        self.interval_value = tk.IntVar(value=self.settings.default_interval_seconds)
        interval_spin = tk.Spinbox(controls, from_=1, to=3600, textvariable=self.interval_value)
        interval_spin.pack(fill="x")

    def _build_astro_controls(self, controls: tk.Frame) -> None:
        btn_frame = tk.Frame(controls, bg="#1b1b1b")
        btn_frame.pack(fill="x", pady=4)
        self.astro_capture_btn = tk.Button(
            btn_frame,
            text="Capture Single Frame",
            command=self.capture_astro_single,
            height=2,
        )
        self.astro_capture_btn.pack(fill="x")
        self.start_astro_btn = tk.Button(
            btn_frame,
            text="Start Astro Sequence",
            command=self.toggle_astro_sequence,
            height=2,
        )
        self.start_astro_btn.pack(fill="x", pady=(8, 0))

        exp_label = tk.Label(controls, text="Exposure (seconds)", fg="white", bg="#1b1b1b")
        exp_label.pack(anchor="w", pady=(14, 2))
        self.astro_exposure_value = tk.IntVar(value=self.settings.default_astro_exposure_seconds)
        self.astro_exposure_display_var = tk.StringVar(value=f"{self.astro_exposure_value.get()} s")
        astro_exposure_slider = tk.Scale(
            controls,
            from_=1,
            to=239,
            orient="horizontal",
            variable=self.astro_exposure_value,
            command=self.on_astro_exposure_change,
            bg="#1b1b1b",
            fg="white",
            highlightthickness=0,
            troughcolor="#333",
        )
        astro_exposure_slider.pack(fill="x")
        tk.Label(controls, textvariable=self.astro_exposure_display_var, fg="#d8d8d8", bg="#1b1b1b").pack(
            anchor="w"
        )

        gain_label = tk.Label(controls, text="Gain", fg="white", bg="#1b1b1b")
        gain_label.pack(anchor="w", pady=(12, 2))
        self.astro_gain_value = tk.DoubleVar(value=self.settings.default_astro_gain)
        self.astro_gain_display_var = tk.StringVar(value=f"Gain {self.astro_gain_value.get():.1f}")
        astro_gain_slider = tk.Scale(
            controls,
            from_=1.0,
            to=16.0,
            resolution=0.5,
            orient="horizontal",
            variable=self.astro_gain_value,
            command=self.on_astro_gain_change,
            bg="#1b1b1b",
            fg="white",
            highlightthickness=0,
            troughcolor="#333",
        )
        astro_gain_slider.pack(fill="x")
        tk.Label(controls, textvariable=self.astro_gain_display_var, fg="#d8d8d8", bg="#1b1b1b").pack(anchor="w")

        gap_label = tk.Label(controls, text="Gap between frames (seconds)", fg="white", bg="#1b1b1b")
        gap_label.pack(anchor="w", pady=(14, 2))
        self.astro_gap_value = tk.IntVar(value=self.settings.default_astro_gap_seconds)
        astro_gap_spin = tk.Spinbox(controls, from_=0, to=3600, textvariable=self.astro_gap_value)
        astro_gap_spin.pack(fill="x")

    def _init_camera(self) -> None:
        try:
            self.camera = CameraService(
                width=self.settings.frame_width,
                height=self.settings.frame_height,
                framerate=self.settings.framerate,
            )
            self.camera.start_preview(self.on_preview_frame)
            self.camera.set_exposure_us(self.settings.default_exposure_us)
            self.camera.set_iso(self.settings.default_iso)
            self.status_var.set("Camera ready.")
        except CameraUnavailableError as exc:
            self.status_var.set(f"Camera unavailable: {exc}")

    def on_preview_frame(self, frame_image) -> None:
        if self.streaming.is_streaming:
            self.streaming.push_frame(frame_image)
        else:
            self.root.after(0, self._handle_stream_stopped_ui)

        def draw() -> None:
            if self._closing or not self.preview_label.winfo_exists():
                return
            try:
                width = self.preview_label.winfo_width()
                height = self.preview_label.winfo_height()
                if width <= 1 or height <= 1:
                    width, height = 900, 720
                frame = frame_image.resize((width, height))
                image = ImageTk.PhotoImage(frame)
                self.preview_image = image
                self.preview_label.configure(image=image)
            except tk.TclError:
                return

        if self._closing:
            return
        self.root.after(0, draw)

    def _handle_stream_stopped_ui(self) -> None:
        if self._closing or not self.livestream_toggle_btn.winfo_exists():
            return
        if self.livestream_toggle_btn.cget("text") == "Stop Livestream":
            self.livestream_toggle_btn.configure(text="Start Livestream")
            self._set_status(f"Livestream ended: {self.streaming.failure_reason()}")

    def on_preview_click(self, _event=None) -> None:
        self.toggle_panel()

    def toggle_panel(self) -> None:
        self.panel_visible = not self.panel_visible
        if self.panel_visible:
            self.controls_container.grid()
            self.root.grid_columnconfigure(1, weight=2)
        else:
            self.controls_container.grid_remove()
            self.root.grid_columnconfigure(1, weight=0)

    def set_capture_mode(self, mode: str) -> None:
        if mode == self.capture_mode:
            return
        if self.timelapse.is_running:
            messagebox.showerror("Timelapse Running", "Stop the timelapse before switching modes.")
            return
        if self._astro_stopping:
            messagebox.showerror("Astro Stopping", "Please wait for astro sequence shutdown to complete.")
            return
        if self.astro.is_running:
            messagebox.showerror("Astro Sequence Running", "Stop the astro sequence before switching modes.")
            return

        self.capture_mode = mode
        if mode == "astro":
            self.timelapse_frame.pack_forget()
            self.astro_frame.pack(fill="x")
            self.status_var.set("Astro Mode selected.")
        else:
            self.astro_frame.pack_forget()
            self.timelapse_frame.pack(fill="x")
            self.status_var.set("Timelapse Mode selected.")

    def _report_callback_exception(self, exc, val, tb) -> None:
        if exc is KeyboardInterrupt:
            self.on_close()
            return
        raise val.with_traceback(tb)

    def on_exposure_change(self, value: str) -> None:
        exposure = int(value)
        self.exposure_display_var.set(f"{exposure} us")
        self.settings.default_exposure_us = exposure
        self.settings_store.save(self.settings)
        self.auto_exposure_enabled = False
        self._update_auto_exposure_button_text()
        if self.camera is None:
            return
        self.camera.set_exposure_us(exposure)

    def on_iso_change(self, value: str) -> None:
        iso = int(float(value))
        self.iso_display_var.set(f"ISO {iso}")
        self.settings.default_iso = iso
        self.settings_store.save(self.settings)
        self.auto_exposure_enabled = False
        self._update_auto_exposure_button_text()
        if self.camera is None:
            return
        self.camera.set_iso(iso)

    def _update_auto_exposure_button_text(self) -> None:
        if self.auto_exposure_enabled:
            self.auto_exp_btn.configure(text="Disable Auto Exposure")
            return
        self.auto_exp_btn.configure(text="Enable Auto Exposure")

    def toggle_auto_exposure(self) -> None:
        if self.camera is None:
            return
        if not self.auto_exposure_enabled:
            self.camera.set_auto_exposure()
            self.auto_exposure_enabled = True
            self.status_var.set("Auto exposure enabled.")
            self._update_auto_exposure_button_text()
            return

        self.auto_exposure_enabled = False
        self.camera.set_exposure_us(self.exposure_value.get())
        self.camera.set_iso(self.iso_value.get())
        self._update_auto_exposure_button_text()
        self.status_var.set("Auto exposure disabled.")

    def on_astro_exposure_change(self, value: str) -> None:
        exposure = int(float(value))
        self.astro_exposure_display_var.set(f"{exposure} s")
        self.settings.default_astro_exposure_seconds = exposure
        self.settings_store.save(self.settings)

    def on_astro_gain_change(self, value: str) -> None:
        gain = float(value)
        self.astro_gain_display_var.set(f"Gain {gain:.1f}")
        self.settings.default_astro_gain = gain
        self.settings_store.save(self.settings)

    def _astro_capture_frame(self, jpg_path: Path, dng_path: Path) -> None:
        assert self.camera is not None
        self.camera.capture_long_exposure(
            jpg_path=jpg_path,
            dng_path=dng_path,
            exposure_seconds=self.astro_exposure_value.get(),
            gain=self.astro_gain_value.get(),
        )

    def capture_astro_single(self) -> None:
        if self.camera is None:
            messagebox.showerror("Camera Error", "Camera is not available.")
            return
        if self.selected_usb is None:
            messagebox.showerror("USB Required", "Select a USB destination first.")
            return
        if not self.storage.ensure_writable(self.selected_usb):
            messagebox.showerror("USB Error", "Selected USB destination is not writable.")
            return
        if self.astro.is_running:
            return

        output_root = self.storage.session_root(self.selected_usb, folder_name="solar_astro")
        exposure = self.astro_exposure_value.get()
        self._set_status(f"Astro: Capturing single frame ({exposure}s)...")
        self.root.update_idletasks()
        try:
            jpg_path = self.astro.capture_single(self._astro_capture_frame, output_root)
        except RuntimeError as exc:
            self._set_status(str(exc))
            return
        self._set_status(f"Astro: Image 1 saved ({jpg_path.name})")

    def toggle_astro_sequence(self) -> None:
        if self._astro_stopping:
            return
        if self.astro.is_running:
            self.stop_astro_sequence_async()
            return
        self.start_astro_sequence()

    def start_astro_sequence(self) -> None:
        if self._astro_stopping:
            return
        if self.camera is None:
            messagebox.showerror("Camera Error", "Camera is not available.")
            return
        if self.selected_usb is None:
            messagebox.showerror("USB Required", "Select a USB destination first.")
            return
        if not self.storage.ensure_writable(self.selected_usb):
            messagebox.showerror("USB Error", "Selected USB destination is not writable.")
            return
        if self.astro.is_running:
            return

        output_root = self.storage.session_root(self.selected_usb, folder_name="solar_astro")
        gap_seconds = int(self.astro_gap_value.get())
        self._astro_gap_seconds = gap_seconds
        self._astro_capture_phase = "capturing"
        self._astro_current_frame = 1
        self._astro_capture_started_at = time.time()
        self._astro_next_capture_at = 0.0
        self.last_session_dir = self.astro.start(
            capture_func=self._astro_capture_frame,
            output_root=output_root,
            gap_seconds=gap_seconds,
            on_capture_event=self._on_astro_capture_event,
        )
        self.settings.default_astro_gap_seconds = gap_seconds
        self.settings_store.save(self.settings)
        self._set_status(f"Astro: Sequence started ({self.last_session_dir.name})", hold_seconds=1.5)
        self.start_astro_btn.configure(text="Stop Astro Sequence")
        self.astro_capture_btn.configure(state=tk.DISABLED)
        self._start_capture_status_updates()

    def stop_astro_sequence_async(self) -> None:
        if not self.astro.is_running:
            return
        self._astro_stopping = True
        self.start_astro_btn.configure(text="Stopping Astro...", state=tk.DISABLED)
        self.astro_capture_btn.configure(state=tk.DISABLED)
        self._set_status("Astro: Stop requested. Waiting for current exposure to finish...")
        self._start_capture_status_updates()

        def worker() -> None:
            self.astro.stop()
            try:
                self.root.after(0, self._finalize_astro_stop_ui)
            except tk.TclError:
                pass

        threading.Thread(target=worker, name="astro-stop-worker", daemon=True).start()

    def _finalize_astro_stop_ui(self) -> None:
        self._astro_stopping = False
        self._stop_capture_status_updates()
        self._astro_capture_phase = "idle"
        if self._closing:
            return
        if self.start_astro_btn.winfo_exists():
            self.start_astro_btn.configure(text="Start Astro Sequence", state=tk.NORMAL)
        if self.astro_capture_btn.winfo_exists():
            self.astro_capture_btn.configure(state=tk.NORMAL)
        self._set_status(
            f"Astro sequence stopped. {self.astro.frame_count} frame(s) saved to {self.astro.session_dir}"
        )

    def refresh_usb_mounts(self) -> None:
        mounts = self.storage.list_mounts()
        labels = [f"{m.device} -> {m.mount_point}" for m in mounts]
        self.usb_combo["values"] = labels
        if labels:
            self.usb_combo.current(0)
            self.selected_usb = mounts[0].mount_point
        else:
            self.selected_usb = None
            self.status_var.set("No USB storage detected.")
        self._usb_mounts = mounts

    def on_usb_selected(self, _event) -> None:
        index = self.usb_combo.current()
        if index < 0:
            self.selected_usb = None
            return
        self.selected_usb = self._usb_mounts[index].mount_point
        self.status_var.set(f"USB selected: {self.selected_usb}")

    def start_timelapse(self) -> None:
        if self.camera is None:
            messagebox.showerror("Camera Error", "Camera is not available.")
            return
        if self.selected_usb is None:
            messagebox.showerror("USB Required", "Select a USB destination first.")
            return
        if not self.storage.ensure_writable(self.selected_usb):
            messagebox.showerror("USB Error", "Selected USB destination is not writable.")
            return
        if self.timelapse.is_running:
            return

        output_root = self.storage.session_root(self.selected_usb)
        interval = int(self.interval_value.get())
        self._timelapse_interval_seconds = interval
        self._timelapse_next_capture_at = time.time()
        self.last_session_dir = self.timelapse.start(
            capture_func=self.camera.capture_still,
            output_root=output_root,
            interval_seconds=interval,
            on_frame_captured=self._on_timelapse_frame_captured,
        )
        self.settings.default_interval_seconds = interval
        self.settings_store.save(self.settings)
        self._set_status(f"Timelapse started: {self.last_session_dir}", hold_seconds=1.5)
        self.timelapse_toggle_btn.configure(text="Stop Timelapse")
        self._start_capture_status_updates()

    def toggle_timelapse(self) -> None:
        if self.timelapse.is_running:
            self.stop_timelapse()
            return
        self.start_timelapse()

    def stop_timelapse(self) -> None:
        if not self.timelapse.is_running:
            return
        self.timelapse.stop()
        self._stop_capture_status_updates()
        self.timelapse_toggle_btn.configure(text="Start Timelapse")
        assert self.last_session_dir is not None
        try:
            output = self.timelapse.render_mp4(self.last_session_dir, fps=self.settings.framerate)
            self._set_status(f"Timelapse saved: {output}")
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self._set_status(f"Render failed: {exc}")

    def start_stream(self) -> None:
        if self.camera is None:
            messagebox.showerror("Livestream Error", "Camera is not available.")
            return

        try:
            self.streaming.start(
                width=self.settings.frame_width,
                height=self.settings.frame_height,
                fps=self.settings.framerate,
                bitrate=self.settings.bitrate,
            )
        except ValueError as exc:
            self.status_var.set(str(exc))
            messagebox.showerror("Livestream Config", str(exc))
            return
        self.status_var.set("Livestream started. YouTube preview may take 10-20 seconds to appear.")
        self.livestream_toggle_btn.configure(text="Stop Livestream")

    def toggle_stream(self) -> None:
        if self.streaming.is_streaming:
            self.stop_stream()
            return
        self.start_stream()

    def stop_stream(self) -> None:
        self.streaming.stop()
        self.status_var.set("Livestream stopped.")
        self.livestream_toggle_btn.configure(text="Start Livestream")

    def open_stream_config(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("YouTube Stream Configuration")
        dialog.geometry("480x220")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="RTMP Server URL").pack(anchor="w", padx=12, pady=(12, 2))
        url_var = tk.StringVar(value=self.settings.stream_url)
        url_entry = tk.Entry(dialog, textvariable=url_var)
        url_entry.pack(fill="x", padx=12)

        tk.Label(dialog, text="Stream Key").pack(anchor="w", padx=12, pady=(10, 2))
        key_var = tk.StringVar(value=self.settings.stream_key)
        key_entry = tk.Entry(dialog, textvariable=key_var, show="*")
        key_entry.pack(fill="x", padx=12)

        def save() -> None:
            self.settings.stream_url = url_var.get().strip()
            self.settings.stream_key = key_var.get().strip()
            self.settings_store.save(self.settings)
            self.streaming.configure(self.settings.stream_url, self.settings.stream_key)
            self.status_var.set("YouTube stream settings saved.")
            dialog.destroy()

        tk.Button(dialog, text="Save", command=save).pack(pady=16)

    def on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._stop_capture_status_updates()
        if self.timelapse.is_running:
            self.timelapse.stop()
        if self.astro.is_running:
            self.astro.stop()
        if self.streaming.is_streaming:
            self.streaming.stop()
        if self.camera is not None:
            self.camera.close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
