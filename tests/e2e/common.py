from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Iterable, Sequence

import pexpect
from rich.console import Console
from rich.panel import Panel


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKAGE_BIN = ROOT / "dist" / "suf" / "bin"
console = Console()
_CACHED_SUDO_PASSWORD: str | None = None
_PLACEHOLDER_MARKERS = {"", "REPLACE_ME", "/dev/disk/by-id/REPLACE_ME"}

E2E_DEFAULT_VAULT_SIZE = "64M"
E2E_FULL_WIPE_MAX_BYTES = 8 * 1024 * 1024
E2E_FAST_WIPE_MIN_BYTES = E2E_FULL_WIPE_MAX_BYTES
_SIZE_UNITS = {
    "": 1,
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024**2,
    "MB": 1024**2,
    "G": 1024**3,
    "GB": 1024**3,
    "T": 1024**4,
    "TB": 1024**4,
}


def parse_size_bytes(value: str) -> int:
    text = value.strip().upper()
    if not text:
        raise ValueError("size must not be empty")
    number = ""
    unit = ""
    for char in text:
        if char.isdigit():
            if unit:
                raise ValueError(f"invalid size: {value}")
            number += char
        elif not char.isspace():
            unit += char
    if not number or unit not in _SIZE_UNITS:
        raise ValueError(f"invalid size: {value}")
    return int(number) * _SIZE_UNITS[unit]


def package_bin() -> Path:
    return Path(os.environ.get("SUF_E2E_TOOL_DIR", str(DEFAULT_PACKAGE_BIN))).expanduser()


def packaged_tool(name: str) -> Path:
    return package_bin() / name


def is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def e2e_vault_wipe_args(
    cfg: "ScenarioConfig", vault: str, vault_size: str, *, mount: str | None = None
) -> list[str]:
    size_bytes = parse_size_bytes(vault_size)
    args = [
        "wipe",
        "vault",
        "--media-id",
        cfg.stick_id,
        "--mount",
        mount or cfg.media_mount,
        "--vault",
        vault,
    ]
    if size_bytes <= E2E_FULL_WIPE_MAX_BYTES:
        args.append("--full")
    else:
        if size_bytes < E2E_FAST_WIPE_MIN_BYTES:
            raise ValueError(
                f"vault size {vault_size} is smaller than e2e fast-wipe span "
                f"{E2E_FAST_WIPE_MIN_BYTES} bytes"
            )
        args.append("--fast")
    args.append("-V")
    return args


def env_value(name: str, default: str | None) -> str | None:
    return os.environ.get(name, default)


def is_placeholder(value: str | None) -> bool:
    return value is None or value in _PLACEHOLDER_MARKERS or "REPLACE_ME" in value


def require_operator_ready(cfg: "ScenarioConfig", fields: Sequence[str]) -> None:
    missing = [field for field in fields if is_placeholder(getattr(cfg, field))]
    if not missing:
        return
    details = ", ".join(missing)
    raise SystemExit(
        "E2E scenario is not configured: "
        f"{details}. Edit tests/e2e scenario values or set SUF_E2E_* environment variables "
        "before running."
    )


def require_mounted_media(path: str) -> None:
    mount = Path(path)
    if is_placeholder(path):
        raise SystemExit(
            "SKIPPED e2e-mounted-media\n"
            "Reason: SUF_E2E_EXTERNAL_MOUNT is not set."
        )
    if not mount.exists():
        raise SystemExit(
            f"SKIPPED e2e-mounted-media\nReason: {mount} does not exist."
        )
    if not mount.is_dir():
        raise SystemExit(
            f"SKIPPED e2e-mounted-media\nReason: {mount} is not a directory."
        )
    if not os.access(mount, os.W_OK):
        raise SystemExit(
            f"SKIPPED e2e-mounted-media\nReason: {mount} is not writable."
        )
    if not _is_mountpoint(mount):
        raise SystemExit(
            f"SKIPPED e2e-mounted-media\nReason: {mount} is not a mounted directory."
        )


def _is_mountpoint(path: Path) -> bool:
    try:
        return path.is_mount()
    except OSError:
        return False


@dataclass(frozen=True)
class ScenarioConfig:
    stick_id: str
    device_path: str
    timeout: int = 300
    heartbeat: int = 15
    media_mount: str = ""
    passphrase: str | None = None
    vault: str | None = None
    vault_size: str | None = None
    vault_purpose: str | None = None
    vault_passphrase: str | None = None
    external_mount: str | None = None

    @property
    def runner(self) -> str:
        return str(package_bin())


