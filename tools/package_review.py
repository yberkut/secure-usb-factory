from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
EXCLUDE_SUFFIXES = (".egg-info",)


def _ignore_release_junk(_dir: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in EXCLUDE_DIRS or name.endswith(EXCLUDE_SUFFIXES):
            ignored.add(name)
    return ignored


def _copy_review_tree(tmp_root: Path) -> Path:
    review_root = tmp_root / "secure-usb-factory-review"
    shutil.copytree(ROOT, review_root, ignore=_ignore_release_junk)
    return review_root


def _project_version(root: Path) -> str:
    text = (root / "packages/usb_shared/src/usb_shared/version.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("VERSION = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("Could not read project version")


def _set_lib_layout(config_text: str, layout: str) -> str:
    lines = []
    changed = False
    for line in config_text.splitlines():
        if line.strip().startswith("lib_layout = "):
            lines.append(f'lib_layout = "{layout}"')
            changed = True
        else:
            lines.append(line)
    if not changed:
        raise SystemExit("Could not find package.lib_layout in suf.toml")
    return "\n".join(lines) + "\n"


def _run(root: Path, args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.setdefault("SHELL", "/bin/bash")
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        args,
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=True,
    )


def _assert_layout(root: Path, layout: str) -> None:
    package = root / "dist" / "suf"
    if layout == "tree":
        if not (package / "lib" / "src").is_dir():
            raise SystemExit("tree review failed: dist/suf/lib/src is missing")
        for tool in ["stick", "vault", "wipe", "forge"]:
            if (package / "lib" / tool).exists():
                raise SystemExit(f"tree review failed: executable runtime should not exist at dist/suf/lib/{tool}")
        return
    for tool in ["stick", "vault", "wipe", "forge"]:
        if not (package / "lib" / tool).is_file():
            raise SystemExit(f"executable review failed: dist/suf/lib/{tool} is missing")
    if (package / "lib" / "src").exists():
        raise SystemExit("executable review failed: raw Python source tree should not exist at dist/suf/lib/src")


def _review_layout(root: Path, layout: str) -> None:
    print(f"Reviewing package layout: {layout}")
    config = root / "suf.toml"
    original = config.read_text(encoding="utf-8")
    config.write_text(_set_lib_layout(original, layout), encoding="utf-8")
    shutil.rmtree(root / "build", ignore_errors=True)
    shutil.rmtree(root / "dist", ignore_errors=True)

    _run(root, [sys.executable, "tools/package.py"], timeout=600)
    _run(root, [sys.executable, "tools/package_sanity.py"], timeout=120)
    _assert_layout(root, layout)

    package = root / "dist" / "suf"
    version = _project_version(root)
    stick_version = _run(root, [str(package / "bin" / "stick"), "--version"]).stdout.strip()
    if stick_version != f"stick {version}":
        raise SystemExit(f"stick --version mismatch for {layout}: {stick_version}")

    _run(root, [str(package / "bin" / "forge"), "validate"], timeout=120)
    _run(root, [str(package / "bin" / "forge"), "generate"], timeout=120)
    _run(root, [str(package / "generated-scripts" / "green-stick-mount"), "--help"], timeout=30)
    print(f"Package layout OK: {layout}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="suf-package-review-") as tmp:
        review_root = _copy_review_tree(Path(tmp))
        for layout in ("tree", "executable"):
            _review_layout(review_root, layout)
    print("Package review: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
