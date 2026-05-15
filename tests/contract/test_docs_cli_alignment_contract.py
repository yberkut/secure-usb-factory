from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tests.support.cli_output import assert_cli_contains

from forge.cli import app as forge_app
from stick.cli import app as stick_app
from vault.cli import app as vault_app
from wipe.cli import app as wipe_app

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_CONTRACT = ROOT / "docs" / "25 - public CLI contract.md"
runner = CliRunner()

ROOT_HELP_CASES = [
    ("stick", stick_app),
    ("vault", vault_app),
    ("wipe", wipe_app),
    ("forge", forge_app),
]

DOCUMENTED_COMMANDS = {
    "stick": ["create", "mount", "unmount"],
    "vault": ["create", "mount", "unmount"],
    "wipe": ["stick", "vault", "dir", "file"],
    "forge": ["validate", "inspect", "generate"],
}


def test_public_cli_contract_names_match_live_roots() -> None:
    text = PUBLIC_CONTRACT.read_text(encoding="utf-8")

    for name, app in ROOT_HELP_CASES:
        assert f"`{name}`" in text
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0, result.output
        assert_cli_contains(result.output, f"Usage: {name}")


def test_public_cli_contract_command_shapes_exist_in_help() -> None:
    apps = dict(ROOT_HELP_CASES)

    for tool, commands in DOCUMENTED_COMMANDS.items():
        text = PUBLIC_CONTRACT.read_text(encoding="utf-8")
        for command in commands:
            assert f"{tool} {command}" in text
            result = runner.invoke(apps[tool], [command, "--help"])
            assert result.exit_code == 0, result.output
            assert_cli_contains(result.output, "Usage:")


def test_new_examples_prefer_media_id_over_stick_id() -> None:
    # The compatibility alias is still intentionally documented and tested in CLI help,
    # but executable scenario examples should use the current public spelling.
    for path in sorted((ROOT / "tests" / "e2e").glob("scenario_*.py")):
        text = path.read_text(encoding="utf-8")
        assert "--stick-id" not in text, path
        if "vault" in text and "build_command(" in text and "--help" not in text:
            assert "--media-id" in text, path
