from __future__ import annotations

import typer

from usb_shared.cli_style import GLOBAL_PANEL, OPTIONAL_PANEL, REQUIRED_PANEL, make_app
from usb_shared.output import echo_lines
from usb_shared.version import VERSION
from .service import StickService

app = make_app(name="stick", help="[bold cyan]Stick Factory[/bold cyan] — outer stick lifecycle only.")
service = StickService()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"stick {VERSION}")
        raise typer.Exit()


def _root_manual() -> list[str]:
    return [
        "Stick manual procedures:",
        "$ stick create --id <id> --path <device> --manual",
        "$ stick create --id <id> --path <device> --dry-run",
        "$ stick create --id <id> --path <device> --status",
        "$ stick mount --id <id> --path <device> --manual",
        "$ stick mount --id <id> --path <device> --dry-run",
        "$ stick mount --id <id> --path <device> --status",
        "$ stick unmount --id <id> --manual",
        "$ stick unmount --id <id> --dry-run",
        "$ stick unmount --id <id> --status",
        "Use command-level --manual to print the equivalent operator commands without mutation.",
    ]


@app.callback(invoke_without_command=True)
def root_callback(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
        rich_help_panel=GLOBAL_PANEL,
    ),
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


@app.command("create")
def create(
    id: str = typer.Option(..., "--id", help="Logical stick ID.", rich_help_panel=REQUIRED_PANEL),
    path: str = typer.Option(
        ..., "--path", "-p", help="Physical stick path.", rich_help_panel=REQUIRED_PANEL
    ),
    status: bool = typer.Option(
        False, "--status", "-S", help="Show readiness only.", rich_help_panel=OPTIONAL_PANEL
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-D",
        help="Show real actions without mutating.",
        rich_help_panel=OPTIONAL_PANEL,
    ),
    manual: bool = typer.Option(
        False, "--manual", "-M", help="Show manual bash procedure.", rich_help_panel=OPTIONAL_PANEL
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Show extra execution detail.",
        rich_help_panel=OPTIONAL_PANEL,
    ),
) -> None:
    if manual:
        result = service.create_manual(id, path)
    elif status:
        result = service.create_status(id, path)
    else:
        result = service.create(id, path, dry_run=dry_run, verbose=verbose)
    echo_lines(result.lines)
    raise typer.Exit(result.exit_code if not result.ok else 0)


@app.command("mount")
def mount(
    id: str = typer.Option(..., "--id", help="Logical stick ID.", rich_help_panel=REQUIRED_PANEL),
    path: str = typer.Option(
        ..., "--path", "-p", help="Physical stick path.", rich_help_panel=REQUIRED_PANEL
    ),
    status: bool = typer.Option(
        False, "--status", "-S", help="Show readiness only.", rich_help_panel=OPTIONAL_PANEL
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-D",
        help="Show real actions without mutating.",
        rich_help_panel=OPTIONAL_PANEL,
    ),
    manual: bool = typer.Option(
        False, "--manual", "-M", help="Show manual bash procedure.", rich_help_panel=OPTIONAL_PANEL
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Show extra execution detail.",
        rich_help_panel=OPTIONAL_PANEL,
    ),
) -> None:
    if manual:
        result = service.mount_manual(id, path)
    elif status:
        result = service.mount_status(id, path)
    else:
        result = service.mount(id, path, dry_run=dry_run, verbose=verbose)
    echo_lines(result.lines)
    raise typer.Exit(result.exit_code if not result.ok else 0)


@app.command("unmount")
def unmount(
    id: str = typer.Option(..., "--id", help="Logical stick ID.", rich_help_panel=REQUIRED_PANEL),
    status: bool = typer.Option(
        False, "--status", "-S", help="Show readiness only.", rich_help_panel=OPTIONAL_PANEL
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-D",
        help="Show real actions without mutating.",
        rich_help_panel=OPTIONAL_PANEL,
    ),
    manual: bool = typer.Option(
        False, "--manual", "-M", help="Show manual bash procedure.", rich_help_panel=OPTIONAL_PANEL
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Show extra execution detail.",
        rich_help_panel=OPTIONAL_PANEL,
    ),
) -> None:
    if manual:
        result = service.unmount_manual(id)
    elif status:
        result = service.unmount_status(id)
    else:
        result = service.unmount(id, dry_run=dry_run, verbose=verbose)
    echo_lines(result.lines)
    raise typer.Exit(result.exit_code if not result.ok else 0)


def main() -> None:
    app(prog_name="stick")


if __name__ == "__main__":
    main()
