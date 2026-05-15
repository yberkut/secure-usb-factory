from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from forge.cli import app as forge_app
from stick.cli import app as stick_app
from vault.cli import app as vault_app
from wipe.cli import app as wipe_app

runner = CliRunner()

PUBLIC_APPS = [
    ("stick", stick_app),
    ("vault", vault_app),
    ("wipe", wipe_app),
    ("forge", forge_app),
]

_RETIRED_FAMILY_BYTES = [
    [109, 97, 110, 97, 103, 101, 114],
    [98, 117, 105, 108, 100, 101, 114],
    [101, 114, 97, 115, 101, 114],
]
RETIRED_COMMAND_FAMILY_REFERENCES = [
    prefix + "".join(chr(value) for value in values)
    for values in _RETIRED_FAMILY_BYTES
    for prefix in ("suf ", "suf_")
]

TEXT_FILE_SUFFIXES = {
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}

ROOT = Path(__file__).resolve().parents[2]


def test_current_public_cli_help_contract() -> None:
    for command_name, app in PUBLIC_APPS:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert f"Usage: {command_name}" in result.stdout


def test_current_public_cli_short_help_alias_contract() -> None:
    for command_name, app in PUBLIC_APPS:
        result = runner.invoke(app, ["-h"])
        assert result.exit_code == 0
        assert f"Usage: {command_name}" in result.stdout


def test_current_public_cli_version_contract() -> None:
    for command_name, app in PUBLIC_APPS:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert f"{command_name} 1.0.0" in result.stdout


def test_repository_has_no_retired_public_command_family_references() -> None:
    offenders: list[str] = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(
            part in {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "build", "dist"}
            for part in path.parts
        ):
            continue
        if path.suffix not in TEXT_FILE_SUFFIXES and path.name not in {"Makefile"}:
            continue

        text = path.read_text(encoding="utf-8")
        for retired_reference in RETIRED_COMMAND_FAMILY_REFERENCES:
            if retired_reference in text:
                offenders.append(f"{path.relative_to(ROOT)}: {retired_reference}")

    assert offenders == []
