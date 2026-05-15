from __future__ import annotations

import typer

from usb_shared.cli_style import GLOBAL_PANEL, OPTIONAL_PANEL, REQUIRED_PANEL, make_app
from usb_shared.output import echo_lines
from usb_shared.version import VERSION
from .service import WipeService

app = make_app(name="wipe", help="[bold cyan]Wipe[/bold cyan] — destructive operations only.")
service = WipeService()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"wipe {VERSION}")
        raise typer.Exit()


def _root_manual() -> list[str]:
    return [
        "Wipe manual procedures:",
        "$ wipe stick --path <device> --fast --manual",
        "$ wipe stick --path <device> --full --manual",
        "$ wipe stick --path <device> --status",
        "$ wipe vault --media-id <id> --mount <mounted-media> --vault <name> --manual",
        "$ wipe vault --media-id <id> --mount <mounted-media> --vault <name> --fast --manual",
        "$ wipe vault --media-id <id> --mount <mounted-media> --vault <name> --full --manual",
        "$ wipe vault --media-id <id> --mount <mounted-media> --vault <name> --status",
        "$ wipe dir --path <directory> --manual",
        "$ wipe dir --path <directory> --dry-run",
        "$ wipe dir --path <directory> --status",
        "$ wipe file --path <file> --manual",
        "$ wipe file --path <file> --dry-run",
        "$ wipe file --path <file> --status",
        "Note: wipe stick requires exactly one of --fast/--full except with --status.",
        "Note: wipe dir and wipe file are best-effort only and have no --fast/--full modes.",
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


@app.command("stick")
def wipe_stick(
    path: str = typer.Option(..., "--path", "-p", rich_help_panel=REQUIRED_PANEL),
    fast: bool = typer.Option(False, "--fast", "-f", rich_help_panel=OPTIONAL_PANEL),
    full: bool = typer.Option(False, "--full", "-F", rich_help_panel=OPTIONAL_PANEL),
    panic: bool = typer.Option(False, "--panic", "-P", rich_help_panel=OPTIONAL_PANEL),
    status: bool = typer.Option(False, "--status", "-S", rich_help_panel=OPTIONAL_PANEL),
    dry_run: bool = typer.Option(False, "--dry-run", "-D", rich_help_panel=OPTIONAL_PANEL),
    manual: bool = typer.Option(False, "--manual", "-M", rich_help_panel=OPTIONAL_PANEL),
    verbose: bool = typer.Option(False, "--verbose", "-V", rich_help_panel=OPTIONAL_PANEL),
) -> None:
    if not status and fast == full:
        raise typer.BadParameter("Choose exactly one of --fast or --full, or use --status without a wipe mode.")
    result = service.stick(
        path,
        fast=fast,
        full=full,
        panic=panic,
        status=status,
        manual=manual,
        dry_run=dry_run,
        verbose=verbose,
        logger=typer.echo if verbose else None,
    )
    echo_lines(result.lines)
    raise typer.Exit(result.exit_code if not result.ok else 0)


@app.command("vault")
def wipe_vault(
    media_id: str = typer.Option(..., "--media-id", "--stick-id", "-s", rich_help_panel=REQUIRED_PANEL),
    mount: str = typer.Option(..., "--mount", "-m", rich_help_panel=REQUIRED_PANEL),
    vault: str = typer.Option(..., "--vault", "-v", rich_help_panel=REQUIRED_PANEL),
    fast: bool = typer.Option(False, "--fast", "-f", rich_help_panel=OPTIONAL_PANEL),
    full: bool = typer.Option(False, "--full", "-F", rich_help_panel=OPTIONAL_PANEL),
    panic: bool = typer.Option(False, "--panic", "-P", rich_help_panel=OPTIONAL_PANEL),
    status: bool = typer.Option(False, "--status", "-S", rich_help_panel=OPTIONAL_PANEL),
    dry_run: bool = typer.Option(False, "--dry-run", "-D", rich_help_panel=OPTIONAL_PANEL),
    manual: bool = typer.Option(False, "--manual", "-M", rich_help_panel=OPTIONAL_PANEL),
    verbose: bool = typer.Option(False, "--verbose", "-V", rich_help_panel=OPTIONAL_PANEL),
) -> None:
    result = service.vault(
        media_id,
        mount,
        vault,
        fast=fast,
        full=full,
        panic=panic,
        status=status,
        manual=manual,
        dry_run=dry_run,
        verbose=verbose,
        logger=typer.echo if verbose else None,
    )
    echo_lines(result.lines)
    raise typer.Exit(result.exit_code if not result.ok else 0)


@app.command("dir")
def wipe_dir(
    path: str = typer.Option(..., "--path", "-p", rich_help_panel=REQUIRED_PANEL),
    status: bool = typer.Option(False, "--status", "-S", rich_help_panel=OPTIONAL_PANEL),
    dry_run: bool = typer.Option(False, "--dry-run", "-D", rich_help_panel=OPTIONAL_PANEL),
    manual: bool = typer.Option(False, "--manual", "-M", rich_help_panel=OPTIONAL_PANEL),
    verbose: bool = typer.Option(False, "--verbose", "-V", rich_help_panel=OPTIONAL_PANEL),
) -> None:
    result = service.dir(path, status=status, manual=manual, dry_run=dry_run, verbose=verbose)
    echo_lines(result.lines)
    raise typer.Exit(result.exit_code if not result.ok else 0)


@app.command("file")
def wipe_file(
    path: str = typer.Option(..., "--path", "-p", rich_help_panel=REQUIRED_PANEL),
    status: bool = typer.Option(False, "--status", "-S", rich_help_panel=OPTIONAL_PANEL),
    dry_run: bool = typer.Option(False, "--dry-run", "-D", rich_help_panel=OPTIONAL_PANEL),
    manual: bool = typer.Option(False, "--manual", "-M", rich_help_panel=OPTIONAL_PANEL),
    verbose: bool = typer.Option(False, "--verbose", "-V", rich_help_panel=OPTIONAL_PANEL),
) -> None:
    result = service.file(path, status=status, manual=manual, dry_run=dry_run, verbose=verbose)
    echo_lines(result.lines)
    raise typer.Exit(result.exit_code if not result.ok else 0)


def main() -> None:
    app(prog_name="wipe")


if __name__ == "__main__":
    main()
