from __future__ import annotations

from typing import Optional

import typer

from usb_shared.cli_style import make_app
from usb_shared.output import echo_lines
from usb_vault.service import VaultService

app = make_app(name="vault", help="[bold cyan]Vault[/bold cyan] — encrypted vault images on mounted media.")


def _root_manual() -> list[str]:
    return [
        "Vault manual procedures:",
        "$ vault create --media-id <id> --mount <mounted-media> --vault <name> --size <size> --purpose <text> --manual",
        "$ vault create --media-id <id> --mount <mounted-media> --vault <name> --size <size> --purpose <text> --dry-run",
        "$ vault create --media-id <id> --mount <mounted-media> --vault <name> --size <size> --purpose <text> --status",
        "$ vault mount --media-id <id> --mount <mounted-media> --vault <name> --manual",
        "$ vault mount --media-id <id> --mount <mounted-media> --vault <name> --keepass --manual",
        "$ vault mount --media-id <id> --mount <mounted-media> --vault <name> --status",
        "$ vault unmount --media-id <id> --vault <name> --manual",
        "$ vault unmount --media-id <id> --vault <name> --dry-run",
        "$ vault unmount --media-id <id> --vault <name> --status",
        "Use command-level --manual to print the equivalent operator commands without mutation.",
    ]


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(None, "--version", help="Show version and exit."),
    manual: bool = typer.Option(
        False, "--manual", "-M", help="Show manual procedure examples and exit."
    ),
) -> None:
    if version:
        from usb_shared.output import echo_version

        echo_version("vault")
        raise typer.Exit()
    if manual:
        echo_lines(_root_manual())
        raise typer.Exit()
    if ctx.invoked_subcommand is None and not version:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command("create")
def create(
    media_id: str = typer.Option(..., "--media-id", "--stick-id", "-s"),
    mount: str = typer.Option(..., "--mount", "-m"),
    vault: str = typer.Option(..., "--vault", "-v"),
    size: str = typer.Option(..., "--size"),
    purpose: str = typer.Option(..., "--purpose"),
    status: bool = typer.Option(False, "--status", "-S"),
    dry_run: bool = typer.Option(False, "--dry-run", "-D"),
    manual: bool = typer.Option(False, "--manual", "-M"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
) -> None:
    svc = VaultService()
    if manual:
        result = svc.create_manual(media_id, mount, vault, size, purpose)
    elif status:
        result = svc.status(media_id, mount, vault)
    else:
        result = svc.create(media_id, mount, vault, size, purpose, dry_run=dry_run, verbose=verbose)
    echo_lines(result.lines)
    raise typer.Exit(result.exit_code)


@app.command("mount")
def mount_cmd(
    media_id: str = typer.Option(..., "--media-id", "--stick-id", "-s"),
    mount: str = typer.Option(..., "--mount", "-m"),
    vault: str = typer.Option(..., "--vault", "-v"),
    keepass: bool = typer.Option(False, "--keepass", "-k"),
    status: bool = typer.Option(False, "--status", "-S"),
    dry_run: bool = typer.Option(False, "--dry-run", "-D"),
    manual: bool = typer.Option(False, "--manual", "-M"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
) -> None:
    svc = VaultService()
    if manual:
        result = svc.mount_manual(media_id, mount, vault, keepass=keepass)
    elif status:
        result = svc.status(media_id, mount, vault, keepass=keepass)
    else:
        result = svc.mount(media_id, mount, vault, keepass=keepass, dry_run=dry_run, verbose=verbose)
    echo_lines(result.lines)
    raise typer.Exit(result.exit_code)


@app.command("unmount")
def unmount_cmd(
    media_id: str = typer.Option(..., "--media-id", "--stick-id", "-s"),
    vault: str = typer.Option(..., "--vault", "-v"),
    status: bool = typer.Option(False, "--status", "-S"),
    dry_run: bool = typer.Option(False, "--dry-run", "-D"),
    manual: bool = typer.Option(False, "--manual", "-M"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
) -> None:
    svc = VaultService()
    if manual:
        result = svc.unmount_manual(media_id, vault)
    elif status:
        result = svc.unmount_status(media_id, vault)
    else:
        result = svc.unmount(media_id, vault, dry_run=dry_run, verbose=verbose)
    echo_lines(result.lines)
    raise typer.Exit(result.exit_code)


def main() -> None:
    app(prog_name="vault")


if __name__ == "__main__":
    main()
