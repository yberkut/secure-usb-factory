from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import typer

from usb_shared.cli_style import GLOBAL_PANEL, OPTIONAL_PANEL, make_app
from usb_shared.output import echo_lines

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / "tests" / "e2e" / "e2e.env"
DEFAULT_PACKAGE_BIN = ROOT / "dist" / "suf" / "bin"

app = make_app(name="e2e-runner", help="[bold cyan]E2E runner[/bold cyan] — packaged tool scenario runner.")


@dataclass(frozen=True)
class ScenarioSpec:
    script: str
    tools: tuple[str, ...]
    required_env: tuple[str, ...] = ()
    destructive: bool = False
    needs_external_mount: bool = False


SCENARIOS: dict[str, ScenarioSpec] = {
    "e2e-smoke": ScenarioSpec(
        "scenario_smoke.py",
        ("stick", "wipe"),
        ("SUF_E2E_DEVICE_PATH", "SUF_E2E_STICK_PASSPHRASE"),
        destructive=True,
    ),
    "e2e-stick": ScenarioSpec(
        "scenario_fresh_stick.py",
        ("stick", "wipe"),
        ("SUF_E2E_DEVICE_PATH", "SUF_E2E_STICK_PASSPHRASE"),
        destructive=True,
    ),
    "e2e-fresh-stick": ScenarioSpec(
        "scenario_fresh_stick.py",
        ("stick", "wipe"),
        ("SUF_E2E_DEVICE_PATH", "SUF_E2E_STICK_PASSPHRASE"),
        destructive=True,
    ),
    "e2e-vault": ScenarioSpec(
        "scenario_vault_lifecycle.py",
        ("stick", "vault", "wipe"),
        ("SUF_E2E_DEVICE_PATH", "SUF_E2E_STICK_PASSPHRASE", "SUF_E2E_VAULT_PASSPHRASE"),
        destructive=True,
    ),
    "e2e-vault-lifecycle": ScenarioSpec(
        "scenario_vault_lifecycle.py",
        ("stick", "vault", "wipe"),
        ("SUF_E2E_DEVICE_PATH", "SUF_E2E_STICK_PASSPHRASE", "SUF_E2E_VAULT_PASSPHRASE"),
        destructive=True,
    ),
    "e2e-vault-full-tiny": ScenarioSpec(
        "scenario_vault_full_tiny.py",
        ("stick", "vault", "wipe"),
        ("SUF_E2E_DEVICE_PATH", "SUF_E2E_STICK_PASSPHRASE", "SUF_E2E_VAULT_PASSPHRASE"),
        destructive=True,
    ),
    "e2e-mounted-media": ScenarioSpec(
        "scenario_vault_on_mounted_media.py",
        ("vault", "wipe"),
        ("SUF_E2E_VAULT_PASSPHRASE",),
        destructive=True,
        needs_external_mount=True,
    ),
    "e2e-vault-on-mounted-media": ScenarioSpec(
        "scenario_vault_on_mounted_media.py",
        ("vault", "wipe"),
        ("SUF_E2E_VAULT_PASSPHRASE",),
        destructive=True,
        needs_external_mount=True,
    ),
    "e2e-full": ScenarioSpec(
        "scenario_full_e2e.py",
        ("stick", "vault", "wipe"),
        ("SUF_E2E_DEVICE_PATH", "SUF_E2E_STICK_PASSPHRASE", "SUF_E2E_VAULT_PASSPHRASE"),
        destructive=True,
    ),
}

GROUPS: dict[str, tuple[str, ...]] = {
    "e2e-all": (
        "e2e-smoke",
        "e2e-stick",
        "e2e-vault",
        "e2e-vault-full-tiny",
        "e2e-mounted-media",
    )
}

PLACEHOLDER_MARKERS = {"", "REPLACE_ME", "/dev/disk/by-id/REPLACE_ME"}


def package_bin() -> Path:
    return Path(os.environ.get("SUF_E2E_TOOL_DIR", str(DEFAULT_PACKAGE_BIN))).expanduser()


def packaged_tool(name: str) -> Path:
    return package_bin() / name


def _root_manual() -> list[str]:
    return [
        "E2E runner procedures:",
        "$ make package",
        "$ make e2e-config",
        "$ make e2e-smoke",
        "$ make e2e-stick",
        "$ make e2e-vault",
        "$ make e2e-mounted-media",
        "$ make e2e-full",
        "$ make e2e-all",
        "E2E executes packaged tools from dist/suf/bin only.",
        "If tests/e2e/e2e.env is missing, run make e2e-config first.",
        "If dist/suf/bin is missing, run make package first.",
        "Configure tests/e2e/e2e.env before running; exported SUF_E2E_* values may override it.",
    ]


