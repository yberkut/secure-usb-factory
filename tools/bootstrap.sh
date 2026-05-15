#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

# Some locked-down or proxied environments have slow package mirrors.
# Let callers override these, but use a less fragile default than uv's short timeout.
: "${UV_HTTP_TIMEOUT:=120}"
: "${UV_INDEX_URL:=https://pypi.org/simple}"
export UV_HTTP_TIMEOUT UV_INDEX_URL

sync_dev() {
  uv sync --extra dev --extra lint --extra build --index-url "${UV_INDEX_URL}"
}

if ! sync_dev; then
  cat >&2 <<'MSG'

Bootstrap failed while syncing Python dependencies.

This is usually a network or package mirror timeout, not a source-tree failure.
Try one of these from the repository root:

  UV_HTTP_TIMEOUT=300 uv sync --extra dev --extra lint --extra build --index-url https://pypi.org/simple
  UV_HTTP_TIMEOUT=600 UV_HTTP_RETRIES=10 uv sync --extra dev --extra lint --extra build --index-url https://pypi.org/simple
  UV_INDEX_URL=https://pypi.org/simple ./tools/bootstrap.sh
  uv sync --extra dev --extra lint --extra build --offline   # only works if the packages are already cached

If you are using WebStorm over SSH, remember these commands run inside the remote VM.
Inspect mirror-related environment variables with:

  env | grep -E 'UV_|PIP_|HTTP|HTTPS|NO_PROXY'

Then rerun:

  ./tools/bootstrap.sh

MSG
  exit 1
fi

# Help IDEs like WebStorm resolve multi-root editable sources reliably.
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
print(f"Wrote IDE helper paths: {pth}")
PY

echo
echo "Bootstrap complete. The .venv is ready, but this script cannot activate your parent shell."
echo
echo "Use make targets directly; they run through uv run:"
echo "  make contract"
echo "  make test"
echo "  make lint"
echo
echo "For an interactive shell, run:"
echo "  source .venv/bin/activate"
echo
echo "Or call tools directly through uv:"
echo "  uv run stick --help"
echo "  uv run pytest -q"
echo "  uv run ruff check"
echo "  uv run stick --install-completion bash|zsh|fish"
echo
echo "If WebStorm still shows red imports, refresh the interpreter after bootstrap or run tools/refresh_ide_paths.sh."
