#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

uv run python - <<'PY'
from pathlib import Path
import sysconfig

root = Path.cwd()
purelib = Path(sysconfig.get_paths()["purelib"])
pth = purelib / "secure_usb_factory_local_paths.pth"
paths = [
    root / "src",
    root / "packages" / "usb_shared" / "src",
    root / "packages" / "usb_linux" / "src",
    root / "packages" / "usb_stick" / "src",
    root / "packages" / "usb_vault" / "src",
    root / "packages" / "usb_wipe" / "src",
    root / "packages" / "usb_forge" / "src",
]
pth.write_text("\n".join(str(p) for p in paths) + "\n")
print(f"Refreshed IDE helper paths: {pth}")
PY
