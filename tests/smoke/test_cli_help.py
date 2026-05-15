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


def test_public_cli_help() -> None:
    for app in [stick_app, vault_app, wipe_app, forge_app]:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0


def test_public_cli_short_help_alias() -> None:
    for app in [stick_app, vault_app, wipe_app, forge_app]:
        result = runner.invoke(app, ["-h"])
        assert result.exit_code == 0


def test_typer_root_help_mentions_commands_and_examples() -> None:
    for app, command in [
        (stick_app, "create"),
        (vault_app, "mount"),
        (wipe_app, "stick"),
        (forge_app, "validate"),
    ]:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert command in result.stdout


def test_root_help_describes_version_option() -> None:
    for command_name, app in PUBLIC_APPS:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Show version and exit" in result.stdout, command_name
