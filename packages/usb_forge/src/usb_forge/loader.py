from __future__ import annotations

import os
import sys
from pathlib import Path

from usb_shared.config.loader import load_config
from usb_shared.config.schema import SufConfig


def _candidate_config_paths() -> list[Path]:
    candidates: list[Path] = []

    explicit = os.environ.get("SUF_FORGE_CONFIG")
    if explicit:
        candidates.append(Path(explicit))

    cwd = Path.cwd()
    candidates.extend([
        cwd / "config" / "forge.toml",
        cwd / "forge.toml",
        cwd / "suf.toml",
    ])

    executable = Path(sys.executable).resolve()
    candidates.extend([
        executable.parent.parent / "config" / "forge.toml",
        executable.parent / "config" / "forge.toml",
    ])

    return candidates


def find_forge_config() -> Path:
    for candidate in _candidate_config_paths():
        if candidate.exists():
            return candidate
    checked = "\n".join(f"- {path}" for path in _candidate_config_paths())
    raise FileNotFoundError(f"Could not find forge config. Checked:\n{checked}")


def load_root_config() -> SufConfig:
    return load_config(find_forge_config())
