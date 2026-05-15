from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHONPATH = os.pathsep.join(
    str(ROOT / part)
    for part in [
        "src",
        "packages/usb_shared/src",
        "packages/usb_linux/src",
        "packages/usb_stick/src",
        "packages/usb_vault/src",
        "packages/usb_wipe/src",
        "packages/usb_forge/src",
    ]
)


def run_module(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = PYTHONPATH
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if not env.get("SHELL"):
        env["SHELL"] = "/bin/bash"
    for key in list(env):
        if key.endswith("_COMPLETE"):
            env.pop(key, None)
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        timeout=15,
        check=False,
    )


def test_module_entrypoint_version_is_fast() -> None:
    result = run_module("stick.cli", "--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "stick 1.0.0"


def test_module_entrypoint_help_is_fast_and_useful() -> None:
    result = run_module("stick.cli", "--help")
    assert result.returncode == 0, result.stderr
    assert "Usage: stick" in result.stdout
    assert "Commands" in result.stdout
    

def test_module_entrypoint_help_exposes_typer_completion_options() -> None:
    result = run_module("stick.cli", "--help")
    assert result.returncode == 0, result.stderr
    assert "--show-completion" in result.stdout
    assert "--install-completion" in result.stdout


def test_module_entrypoint_help_renders_rich_markup() -> None:
    result = run_module("forge.cli", "--help")
    assert result.returncode == 0, result.stderr
    assert "Forge" in result.stdout
    assert "[bold yellow]" not in result.stdout
    assert "[/bold yellow]" not in result.stdout
