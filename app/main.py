from __future__ import annotations

import tkinter as tk
from pathlib import Path

from app.config.settings import SettingsStore
from app.ui.main_window import MainWindow


def main() -> None:
    settings_path = Path.home() / ".config" / "solarcamera" / "settings.json"
    root = tk.Tk()
    window = MainWindow(root=root, settings_store=SettingsStore(settings_path))
    try:
        root.mainloop()
    except KeyboardInterrupt:
        window.on_close()


if __name__ == "__main__":
    main()