def base_config() -> ScenarioConfig:
    stick_id = env_value("SUF_E2E_STICK_ID", "green") or "green"
    return ScenarioConfig(
        stick_id=stick_id,
        device_path=env_value("SUF_E2E_DEVICE_PATH", "/dev/disk/by-id/REPLACE_ME") or "",
        timeout=int(env_value("SUF_E2E_TIMEOUT", "300") or "300"),
        heartbeat=int(env_value("SUF_E2E_HEARTBEAT", "15") or "15"),
        media_mount=env_value("SUF_E2E_MEDIA_MOUNT", f"/media/{stick_id}-stick")
        or f"/media/{stick_id}-stick",
        passphrase=env_value("SUF_E2E_STICK_PASSPHRASE", "REPLACE_ME"),
        vault=env_value("SUF_E2E_VAULT", "test1"),
        vault_size=env_value("SUF_E2E_VAULT_SIZE", E2E_DEFAULT_VAULT_SIZE),
        vault_purpose=env_value("SUF_E2E_VAULT_PURPOSE", "test vault"),
        vault_passphrase=env_value("SUF_E2E_VAULT_PASSPHRASE", "REPLACE_ME"),
        external_mount=env_value("SUF_E2E_EXTERNAL_MOUNT", "REPLACE_ME"),
    )


def require_value(value: str | None, label: str) -> str:
    if not value:
        raise SystemExit(f"Missing required scenario value: {label}")
    return value


def build_command(_cfg: ScenarioConfig, tool: str, *args: str) -> list[str]:
    return [str(packaged_tool(tool)), *args]


def step(n: int, title: str) -> None:
    console.print()
    console.print(Panel.fit(f"[bold cyan]Step {n}[/bold cyan]\n{title}", border_style="cyan"))


def spawn_command(command: Sequence[str], timeout: int) -> pexpect.spawn:
    display = " ".join(command)
    console.print(f"[bold]$[/bold] {display}")
    child = pexpect.spawn(command[0], list(command[1:]), encoding="utf-8", timeout=timeout)
    child.logfile_read = sys.stdout
    return child


def prompt_sudo_password() -> str:
    global _CACHED_SUDO_PASSWORD
    if _CACHED_SUDO_PASSWORD is None:
        console.print()
        _CACHED_SUDO_PASSWORD = getpass("Enter sudo password: ")
    return _CACHED_SUDO_PASSWORD


def _terminate_child(child: pexpect.spawn) -> None:
    if not child.isalive():
        child.close()
        return
    child.sendintr()
    try:
        child.expect(pexpect.EOF, timeout=5)
    except (pexpect.TIMEOUT, pexpect.ExceptionPexpect):
        child.close(force=True)
    else:
        child.close()


def interactive_run(
    command: Sequence[str],
    *,
    timeout: int,
    heartbeat: int = 15,
    answers: Iterable[tuple[str, str]] | None = None,
    passphrases: list[str] | None = None,
) -> None:
    child = spawn_command(command, max(1, min(timeout, heartbeat)))
    remaining = list(passphrases or [])
    patterns = [pexpect.EOF, pexpect.TIMEOUT]
    actions: list[tuple[str, str]] = list(answers or [])
    sudo_prompt = r"\[sudo\] password for .*:"
    passphrase_prompts = [
        r"Enter new LUKS passphrase:",
        r"Repeat new LUKS passphrase:",
        r"Enter LUKS passphrase:",
    ]
    started = time.monotonic()
    deadline = started + timeout
    next_notice = started + heartbeat
    while True:
        loop_patterns = patterns + [pat for pat, _ in actions] + [sudo_prompt]
        if remaining:
            loop_patterns += passphrase_prompts
        wait = max(1, min(heartbeat, int(deadline - time.monotonic()) or 1))
        child.timeout = wait
        idx = child.expect(loop_patterns)
        now = time.monotonic()
        if idx == 0:
            child.close()
            if child.exitstatus not in (0, None) or child.signalstatus not in (0, None):
                raise SystemExit(f"Command failed with exit status {child.exitstatus}")
            return
        if idx == 1:
            elapsed = int(now - started)
            if now >= deadline:
                _terminate_child(child)
                raise SystemExit(
                    f"Command timed out after {timeout}s: {' '.join(command)}\n"
                    "Last operation did not finish. Check for a hidden sudo/passphrase prompt, "
                    "a busy mount, or a blocked storage command."
                )
            if now >= next_notice:
                console.print(
                    f"[yellow]Still running[/yellow] ({elapsed}s elapsed, "
                    f"timeout {timeout}s): {' '.join(command)}",
                )
                console.file.flush()
                next_notice = now + heartbeat
            continue
        extra_index = idx - len(patterns)
        if extra_index < len(actions):
            _, response = actions[extra_index]
            console.print("[dim]Matched confirmation prompt; sending configured response.[/dim]")
            console.file.flush()
            child.sendline(response)
            continue
        password_prompt_index = len(actions)
        if extra_index == password_prompt_index:
            console.print("[dim]Matched sudo prompt; sending cached sudo password.[/dim]")
            console.file.flush()
            child.sendline(prompt_sudo_password())
            continue
        if not remaining:
            _terminate_child(child)
            raise SystemExit("Unexpected passphrase prompt without configured passphrase")
        console.print("[dim]Matched LUKS passphrase prompt; sending configured passphrase.[/dim]")
        console.file.flush()
        child.sendline(remaining.pop(0))


def confirm_device_answers(device_path: str) -> list[tuple[str, str]]:
    return [(r"Type the exact path to continue: .*", device_path)]


def yes_answer() -> list[tuple[str, str]]:
    return [(r"Proceed with .*\? \[y/N\]:", "y"), (r"Type YES to continue.*:", "YES")]
