from __future__ import annotations

from pathlib import Path

from usb_shared.subprocesses import run


def open_path(path: Path) -> None:
    run(["xdg-open", str(path)], check=False)
