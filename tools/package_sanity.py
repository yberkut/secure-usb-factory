from __future__ import annotations

import importlib.util
import json
import os
import re
import tomllib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dist" / "suf"
DEFAULT_PACKAGE_TOOLS = ["stick", "vault", "wipe", "forge"]
VERSION_FILE = ROOT / "packages/usb_shared/src/usb_shared/version.py"
CONFIG_PATH = ROOT / "suf.toml"

ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
WHITESPACE_RE = re.compile(r"\s+")


def normalized_cli_output(text: str) -> str:
    """Return CLI output with ANSI styling removed and whitespace made stable."""
    return WHITESPACE_RE.sub(" ", ANSI_RE.sub("", text)).strip()


def project_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("VERSION = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"Could not read project version from: {VERSION_FILE}")


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _source_package_config() -> tuple[list[str], str, bool]:
    with CONFIG_PATH.open("rb") as fh:
        raw = tomllib.load(fh)
    package = raw.get("package", {})
    artifacts = raw.get("artifacts", {})
    return (
        list(package.get("tools", DEFAULT_PACKAGE_TOOLS)),
        str(package.get("lib_layout", "tree")),
        bool(artifacts.get("include_manifest", True)),
    )


def main() -> int:
    version = project_version()
    if not PACKAGE.exists():
        return fail(f"Package output not found: {PACKAGE}")
    if (ROOT / "build").exists():
        return fail("Package build left build/ behind")

    expected_tools, expected_layout, include_manifest = _source_package_config()
    manifest_path = PACKAGE / "manifest.json"
    if include_manifest:
        if not manifest_path.exists():
            return fail(f"Package manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tools = list(manifest.get("tools", DEFAULT_PACKAGE_TOOLS))
        if manifest.get("version") != version:
            return fail(f"Package manifest version mismatch: {manifest.get('version')}")
        layout = manifest.get("layout")
    else:
        if manifest_path.exists():
            return fail(f"Package manifest should not exist when artifacts.include_manifest is false: {manifest_path}")
        tools = expected_tools
        layout = expected_layout
    command_names = tools

    if tools != expected_tools:
        return fail(f"Package tools mismatch: {tools}")
    if layout not in {"tree", "executable"}:
        return fail(f"Package layout mismatch: {layout}")
    if layout == "tree":
        if not (PACKAGE / "lib" / "src").is_dir():
            return fail("Tree package is missing raw Python libraries under lib/src")
    else:
        for tool in expected_tools:
            if not (PACKAGE / "lib" / tool).is_file():
                return fail(f"Executable package is missing runtime: lib/{tool}")
        if (PACKAGE / "lib" / "src").exists():
            return fail("Executable package should not include raw Python source tree under lib/src")

    for tool in command_names:
        binary = PACKAGE / "bin" / tool
        if not binary.exists():
            return fail(f"Packaged tool not found: {binary}")
        docs = PACKAGE / "docs" / f"{tool}.md"
        if not docs.exists():
            return fail(f"Packaged runtime docs not found: {docs}")

    if "forge" in tools and not (PACKAGE / "config" / "forge.toml").exists():
        return fail("Packaged forge config not found: config/forge.toml")

    if importlib.util.find_spec("typer") is None:
        print("Package sanity: OK; skipped packaged CLI smoke because typer is not importable")
        return 0

    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

    if not env.get("SHELL"):
        env["SHELL"] = "/bin/bash"

    for tool in command_names:
        result = subprocess.run(
            [str(PACKAGE / "bin" / tool), "--version"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return fail(f"Packaged {tool} --version failed:\n" + result.stderr)
        if result.stdout.strip() != f"{tool} {version}":
            return fail(f"Packaged {tool} --version mismatch: {result.stdout.strip()}")

    help_tool = tools[0] if tools else "suf"
    result = subprocess.run(
        [str(PACKAGE / "bin" / help_tool), "--help"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return fail(f"Packaged {help_tool} --help failed:\n" + result.stderr)
    normalized_help = normalized_cli_output(result.stdout)
    if f"Usage: {help_tool}" not in normalized_help:
        return fail(
            f"Packaged {help_tool} --help did not show expected usage\n"
            f"Expected: Usage: {help_tool}\n"
            f"Output: {normalized_help}"
        )

    print("Package sanity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
