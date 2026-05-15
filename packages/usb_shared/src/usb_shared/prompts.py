from __future__ import annotations

import typer


def confirm(message: str) -> bool:
    return typer.confirm(message)


def prompt_text(message: str) -> str:
    return typer.prompt(message)


def pause_for_enter(message: str) -> None:
    typer.echo(message)
    input()
