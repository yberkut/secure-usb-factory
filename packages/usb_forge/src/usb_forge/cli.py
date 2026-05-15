from __future__ import annotations

import typer

from usb_shared.cli_style import GLOBAL_PANEL, OPTIONAL_PANEL, make_app
from usb_shared.config.loader import load_config
from usb_shared.errors import ValidationError
from usb_shared.output import echo_lines, echo_themed_line, echo_version

from .loader import find_forge_config
from .packager import stage_artifact
from .planner import build_plan, inspect_plan
from .validator import validate_generation_inputs

app = make_app(name="forge", help="[bold yellow]Forge[/bold yellow] — script and artifact composition.")


def _load_and_validate_or_exit() -> tuple[object, object]:
    try:
        config_path = find_forge_config()
        config = load_config(config_path)
        validate_generation_inputs(config)
        return config_path, config
    except (FileNotFoundError, OSError, ValidationError) as exc:
        echo_lines([
            "Forge validation:",
            "Result: FAILED",
            f"Error: {exc}",
        ])
        raise typer.Exit(1)


def _validation_summary_lines(config_path: object, config: object) -> list[str]:
    plan = build_plan(config)
    return [
        "Forge validation:",
        f"Config file: {config_path}",
        "Result: OK",
        f"Scripts checked: {len(config.forge.scripts)}",
        f"Atomic scripts: {len(plan.atomic_scripts)}",
        f"Scenario scripts: {len(plan.scenario_scripts)}",
        f"Disabled scripts: {len(plan.disabled_scripts)}",
        f"Packages planned: {', '.join(plan.included_packages) or '(none)'}",
        f"Output artifact: {config.artifacts.output_dir}",
    ]


def _manual_lines(command: str) -> list[str]:
    return [
        f"Forge manual procedure: {command}",
        "1. Review the active forge config.",
        "2. Run validation before generation.",
        "$ forge validate",
        f"$ forge {command}",
        "No operational stick or vault data is modified by forge.",
    ]


@app.callback(invoke_without_command=True)
def root_callback(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit.", rich_help_panel=GLOBAL_PANEL
    ),
    manual: bool = typer.Option(
        False,
        "--manual",
        "-M",
        help="Show manual procedure examples and exit.",
        rich_help_panel=GLOBAL_PANEL,
    ),
) -> None:
    if version:
        echo_version("forge")
        raise typer.Exit()
    if manual:
        echo_lines([
            "Forge manual procedures:",
            "$ forge validate --manual",
            "$ forge inspect --manual",
            "$ forge generate --manual",
            "Use command-level --manual to print the equivalent forge operator procedure without mutation.",
        ])
        raise typer.Exit()


@app.command()
def validate(
    manual: bool = typer.Option(False, "--manual", "-M", help="Show manual procedure.", rich_help_panel=OPTIONAL_PANEL),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Show extra detail.", rich_help_panel=OPTIONAL_PANEL),
) -> None:
    if manual:
        echo_lines(_manual_lines("validate"))
        return
    config_path, config = _load_and_validate_or_exit()
    lines = _validation_summary_lines(config_path, config)
    if verbose:
        plan = build_plan(config)
        lines.append(f"Referenced targets: {', '.join(plan.referenced_targets) or '(none)'}")
    echo_lines(lines)


@app.command()
def inspect(
    manual: bool = typer.Option(False, "--manual", "-M", help="Show manual procedure.", rich_help_panel=OPTIONAL_PANEL),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Show extra detail.", rich_help_panel=OPTIONAL_PANEL),
) -> None:
    if manual:
        echo_lines(_manual_lines("inspect"))
        return
    config_path, config = _load_and_validate_or_exit()
    lines = [f"Config file: {config_path}", *inspect_plan(config).splitlines()]
    if verbose:
        lines.append(f"Config scripts checked: {len(config.forge.scripts)}")
    echo_lines(lines)


@app.command()
def generate(
    manual: bool = typer.Option(False, "--manual", "-M", help="Show manual procedure.", rich_help_panel=OPTIONAL_PANEL),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Show extra detail.", rich_help_panel=OPTIONAL_PANEL),
) -> None:
    if manual:
        echo_lines(_manual_lines("generate"))
        return
    _config_path, config = _load_and_validate_or_exit()
    output = stage_artifact(config, reporter=echo_themed_line)
    echo_themed_line("Generation result: OK")
    echo_themed_line(f"Generated scripts at: {output}")
    if verbose:
        echo_themed_line(f"Scripts configured: {len(config.forge.scripts)}")


def main() -> None:
    app(prog_name="forge")


if __name__ == "__main__":
    main()
