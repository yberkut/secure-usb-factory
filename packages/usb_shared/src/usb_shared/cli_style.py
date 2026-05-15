from __future__ import annotations

import typer

CLI_WIDTH = 76
REQUIRED_PANEL = "Required options"
OPTIONAL_PANEL = "Optional options"
GLOBAL_PANEL = "Global options"


def make_app(*, name: str, help: str, add_completion: bool = True) -> typer.Typer:
    return typer.Typer(
        name=name,
        help=help,
        no_args_is_help=True,
        add_completion=add_completion,
        rich_markup_mode="rich",
        context_settings={
            "terminal_width": CLI_WIDTH,
            "max_content_width": CLI_WIDTH,
            "help_option_names": ["-h", "--help"],
        },
    )