def _manual_lines(name: str) -> list[str]:
    spec = SCENARIOS[name]
    lines = [
        f"E2E manual procedure: {name}",
        "1. Build or refresh the package.",
        "   $ make package",
        "2. Create a local E2E config from the template.",
        "   $ make e2e-config",
        "3. Edit tests/e2e/e2e.env with disposable target values.",
        f"4. Run: make {name}",
        "",
        "Packaged tools used:",
        *(f"  dist/suf/bin/{tool}" for tool in spec.tools),
        "",
        "Common local config values:",
        "  SUF_E2E_DEVICE_PATH=/dev/disk/by-id/...",
        "  SUF_E2E_STICK_PASSPHRASE=...",
        "  SUF_E2E_VAULT_PASSPHRASE=...",
        "  SUF_E2E_STICK_ID=green",
        "  SUF_E2E_MEDIA_MOUNT=/media/green-stick",
        "  SUF_E2E_VAULT=test1",
        "  SUF_E2E_VAULT_SIZE=64M",
    ]
    if spec.needs_external_mount:
        lines.extend(
            [
                "",
                "Mounted-media scenario values:",
                "  SUF_E2E_EXTERNAL_MOUNT=/media/veracrypt1",
                "This scenario does not create, unmount, or wipe the outer media.",
            ]
        )
    lines.extend(
        [
            "",
            "The runner loads tests/e2e/e2e.env before executing, then applies exported overrides.",
            "Use disposable media for destructive scenarios.",
        ]
    )
    return lines


@app.callback(invoke_without_command=True)
def root_callback(
    manual: bool = typer.Option(
        False,
        "--manual",
        "-M",
        help="Show manual procedure examples and exit.",
        rich_help_panel=GLOBAL_PANEL,
    ),
) -> None:
    if manual:
        echo_lines(_root_manual())
        raise typer.Exit()
    return None


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "=" not in stripped:
        raise typer.BadParameter(f"Invalid env line: {line.rstrip()}")
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        raise typer.BadParameter(f"Invalid env line: {line.rstrip()}")
    return key, value


def _require_env_file(path: Path) -> None:
    if not path.exists():
        echo_lines(
            [
                f"E2E config not found: {path}",
                "Run `make e2e-config` first, then edit tests/e2e/e2e.env with disposable target values.",
            ]
        )
        raise typer.Exit(1)


def _load_env_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    loaded: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        os.environ.setdefault(key, value)
        loaded.append(key)
    return loaded


def _configuration_help(missing: list[str] | None = None) -> list[str]:
    lines = ["E2E scenario is not configured."]
    if missing:
        lines.extend(["", "Missing values:", *(f"  {name}" for name in missing)])
    lines.extend(
        [
            "",
            "Create a local config file:",
            "  make e2e-config",
            "",
            "Then edit:",
            "  tests/e2e/e2e.env",
            "",
            "Required values include:",
            "  SUF_E2E_DEVICE_PATH=/dev/disk/by-id/...",
            "  SUF_E2E_STICK_PASSPHRASE=...",
            "  SUF_E2E_VAULT_PASSPHRASE=...      # vault scenarios only",
            "",
            "Optional runtime controls:",
            "  SUF_E2E_TIMEOUT=300",
            "  SUF_E2E_HEARTBEAT=15",
            "  SUF_E2E_TOOL_DIR=dist/suf/bin",
            "",
            "Or export SUF_E2E_* variables in the current shell.",
            "Only use disposable media. These scenarios are destructive.",
        ]
    )
    return lines


def _is_placeholder(value: str | None) -> bool:
    return value is None or value in PLACEHOLDER_MARKERS or "REPLACE_ME" in value


def _missing_required_env(spec: ScenarioSpec) -> list[str]:
    return [key for key in spec.required_env if _is_placeholder(os.environ.get(key))]


def _require_package_bin() -> None:
    bin_dir = package_bin()
    if not bin_dir.is_dir():
        echo_lines([f"Package not found: {bin_dir}", "Run `make package` first."])
        raise typer.Exit(1)


def _missing_packaged_tools(spec: ScenarioSpec) -> list[str]:
    missing: list[str] = []
    for tool in spec.tools:
        path = packaged_tool(tool)
        if not path.is_file() or not os.access(path, os.X_OK):
            missing.append(tool)
    return missing


def _skip_missing_tools(name: str, missing: list[str]) -> None:
    paths = ", ".join(str(packaged_tool(tool)) for tool in missing)
    echo_lines([f"SKIPPED {name}", f"Reason: packaged tool missing: {paths}"])


def _external_mount_skip_reason() -> str | None:
    raw = os.environ.get("SUF_E2E_EXTERNAL_MOUNT")
    if _is_placeholder(raw):
        return "SUF_E2E_EXTERNAL_MOUNT is not set"
    path = Path(raw or "")
    if not path.exists():
        return f"{path} does not exist"
    if not path.is_dir():
        return f"{path} is not a directory"
    if not os.access(path, os.W_OK):
        return f"{path} is not writable"
    try:
        if not path.is_mount():
            return f"{path} is not a mounted directory"
    except OSError as exc:
        return f"cannot inspect mountpoint {path}: {exc}"
    return None


