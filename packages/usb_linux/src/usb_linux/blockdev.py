from __future__ import annotations

from pathlib import Path
import shlex
import stat
import time
from dataclasses import dataclass

from usb_shared.execution import ExecutionContext
from usb_shared.subprocesses import run


@dataclass(frozen=True)
class DeviceIdentity:
    requested_path: str
    resolved_path: str
    size: str = ""
    model: str = ""
    vendor: str = ""
    transport: str = ""
    serial: str = ""


def device_exists(path: str) -> bool:
    return Path(path).exists()


def is_block_device(path: str) -> bool:
    try:
        return stat.S_ISBLK(Path(path).resolve().stat().st_mode)
    except OSError:
        return False


def resolved_device_path(device_path: str) -> str:
    return str(Path(device_path).resolve())


def _parse_lsblk_pairs(line: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in shlex.split(line):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        result[key] = value
    return result


def device_identity(device_path: str, ctx: ExecutionContext | None = None) -> DeviceIdentity:
    resolved = resolved_device_path(device_path)
    completed = run(
        ["lsblk", "-dn", "-P", "-o", "PATH,SIZE,MODEL,VENDOR,TRAN,SERIAL", resolved], ctx=ctx
    )
    line = completed.stdout.strip()
    if not line:
        return DeviceIdentity(requested_path=device_path, resolved_path=resolved)
    parsed = _parse_lsblk_pairs(line)
    return DeviceIdentity(
        requested_path=device_path,
        resolved_path=parsed.get("PATH", resolved),
        size=parsed.get("SIZE", ""),
        model=parsed.get("MODEL", ""),
        vendor=parsed.get("VENDOR", ""),
        transport=parsed.get("TRAN", ""),
        serial=parsed.get("SERIAL", ""),
    )


def list_block_nodes(device_path: str, ctx: ExecutionContext | None = None) -> list[str]:
    completed = run(["lsblk", "-lnpo", "NAME", device_path], ctx=ctx)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def list_mapper_names_for_device(
    device_path: str, ctx: ExecutionContext | None = None
) -> list[str]:
    completed = run(["lsblk", "-lnpo", "NAME,TYPE", device_path], ctx=ctx)
    names: list[str] = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[-1] != "crypt":
            continue
        node = Path(parts[0]).name
        if node:
            names.append(node)
    return names


def create_gpt(device_path: str, ctx: ExecutionContext | None = None) -> None:
    run(["sudo", "parted", "-s", device_path, "mklabel", "gpt"], ctx=ctx)


def create_primary_partition(device_path: str, ctx: ExecutionContext | None = None) -> None:
    run(["sudo", "parted", "-s", device_path, "mkpart", "primary", "1MiB", "100%"], ctx=ctx)


def reread_partition_table(device_path: str, ctx: ExecutionContext | None = None) -> None:
    run(["sudo", "partprobe", device_path], ctx=ctx)
    run(["udevadm", "settle"], ctx=ctx)


def first_partition_path(
    device_path: str, timeout_seconds: float = 10.0, ctx: ExecutionContext | None = None
) -> str:
    resolved = Path(device_path).resolve()
    base = str(resolved)

    candidates = [f"{device_path}-part1"]
    if (
        base.startswith("/dev/nvme")
        or base.startswith("/dev/mmcblk")
        or base.startswith("/dev/loop")
    ):
        candidates.append(f"{base}p1")
    else:
        candidates.append(f"{base}1")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        run(["udevadm", "settle"], ctx=ctx)
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        time.sleep(0.25)

    raise RuntimeError(
        "Could not resolve first partition path after partition creation. Tried: "
        + ", ".join(candidates)
    )


def wipe_signatures(device_path: str, ctx: ExecutionContext | None = None) -> None:
    run(["sudo", "wipefs", "-a", device_path], ctx=ctx)


def zero_device_head(
    device_path: str, count_mb: int = 16, ctx: ExecutionContext | None = None
) -> None:
    run(
        [
            "sudo",
            "dd",
            "if=/dev/zero",
            f"of={device_path}",
            "bs=1M",
            f"count={count_mb}",
            "conv=fsync",
            "status=none",
        ],
        ctx=ctx,
    )


def zero_device_tail(
    device_path: str, count_mb: int = 16, ctx: ExecutionContext | None = None
) -> None:
    size_bytes = int(run(["sudo", "blockdev", "--getsize64", device_path], ctx=ctx).stdout.strip())
    seek_mb = max(0, size_bytes // (1024 * 1024) - count_mb)
    run(
        [
            "sudo",
            "dd",
            "if=/dev/zero",
            f"of={device_path}",
            "bs=1M",
            f"seek={seek_mb}",
            f"count={count_mb}",
            "conv=fsync",
            "status=none",
        ],
        ctx=ctx,
    )


def overwrite_device_full(device_path: str, ctx: ExecutionContext | None = None) -> None:
    run(
        [
            "sudo",
            "dd",
            "if=/dev/zero",
            f"of={device_path}",
            "bs=16M",
            "conv=fsync",
            "status=progress",
        ],
        ctx=ctx,
    )
