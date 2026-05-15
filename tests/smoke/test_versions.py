from typer.testing import CliRunner

from forge.cli import app as forge_app
from stick.cli import app as stick_app
from vault.cli import app as vault_app
from wipe.cli import app as wipe_app

runner = CliRunner()


def test_versions() -> None:
    expectations = [
        (stick_app, "stick 1.0.0"),
        (vault_app, "vault 1.0.0"),
        (wipe_app, "wipe 1.0.0"),
        (forge_app, "forge 1.0.0"),
    ]
    for app, text in expectations:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert text in result.stdout
