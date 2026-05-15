from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from forge.cli import app as forge_app
from stick.cli import app as stick_app
from vault.cli import app as vault_app
from wipe.cli import app as wipe_app

runner = CliRunner()


def test_stick_status_and_dry_run_labels_are_stable() -> None:
    status = runner.invoke(stick_app, ["create", "--id", "blue", "--path", "/dev/not-a-real-device", "--status"])
    assert status.exit_code == 0
    for fragment in [
        "Stick create status:",
        "ID:                blue",
        "Path:              /dev/not-a-real-device",
        "Path exists:",
        "Stick:             blue-stick",
        "Mapper:            map-blue-stick",
        "Filesystem label:  blue_stick",
        "Mount path:        /media/blue-stick",
        "Ready:",
    ]:
        assert fragment in status.output

    dry_run = runner.invoke(stick_app, ["mount", "--id", "blue", "--path", "/dev/not-a-real-device", "--dry-run"])
    assert dry_run.exit_code == 0
    for fragment in ["Plan:", "Equivalent commands:", "sudo cryptsetup open", "Dry-run only. No changes were made."]:
        assert fragment in dry_run.output


def test_vault_status_and_dry_run_labels_are_stable(tmp_path: Path) -> None:
    media_mount = tmp_path / "blue-stick"
    media_mount.mkdir()

    status = runner.invoke(
        vault_app,
        ["create", "--media-id", "blue", "--mount", str(media_mount), "--vault", "personal", "--size", "8M", "--purpose", "personal", "--status"],
    )
    assert status.exit_code == 0
    for fragment in [
        "Vault status:",
        "Media ID:          blue",
        f"Media mount:       {media_mount}",
        "Media mounted:",
        "Vault:             blue-personal-vault",
        f"Vault dir:         {media_mount / 'personal'}",
        f"Vault image:       {media_mount / 'personal' / 'personal.img'}",
        f"Secret path:       {media_mount / 'personal' / 'personal.kdbx'}",
        "Mapper:            CLOSED (map-blue-personal-vault)",
        "Vault mount:       /media/blue-personal-vault",
        "Ready:",
    ]:
        assert fragment in status.output

    dry_run = runner.invoke(
        vault_app,
        ["create", "--media-id", "blue", "--mount", str(media_mount), "--vault", "personal", "--size", "8M", "--purpose", "personal", "--dry-run"],
    )
    assert dry_run.exit_code == 0
    for fragment in [
        "Requested size:    8M",
        "Purpose:           personal",
        "Plan:",
        "Leave matching secret manual at:",
        "Equivalent commands:",
        "Dry-run only. No changes were made.",
    ]:
        assert fragment in dry_run.output
    assert not (media_mount / "personal").exists()


def test_wipe_status_and_dry_run_labels_are_stable(tmp_path: Path) -> None:
    dir_target = tmp_path / "scratch-dir"
    dir_target.mkdir()
    file_target = tmp_path / "scratch-file.txt"
    file_target.write_text("keep", encoding="utf-8")

    stick_status = runner.invoke(wipe_app, ["stick", "--path", "/dev/not-a-real-device", "--status"])
    assert stick_status.exit_code == 0
    for fragment in ["Wipe stick status:", "Path:              /dev/not-a-real-device", "Exists:", "Ready:"]:
        assert fragment in stick_status.output

    dir_dry_run = runner.invoke(wipe_app, ["dir", "--path", str(dir_target), "--dry-run"])
    assert dir_dry_run.exit_code == 0
    for fragment in ["Wipe dir status:", "Plan:", "Dry-run procedure:", "Dry-run only. No changes were made."]:
        assert fragment in dir_dry_run.output

    file_dry_run = runner.invoke(wipe_app, ["file", "--path", str(file_target), "--dry-run"])
    assert file_dry_run.exit_code == 0
    for fragment in ["Wipe file status:", "Plan:", "Dry-run procedure:", "Dry-run only. No changes were made."]:
        assert fragment in file_dry_run.output

    assert dir_target.exists()
    assert file_target.read_text(encoding="utf-8") == "keep"


def test_forge_manual_output_is_non_operational() -> None:
    for command in ["validate", "inspect", "generate"]:
        result = runner.invoke(forge_app, [command, "--manual"])
        assert result.exit_code == 0
        assert f"Forge manual procedure: {command}" in result.output
        assert "$ forge validate" in result.output
        assert f"$ forge {command}" in result.output
        assert "No operational stick or vault data is modified by forge." in result.output
