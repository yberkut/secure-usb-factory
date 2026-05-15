from __future__ import annotations

from pathlib import Path

from usb_shared.execution import ExecutionContext
from usb_shared.subprocesses import run


def is_mounted(path: Path) -> bool:
    mount_path = str(path)
    try:
        with Path("/proc/mounts").open("r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == mount_path:
                    return True
    except FileNotFoundError:
        return False
    return False


def list_mounts() -> list[tuple[str, str]]:
    mounts: list[tuple[str, str]] = []
    try:
        with Path("/proc/mounts").open("r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 2:
                    mounts.append((parts[0], parts[1]))
    except FileNotFoundError:
        return []
    return mounts


def mounted_targets_for_sources(sources: list[str]) -> list[Path]:
    source_set = set(sources)
    return [Path(target) for source, target in list_mounts() if source in source_set]


def ensure_mount_dir(path: Path, ctx: ExecutionContext | None = None) -> None:
    run(["sudo", "mkdir", "-p", str(path)], ctx=ctx)


def mount_device(source: str, target: Path, ctx: ExecutionContext | None = None) -> None:
    run(["sudo", "mount", source, str(target)], ctx=ctx)


def unmount_path(target: Path, ctx: ExecutionContext | None = None) -> None:
    run(["sudo", "umount", str(target)], ctx=ctx)


def force_unmount_path(target: Path, ctx: ExecutionContext | None = None) -> None:
    run(["sudo", "umount", "-l", str(target)], ctx=ctx)


def remove_empty_dir(path: Path, ctx: ExecutionContext | None = None) -> None:
    run(["sudo", "rmdir", str(path)], ctx=ctx)
