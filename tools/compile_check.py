from __future__ import annotations

import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK_ROOTS = [
    ROOT / "src",
    ROOT / "packages",
    ROOT / "tests",
    ROOT / "tools",
]


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    ignored_parts = {"__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "build", "dist"}
    for root in CHECK_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if ignored_parts.intersection(path.parts):
                continue
            files.append(path)
    return sorted(files)


def main() -> int:
    files = iter_python_files()
    for path in files:
        py_compile.compile(str(path), doraise=True)
    print(f"Compiled Python files: {len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
