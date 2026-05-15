from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CliTheme:
    heading_style: str = "bold white"
    label_style: str = "bold cyan"
    value_style: str = "none"
    info_style: str = "bright_white"
    command_style: str = "dim bright_black"
    success_style: str = "bold green"
    warning_style: str = "yellow"
    error_style: str = "bold red"
    prompt_style: str = "bold magenta"
    note_style: str = "dim white"
    plan_heading_style: str = "dim white"
    plan_prefix_style: str = "dim white"
    plan_label_style: str = "dim white"
    token_styles: dict[str, str] = field(
        default_factory=lambda: {
            "OK": "bold green",
            "READY": "bold green",
            "YES": "bold green",
            "FOUND": "bold green",
            "OPEN": "bold green",
            "MOUNTED": "bold green",
            "CLOSED": "yellow",
            "NOT MOUNTED": "yellow",
            "NOT FOUND": "yellow",
            "NO": "yellow",
            "NONE": "yellow",
            "UNKNOWN": "bold red",
            "MISSING": "bold red",
            "FAIL": "bold red",
            "FAILED": "bold red",
            "ERROR": "bold red",
            "CANCELLED": "yellow",
        }
    )
    success_prefixes: tuple[str, ...] = (
        "Mounted ",
        "Unmounted ",
        "Wiped ",
        "Created ",
        "Opened ",
        "Generated ",
        "Config is valid",
        "Ready:",
    )
    warning_prefixes: tuple[str, ...] = (
        "Could not ",
        "Remove it manually",
        "Dry-run only",
        "Cancelled",
        "Back up ",
        "Close the matching",
        "Type YES to continue",
        "Type the exact",
        "Interactive step:",
        "Press Enter when ready",
        "Stick was already ",
        "Vault was already ",
    )
    error_prefixes: tuple[str, ...] = (
        "Failed ",
        "Missing ",
        "Configured ",
        "Device confirmation did not match",
        "Resolved device confirmation did not match",
        "Stick must already be mounted",
        "Target directory not found",
        "Vault image not found",
        "Unknown ",
    )


CLI_THEME = CliTheme()
