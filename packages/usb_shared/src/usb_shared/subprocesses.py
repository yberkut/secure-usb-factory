from __future__ import annotations

import subprocess
from typing import Sequence

from usb_shared.execution import ExecutionContext, format_command


def format_process_error(exc: subprocess.CalledProcessError) -> str:
    stderr = getattr(exc, "stderr", None)
    stdout = getattr(exc, "stdout", None)
    if stderr and str(stderr).strip():
        return str(stderr).strip()
    if stdout and str(stdout).strip():
        return str(stdout).strip()
    return f"Command failed ({exc.returncode}): {format_command(exc.cmd)}"


def run(
    cmd: Sequence[str],
    check: bool = True,
    ctx: ExecutionContext | None = None,
) -> subprocess.CompletedProcess[str]:
    if ctx is not None:
        ctx.command(cmd)
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def run_interactive(
    cmd: Sequence[str],
    check: bool = True,
    ctx: ExecutionContext | None = None,
) -> int:
    if ctx is not None:
        ctx.command(cmd)
    completed = subprocess.run(cmd, check=check)
    return completed.returncode


def run_with_input(
    cmd: Sequence[str],
    input_text: str,
    check: bool = True,
    ctx: ExecutionContext | None = None,
) -> subprocess.CompletedProcess[str]:
    if ctx is not None:
        ctx.command(cmd)
    return subprocess.run(cmd, text=True, input=input_text, capture_output=True, check=check)
