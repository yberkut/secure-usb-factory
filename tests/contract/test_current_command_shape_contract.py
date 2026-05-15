from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from forge.cli import app as forge_app
from stick.cli import app as stick_app
from vault.cli import app as vault_app
from wipe.cli import app as wipe_app

runner = CliRunner()

COMMAND_HELP_CASES = [
    (stick_app, ["create"], ["--id", "--path", "--dry-run", "--manual", "--status"]),
    (stick_app, ["mount"], ["--id", "--path", "--dry-run", "--manual", "--status"]),
    (stick_app, ["unmount"], ["--id", "--dry-run", "--manual", "--status"]),
    (vault_app, ["create"], ["--media-id", "--stick-id", "--mount", "--vault", "--size", "--purpose"]),
    (vault_app, ["mount"], ["--media-id", "--stick-id", "--mount", "--vault", "--keepass"]),
    (vault_app, ["unmount"], ["--media-id", "--stick-id", "--vault", "--dry-run", "--manual"]),
    (wipe_app, ["stick"], ["--path", "--fast", "--full", "--dry-run", "--manual", "--status"]),
    (wipe_app, ["vault"], ["--media-id", "--stick-id", "--mount", "--vault", "--fast", "--full"]),
    (wipe_app, ["dir"], ["--path", "--dry-run", "--manual", "--status"]),
    (wipe_app, ["file"], ["--path", "--dry-run", "--manual", "--status"]),
    (forge_app, ["validate"], ["--manual", "--verbose"]),
    (forge_app, ["inspect"], ["--manual", "--verbose"]),
    (forge_app, ["generate"], ["--manual", "--verbose"]),
]


def test_current_command_help_shapes() -> None:
    for app, command, expected_fragments in COMMAND_HELP_CASES:
        result = runner.invoke(app, [*command, "--help"])
        assert result.exit_code == 0, result.output
        assert "Usage:" in result.output
        for fragment in expected_fragments:
            assert fragment in result.output


def test_dry_run_and_manual_paths_are_non_interactive(tmp_path: Path) -> None:
    vault_mount = tmp_path / "media"
    vault_mount.mkdir()
    dir_target = tmp_path / "dir-target"
    dir_target.mkdir()
    file_target = tmp_path / "file-target.txt"
    file_target.write_text("keep me", encoding="utf-8")

    cases = [
        (stick_app, ["create", "--id", "blue", "--path", "/dev/not-a-real-device", "--dry-run"], "Dry-run only"),
        (stick_app, ["mount", "--id", "blue", "--path", "/dev/not-a-real-device", "--dry-run"], "Dry-run only"),
        (stick_app, ["unmount", "--id", "blue", "--dry-run"], "Dry-run only"),
        (
            vault_app,
            [
                "create",
                "--media-id",
                "blue",
                "--mount",
                str(vault_mount),
                "--vault",
                "personal",
                "--size",
                "8M",
                "--purpose",
                "test vault",
                "--dry-run",
            ],
            "Dry-run only",
        ),
        (
            vault_app,
            ["mount", "--media-id", "blue", "--mount", str(vault_mount), "--vault", "personal", "--dry-run"],
            "Dry-run only",
        ),
        (vault_app, ["unmount", "--media-id", "blue", "--vault", "personal", "--dry-run"], "Dry-run only"),
        (wipe_app, ["stick", "--path", "/dev/not-a-real-device", "--fast", "--dry-run"], "Dry-run only"),
        (wipe_app, ["stick", "--path", "/dev/not-a-real-device", "--full", "--dry-run"], "Dry-run only"),
        (
            wipe_app,
            ["vault", "--media-id", "blue", "--mount", str(vault_mount), "--vault", "personal", "--dry-run"],
            "Dry-run only",
        ),
        (wipe_app, ["dir", "--path", str(dir_target), "--dry-run"], "Dry-run only"),
        (wipe_app, ["file", "--path", str(file_target), "--dry-run"], "Dry-run only"),
        (forge_app, ["validate", "--manual"], "No operational stick or vault data is modified"),
        (forge_app, ["inspect", "--manual"], "No operational stick or vault data is modified"),
        (forge_app, ["generate", "--manual"], "No operational stick or vault data is modified"),
    ]

    for app, args, expected_fragment in cases:
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        assert expected_fragment in result.output

    assert not (vault_mount / "personal").exists()
    assert dir_target.is_dir()
    assert file_target.read_text(encoding="utf-8") == "keep me"


def test_wipe_stick_mode_validation_contract() -> None:
    no_mode = runner.invoke(wipe_app, ["stick", "--path", "/dev/not-a-real-device"])
    assert no_mode.exit_code != 0
    assert "Choose exactly one of --fast or --full" in no_mode.output

    both_modes = runner.invoke(
        wipe_app,
        ["stick", "--path", "/dev/not-a-real-device", "--fast", "--full"],
    )
    assert both_modes.exit_code != 0
    assert "Choose exactly one of --fast or --full" in both_modes.output

    status_without_mode = runner.invoke(wipe_app, ["stick", "--path", "/dev/not-a-real-device", "--status"])
    assert status_without_mode.exit_code == 0
    assert "Wipe stick status:" in status_without_mode.output
