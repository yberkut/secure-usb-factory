from __future__ import annotations

from pathlib import Path


def ensure_path(value: str) -> Path:
    return Path(value).expanduser()
