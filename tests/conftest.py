from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATHS = [
    ROOT,
    ROOT / "src",
    ROOT / "packages" / "usb_shared" / "src",
    ROOT / "packages" / "usb_linux" / "src",
    ROOT / "packages" / "usb_stick" / "src",
    ROOT / "packages" / "usb_vault" / "src",
    ROOT / "packages" / "usb_wipe" / "src",
    ROOT / "packages" / "usb_forge" / "src",
]
for path in reversed(PATHS):
    s = str(path)
    if s not in sys.path:
        sys.path.insert(0, s)

# Keep help wrapping deterministic across local terminals and GitHub Actions.
# Content assertions normalize ANSI instead of disabling color globally because
# generated-script tests intentionally verify colorized help.
os.environ.setdefault("COLUMNS", "120")
