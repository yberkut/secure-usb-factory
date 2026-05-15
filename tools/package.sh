#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required." >&2
  exit 1
fi

: "${UV_HTTP_TIMEOUT:=120}"
: "${UV_INDEX_URL:=https://pypi.org/simple}"
export UV_HTTP_TIMEOUT UV_INDEX_URL

# Build/package commands intentionally remove stale output before they run.
rm -rf "${ROOT_DIR}/build" "${ROOT_DIR}/dist"

uv sync --extra dev --extra lint --extra build --index-url "${UV_INDEX_URL}"
uv run python tools/package.py