def _scenario_summary(name: str, *, env_file: Path, loaded: list[str], spec: ScenarioSpec) -> list[str]:
    stick_id = os.environ.get("SUF_E2E_STICK_ID", "green")
    vault = os.environ.get("SUF_E2E_VAULT", "test1")
    vault_size = os.environ.get("SUF_E2E_VAULT_SIZE", "64M")
    timeout = os.environ.get("SUF_E2E_TIMEOUT", "300")
    heartbeat = os.environ.get("SUF_E2E_HEARTBEAT", "15")
    env_status = f"{env_file} ({len(loaded)} values loaded)" if env_file.exists() else f"{env_file} (not found)"
    lines = [
        f"E2E scenario: {name}",
        f"Env file: {env_status}",
        f"Packaged tools: {package_bin()}",
        f"Step timeout: {timeout}s",
        f"Heartbeat: {heartbeat}s",
        f"Tools: {', '.join(spec.tools)}",
    ]
    if "stick" in spec.tools:
        lines.extend(
            [
                f"Stick ID: {stick_id}",
                f"Device path: {os.environ.get('SUF_E2E_DEVICE_PATH', '<missing>')}",
                f"Media mount: {os.environ.get('SUF_E2E_MEDIA_MOUNT', f'/media/{stick_id}-stick')}",
            ]
        )
    if "vault" in spec.tools:
        lines.append(f"Vault: {vault}")
        lines.append(f"Vault size: {vault_size}")
    if spec.needs_external_mount:
        lines.append(f"External mount: {os.environ.get('SUF_E2E_EXTERNAL_MOUNT', '<missing>')}")
    lines.extend(["", "Output streams live below. Press Ctrl+C to abort."])
    if spec.destructive:
        lines.append("This scenario is destructive. Use disposable media only.")
    return lines


def _run_scenario(name: str, spec: ScenarioSpec, *, env_file: Path) -> int:
    script = ROOT / "tests" / "e2e" / spec.script
    if not script.exists():
        raise typer.BadParameter(f"Scenario file not found: {script}")
    _require_env_file(env_file)
    loaded = _load_env_file(env_file)
    _require_package_bin()
    missing_tools = _missing_packaged_tools(spec)
    if missing_tools:
        _skip_missing_tools(name, missing_tools)
        return 0
    missing_env = _missing_required_env(spec)
    if missing_env:
        echo_lines(_configuration_help(missing_env))
        return 1
    if spec.needs_external_mount:
        reason = _external_mount_skip_reason()
        if reason:
            echo_lines([f"SKIPPED {name}", f"Reason: {reason}"])
            return 0

    echo_lines(_scenario_summary(name, env_file=env_file, loaded=loaded, spec=spec))
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("SUF_E2E_TOOL_DIR", str(package_bin()))
    try:
        result = subprocess.run([sys.executable, "-u", str(script)], cwd=ROOT, text=True, env=env)
    except KeyboardInterrupt:
        typer.echo("E2E scenario interrupted by operator.", err=True)
        return 130
    return result.returncode


def _run_named_scenario(name: str, *, manual: bool, verbose: bool, env_file: Path) -> None:
    if name in GROUPS:
        if manual:
            echo_lines([f"E2E group: {name}", *(f"  {item}" for item in GROUPS[name])])
            return
        final_code = 0
        for child_name in GROUPS[name]:
            code = _run_scenario(child_name, SCENARIOS[child_name], env_file=env_file)
            if code != 0:
                final_code = code
                break
        raise typer.Exit(final_code)
    if manual:
        echo_lines(_manual_lines(name))
        return
    if verbose:
        typer.echo(f"Running {name} scenario.")
    raise typer.Exit(_run_scenario(name, SCENARIOS[name], env_file=env_file))


def _scenario_command(name: str):
    def command(
        manual: bool = typer.Option(False, "--manual", "-M", rich_help_panel=OPTIONAL_PANEL),
        verbose: bool = typer.Option(False, "--verbose", "-V", rich_help_panel=OPTIONAL_PANEL),
        env_file: Path = typer.Option(
            DEFAULT_ENV_FILE,
            "--env-file",
            help="Local E2E env file to load before running.",
            rich_help_panel=OPTIONAL_PANEL,
        ),
    ) -> None:
        _run_named_scenario(name, manual=manual, verbose=verbose, env_file=env_file)

    command.__name__ = name.replace("-", "_")
    return command


for _name in [*SCENARIOS, *GROUPS]:
    app.command(_name)(_scenario_command(_name))


def main() -> None:
    app(prog_name="e2e-runner")


if __name__ == "__main__":
    main()
