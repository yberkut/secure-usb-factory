from __future__ import annotations

import os
import shutil
from pathlib import Path

from usb_shared.execution import ExecutionContext
from usb_shared.subprocesses import run


def path_exists(path: Path) -> bool:
    return path.exists()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def is_writable_path(path: Path) -> bool:
    target = path if path.exists() else path.parent
    return target.exists() and os.access(target, os.W_OK | os.X_OK)


def create_sparse_file(path: Path, size: str, ctx: ExecutionContext | None = None) -> None:
    ensure_dir(path.parent)
    run(["truncate", "-s", size, str(path)], ctx=ctx)


def remove_tree(path: Path) -> None:
    shutil.rmtree(path)


def chown_path(path: Path, uid: int | None = None, gid: int | None = None, recursive: bool = False, ctx: ExecutionContext | None = None) -> None:
    uid = os.getuid() if uid is None else uid
    gid = os.getgid() if gid is None else gid
    target = f"{uid}:{gid}"
    cmd = ["sudo", "chown"]
    if recursive:
        cmd.append("-R")
    cmd.extend([target, str(path)])
    run(cmd, ctx=ctx)
