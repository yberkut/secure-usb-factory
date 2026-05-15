from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "dist" / "suf"
DEFAULT_TIMEOUT = int(os.environ.get("SUF_INTEGRATION_TIMEOUT", "30"))
COMPLETION_TIMEOUT = int(os.environ.get("SUF_COMPLETION_TIMEOUT", str(DEFAULT_TIMEOUT)))


def package_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    
    if not env.get("SHELL"):
        env["SHELL"] = "/bin/bash"
    for key in list(env):
        if key.endswith("_COMPLETE"):
            env.pop(key, None)
    env.setdefault("SUF_INTEGRATION", "1")
    # Integration tests use the fast inspectable tree package.
    # Executable packaging is covered by tools/package_review.py with the build extra.
    env["SUF_PACKAGE_LIB_LAYOUT"] = "tree"
    env["SUF_PACKAGE_TOOLS"] = "stick,vault,wipe,forge"
    return env


def run(args: list[str], *, cwd: Path = ROOT, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=package_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        timeout=DEFAULT_TIMEOUT if timeout is None else timeout,
        check=True,
    )


def run_completion(args: list[str], *, cwd: Path = ROOT, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    timeout = COMPLETION_TIMEOUT if timeout is None else timeout
    quoted = " ".join(shlex.quote(str(arg)) for arg in args)
    return subprocess.run(
        ["bash", "-c", f"timeout {timeout}s {quoted} | head -200"],
        cwd=cwd,
        env=package_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        timeout=timeout + 5,
        check=True,
    )
