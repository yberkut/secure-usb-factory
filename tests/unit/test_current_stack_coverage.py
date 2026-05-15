from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from forge.cli import app as forge_app
from stick.cli import app as stick_app
from vault.cli import app as vault_app
from wipe.cli import app as wipe_app
from usb_forge.packager import _packaged_available_tools, _packaged_root, _render_atomic_script, _render_scenario_script, _repo_root_from_source, _shell_quote, _translated_scenario_cli_args, _translated_tool_and_args, stage_artifact
from usb_forge.planner import build_plan, inspect_plan
from usb_forge.validator import validate_generation_inputs
from usb_linux import blockdev, files, luks, mounts
from usb_shared.config.loader import load_config
from usb_shared.config.schema import ArtifactsConfig, AtomicScriptConfig, ForgeConfig, PackageConfig, ScenarioStepConfig, ScenarioScriptConfig, StickConfig, SufConfig, VaultConfig
from usb_shared.config.validate import validate_config
from usb_shared.errors import ValidationError
from usb_shared.execution import ExecutionContext, format_command, make_context
from usb_shared.naming import derive_stick_names, derive_vault_names
from usb_shared.subprocesses import format_process_error, run, run_interactive, run_with_input
from usb_stick.service import StickService
from usb_vault.service import VaultService
from usb_wipe.service import WipeService
from tools.package import _copy_runtime_docs, _load_package_config, _needed_source_cli_names, _tool_runtime_script, _write_executable_package, _write_executable_runtime, _write_manifest, _write_packaged_forge_config, _write_tree_package


def script(name: str, tool: str, command: str, **kwargs) -> AtomicScriptConfig:
    return AtomicScriptConfig(name=name, type="atomic", tool=tool, command=command, help=name, **kwargs)  # type: ignore[arg-type]


def config(*scripts: object, sticks: dict[str, StickConfig] | None = None, out: str = "build/suf") -> SufConfig:
    return SufConfig(
        artifacts=ArtifactsConfig(output_dir=out),
        sticks=sticks if sticks is not None else {"blue": StickConfig("/dev/disk/by-id/blue", "test", {"personal": VaultConfig("8G", "personal data")})},
        forge=ForgeConfig({getattr(w, "name"): w for w in scripts}),
    )


@pytest.mark.parametrize("app,text", [(stick_app, "stick 1.0.0"), (vault_app, "vault 1.0.0"), (wipe_app, "wipe 1.0.0"), (forge_app, "forge 1.0.0")])
def test_cli_versions(app, text):
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert text in result.stdout


@pytest.mark.parametrize("app", [stick_app, vault_app, wipe_app, forge_app])
def test_cli_help(app):
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert runner.invoke(app, ["-h"]).exit_code == 0


def test_wipe_dir_and_file_reject_mode_flags():
    runner = CliRunner()
    for target in ("dir", "file"):
        for flag in ("--fast", "--full"):
            result = runner.invoke(wipe_app, [target, "--path", "/tmp/target", flag, "--dry-run"])
            assert result.exit_code != 0
            assert "No such option" in result.output


def test_wipe_stick_requires_explicit_mode_except_status():
    service = WipeService()
    assert not service.stick("/dev/x").ok
    assert not service.stick("/dev/x", dry_run=True).ok
    assert not service.stick("/dev/x", manual=True).ok
    assert not service.stick("/dev/x", fast=True, full=True).ok
    assert service.stick("/dev/x", status=True).ok
    assert service.stick("/dev/x", fast=True, manual=True).ok
    assert service.stick("/dev/x", full=True, manual=True).ok



@pytest.mark.parametrize("stick_id", ["blue", "travel", "vault01", "alpha-2"])
def test_stick_name_derivation(stick_id):
    names = derive_stick_names(stick_id)
    assert names.stick_name == f"{stick_id}-stick"
    assert names.stick_mapper == f"map-{stick_id}-stick"
    assert str(names.stick_mount) == f"/media/{stick_id}-stick"
    assert names.stick_fs_label == f"{stick_id}_stick".replace("-", "_")


@pytest.mark.parametrize("stick_id,vault", [("blue", "personal"), ("travel", "admin"), ("vault01", "docs"), ("alpha", "keys")])
def test_vault_name_derivation(stick_id, vault):
    names = derive_vault_names(stick_id, vault)
    assert names.vault_name == f"{stick_id}-{vault}-vault"
    assert names.vault_mapper == f"map-{stick_id}-{vault}-vault"
    assert str(names.vault_dir) == f"/media/{stick_id}-stick/{vault}"
    assert str(names.vault_image) == f"/media/{stick_id}-stick/{vault}/{vault}.img"
    assert str(names.secret_path) == f"/media/{stick_id}-stick/{vault}/{vault}.kdbx"


@pytest.mark.parametrize("cmd,expected", [(["echo", "x"], "echo x"), (["touch", "a b"], "touch 'a b'"), (["printf", "it's"], "printf 'it'\"'\"'s'")])
def test_format_command(cmd, expected):
    assert format_command(cmd) == expected


def test_execution_context_emit_control():
    logs: list[str] = []
    make_context(False, logs.append).info("hidden")
    assert logs == []
    ctx = ExecutionContext(True, logs.append)
    ctx.step(1, 2, "work")
    ctx.command(["echo", "a b"])
    assert logs == ["[1/2] work", "$ echo 'a b'"]


def test_subprocess_scripts(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 3, stdout="out", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run(["x"], check=False).stdout == "out"
    assert run_interactive(["x"], check=False) == 3
    assert run_with_input(["x"], "secret", check=False).stdout == "out"
    assert calls[2][1]["input"] == "secret"


@pytest.mark.parametrize("exc,expected", [(subprocess.CalledProcessError(1, ["x"], stderr="err"), "err"), (subprocess.CalledProcessError(1, ["x"], output="out"), "out"), (subprocess.CalledProcessError(1, ["x", "a b"]), "Command failed (1): x 'a b'")])
def test_format_process_error(exc, expected):
    assert format_process_error(exc) == expected


def test_load_config_from_toml(tmp_path):
    path = tmp_path / "suf.toml"
    path.write_text('[artifacts]\noutput_dir="out"\n[sticks.blue]\ndevice_path="/dev/blue"\npurpose="test"\n[sticks.blue.vaults.personal]\nsize="8G"\npurpose="personal data"\n[forge.scripts.open]\ntype="atomic"\ntool="stick"\ncommand="mount"\nhelp="open"\nstick_id="blue"\n')
    loaded = load_config(path)
    assert loaded.sticks["blue"].vaults["personal"].purpose == "personal data"
    assert isinstance(loaded.forge.scripts["open"], AtomicScriptConfig)


@pytest.mark.parametrize("bad,pattern", [(config(sticks={}), "At least one stick"), (config(sticks={"": StickConfig("/dev/x", "")}), "Stick ID"), (config(sticks={"blue": StickConfig("", "")}), "device_path"), (config(sticks={"blue": StickConfig("/dev/x", "", {"v": VaultConfig("", "")})}), "empty size")])
def test_validate_config_bad_shapes(bad, pattern):
    with pytest.raises(ValidationError, match=pattern):
        validate_config(bad)




def test_validate_config_rejects_bad_script_id():
    cfg = config(script("bad_name", "stick", "mount", stick_id="blue"))
    with pytest.raises(ValidationError, match="script name"):
        validate_config(cfg)



@pytest.mark.parametrize("bad_script,pattern", [(script("bad", "stick", "bogus", stick_id="blue"), "Invalid atomic"), (script("bad", "stick", "mount", stick_id="missing"), "Unknown Stick"), (script("bad", "vault", "mount", stick_id="blue"), "requires stick_id and vault"), (script("bad", "vault", "mount", stick_id="blue", vault="missing"), "Unknown vault"), (script("bad", "wipe", "stick"), "requires stick_id"), (script("bad", "wipe", "dir"), "fixed_args")])
def test_validate_generation_inputs_bad_scripts(bad_script, pattern):
    with pytest.raises(ValidationError, match=pattern):
        validate_generation_inputs(config(bad_script))


@pytest.mark.parametrize("step", [ScenarioStepConfig("cli", command=["mount"]), ScenarioStepConfig("cli", tool="stick"), ScenarioStepConfig("entrypoint", module="m"), ScenarioStepConfig("python"), ScenarioStepConfig("weird")])
def test_validate_generation_inputs_bad_steps(step):
    scenario = ScenarioScriptConfig("flow", "scenario", "help", steps=[step])
    with pytest.raises(ValidationError):
        validate_generation_inputs(config(scenario))


def test_forge_plan_inspect_and_stage(tmp_path, monkeypatch):
    open_script = script("open", "stick", "mount", stick_id="blue")
    scenario = ScenarioScriptConfig(
        "flow",
        "scenario",
        "help",
        steps=[ScenarioStepConfig("cli", tool="stick", command=["mount"], args=["--id", "blue"])],
    )
    cfg = config(open_script, script("v", "vault", "mount", stick_id="blue", vault="personal"), script("w", "wipe", "stick", stick_id="blue"), scenario, out="out")
    plan = build_plan(cfg)
    assert plan.included_packages == ["src", "usb_shared", "usb_linux", "usb_stick", "usb_vault", "usb_wipe"]
    assert "Scripts generated: open, v, w, flow" in inspect_plan(cfg)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("usb_forge.packager._copy_tree", lambda src, dst: (dst.mkdir(parents=True, exist_ok=True), (dst / "copied").write_text(str(src))))
    out = stage_artifact(cfg)
    assert (out / "open").exists()
    assert (out / "flow").exists()
    assert (out / "manifest.json").exists()
    assert json.loads((out / "manifest.json").read_text())["generated_scripts"] == ["open", "v", "w", "flow"]



def test_disabled_scripts_are_validated_but_not_generated(tmp_path, monkeypatch):
    enabled = script("open", "stick", "mount", stick_id="blue")
    disabled = script("skip", "vault", "mount", stick_id="blue", vault="personal", disabled=True)
    disabled_bad = script("bad-disabled", "vault", "mount", stick_id="blue", vault="missing", disabled=True)

    with pytest.raises(ValidationError, match="Unknown vault"):
        validate_generation_inputs(config(disabled_bad))

    cfg = config(enabled, disabled, out="out")
    validate_generation_inputs(cfg)
    plan = build_plan(cfg)
    assert plan.atomic_scripts == ["open"]
    assert plan.disabled_scripts == ["skip"]
    assert "Scripts generated: open" in inspect_plan(cfg)
    assert "Scripts disabled: skip" in inspect_plan(cfg)
    assert plan.included_packages == ["src", "usb_shared", "usb_linux", "usb_stick"]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("usb_forge.packager._copy_tree", lambda src, dst: (dst.mkdir(parents=True, exist_ok=True), (dst / "copied").write_text(str(src))))
    out = stage_artifact(cfg)
    assert (out / "open").exists()
    assert not (out / "skip").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["generated_scripts"] == ["open"]
    assert manifest["disabled_scripts"] == ["skip"]

def test_forge_executable_library_layout(tmp_path, monkeypatch):
    cfg = config(script("open", "stick", "mount", stick_id="blue"), out="out")
    cfg = SufConfig(
        artifacts=ArtifactsConfig(output_dir="out"), package=PackageConfig(lib_layout="executable"),
        sticks=cfg.sticks,
        forge=cfg.forge,
    )
    monkeypatch.chdir(tmp_path)

    def fake_runtime(repo_root, output, plan):
        runtime = output / "lib" / "runtime"
        runtime.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        runtime.chmod(0o755)
        return runtime

    monkeypatch.setattr("usb_forge.packager._write_executable_runtime", fake_runtime)
    out = stage_artifact(cfg)
    assert (out / "lib" / "runtime").exists()
    assert not (out / "lib" / "src").exists()
    script_text = (out / "open").read_text()
    assert '"$ROOT_DIR/lib/runtime" stick' in script_text
    assert "PYTHONPATH" not in script_text


def test_forge_archive_format_zip_packages_complete_artifact(tmp_path, monkeypatch):
    cfg = config(script("open", "stick", "mount", stick_id="blue"), out="out")
    cfg = SufConfig(
        artifacts=ArtifactsConfig(output_dir="out", archive_format="zip"),
        sticks=cfg.sticks,
        forge=cfg.forge,
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("usb_forge.packager._copy_tree", lambda src, dst: (dst.mkdir(parents=True, exist_ok=True), (dst / "copied").write_text(str(src))))
    out = stage_artifact(cfg)
    archive_path = tmp_path / "out.zip"
    assert archive_path.exists()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert "out/open" in names
    assert "out/manifest.json" in names
    assert json.loads((out / "manifest.json").read_text())["archive_format"] == "zip"


@pytest.mark.parametrize("wrap,entry,args", [
    (script("s", "stick", "mount", stick_id="blue"), "stick", ["mount", "--id", "blue", "--path", "/dev/disk/by-id/blue"]),
    (script("ss", "stick", "mount", stick_id="blue", fixed_args=["--status"]), "stick", ["mount", "--id", "blue", "--path", "/dev/disk/by-id/blue", "--status"]),
    (script("v", "vault", "mount", stick_id="blue", vault="personal"), "vault", ["mount", "--media-id", "blue", "--mount", "/media/blue-stick", "--vault", "personal"]),
    (script("vu", "vault", "unmount", stick_id="blue", vault="personal"), "vault", ["unmount", "--media-id", "blue", "--vault", "personal"]),
    (script("vs", "vault", "create", stick_id="blue", vault="personal", fixed_args=["--status"]), "vault", ["create", "--media-id", "blue", "--mount", "/media/blue-stick", "--vault", "personal", "--size", "8G", "--purpose", "personal data", "--status"]),
    (script("w", "wipe", "vault", stick_id="blue", vault="personal"), "wipe", ["vault", "--media-id", "blue", "--mount", "/media/blue-stick", "--vault", "personal"]),
    (script("ws", "wipe", "stick", stick_id="blue", fixed_args=["--status"]), "wipe", ["stick", "--path", "/dev/disk/by-id/blue", "--status"]),
])
def test_forge_translation(wrap, entry, args):
    assert _translated_tool_and_args(config(wrap), wrap) == (entry, args)




def test_vault_create_script_derives_size_and_purpose_from_config():
    wrap = script("create-personal", "vault", "create", stick_id="blue", vault="personal")
    assert _translated_tool_and_args(config(wrap), wrap) == (
        "vault",
        [
            "create",
            "--media-id",
            "blue",
            "--mount",
            "/media/blue-stick",
            "--vault",
            "personal",
            "--size",
            "8G",
            "--purpose",
            "personal data",
        ],
    )


@pytest.mark.parametrize(
    "bad_script,pattern",
    [
        (script("bad-path", "stick", "mount", stick_id="blue", fixed_args=["--path", "/dev/other"]), "must not set --path"),
        (script("bad-vault", "vault", "mount", stick_id="blue", vault="personal", fixed_args=["--vault", "other"]), "must not set --vault"),
        (script("bad-size", "vault", "create", stick_id="blue", vault="personal", fixed_args=["--size", "1G"]), "must not set --size"),
        (script("bad-wipe", "wipe", "stick", stick_id="blue", fixed_args=["--path", "/dev/other"]), "must not set --path"),
        (script("bad-option", "stick", "mount", stick_id="blue", fixed_args=["--status", "--path"]), "requires a value"),
    ],
)
def test_validate_generation_inputs_rejects_duplicate_bound_fixed_args(bad_script, pattern):
    with pytest.raises(ValidationError, match=pattern):
        validate_generation_inputs(config(bad_script))


def test_validate_generation_inputs_checks_scenario_target_references():
    bad_step = ScenarioStepConfig("cli", tool="vault", command=["mount"], args=["--media-id", "blue", "--vault", "missing"])
    scenario = ScenarioScriptConfig("flow", "scenario", "help", steps=[bad_step])
    with pytest.raises(ValidationError, match="Unknown vault reference in scenario step"):
        validate_generation_inputs(config(scenario))

    bad_id_step = ScenarioStepConfig("cli", tool="stick", command=["mount"], args=["--id", "../blue"])
    bad_id_scenario = ScenarioScriptConfig("bad-flow", "scenario", "help", steps=[bad_id_step])
    with pytest.raises(ValidationError, match="Invalid Stick ID"):
        validate_generation_inputs(config(bad_id_scenario))


def test_script_rendering_uses_current_modules():
    wrap = script("open", "stick", "mount", stick_id="blue", fixed_args=["--dry-run"])
    content = _render_atomic_script(config(wrap), wrap, ["lib/src", "lib/usb_shared"])
    assert "python3 -m stick.cli" in content
    assert "usage()" not in content
    assert "--help" in content
    assert "_suf_script_help" in content
    assert "Purpose:" in content
    scenario = ScenarioScriptConfig("flow", "scenario", "help", steps=[ScenarioStepConfig("cli", tool="vault", command=["mount"], args=["--media-id", "blue"])])
    scenario_content = _render_scenario_script(scenario, ["lib/src", "lib/usb_shared"])
    assert "python3 -m vault.cli 'mount' '--media-id' 'blue'" in scenario_content
    assert _shell_quote("it's") == "'it'\"'\"'s'"


def test_blockdev_identity(monkeypatch):
    monkeypatch.setattr(blockdev, "resolved_device_path", lambda path: "/dev/sdb")
    monkeypatch.setattr(blockdev, "run", lambda cmd, ctx=None: type("C", (), {"stdout": 'PATH="/dev/sdb" SIZE="8G" MODEL="Fast USB" VENDOR="Acme" TRAN="usb" SERIAL="123"\n'})())
    ident = blockdev.device_identity("/dev/x")
    assert ident.model == "Fast USB"
    assert ident.serial == "123"
    monkeypatch.setattr(blockdev, "run", lambda cmd, ctx=None: type("C", (), {"stdout": "/dev/sdb\n/dev/sdb1\n"})())
    assert blockdev.list_block_nodes("/dev/sdb") == ["/dev/sdb", "/dev/sdb1"]


@pytest.mark.parametrize("func,expected", [(lambda: blockdev.create_gpt("/dev/sdb"), ["sudo", "parted", "-s", "/dev/sdb", "mklabel", "gpt"]), (lambda: blockdev.create_primary_partition("/dev/sdb"), ["sudo", "parted", "-s", "/dev/sdb", "mkpart", "primary", "1MiB", "100%"]), (lambda: blockdev.wipe_signatures("/dev/sdb"), ["sudo", "wipefs", "-a", "/dev/sdb"]), (lambda: blockdev.overwrite_device_full("/dev/sdb"), ["sudo", "dd", "if=/dev/zero", "of=/dev/sdb", "bs=16M", "conv=fsync", "status=progress"])])
def test_blockdev_command_builders(monkeypatch, func, expected):
    calls = []
    monkeypatch.setattr(blockdev, "run", lambda cmd, ctx=None: calls.append(cmd))
    func()
    assert calls == [expected]


def test_zero_tail_and_luks(monkeypatch):
    calls = []
    monkeypatch.setattr(blockdev, "run", lambda cmd, ctx=None: calls.append(cmd) or type("C", (), {"stdout": str(64 * 1024 * 1024)})())
    blockdev.zero_device_tail("/dev/sdb", 16)
    assert "seek=48" in calls[-1]
    assert luks.mapper_path("map-x") == Path("/dev/mapper/map-x")
    values = iter(["a", "b"])
    monkeypatch.setattr(luks, "getpass", lambda prompt: next(values))
    with pytest.raises(ValueError):
        luks.luks_format("/dev/x")
    values = iter(["secret"])
    crypt_calls = []
    monkeypatch.setattr(luks, "getpass", lambda prompt: next(values))
    monkeypatch.setattr(luks, "run_with_input", lambda cmd, input_text, ctx=None: crypt_calls.append((cmd, input_text)))
    luks.open_mapper("/dev/x", "map-x")
    assert crypt_calls == [(["sudo", "cryptsetup", "open", "/dev/x", "map-x"], "secret\n")]


def test_mount_and_file_helpers(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(mounts, "run", lambda cmd, ctx=None: calls.append(cmd))
    mounts.ensure_mount_dir(Path("/m"))
    mounts.mount_device("/d", Path("/m"))
    mounts.unmount_path(Path("/m"))
    mounts.force_unmount_path(Path("/m"))
    mounts.remove_empty_dir(Path("/m"))
    assert calls[0] == ["sudo", "mkdir", "-p", "/m"]
    assert calls[-1] == ["sudo", "rmdir", "/m"]
    monkeypatch.setattr(mounts, "list_mounts", lambda: [("/dev/sdb1", "/media/x"), ("tmpfs", "/run")])
    assert mounts.mounted_targets_for_sources(["/dev/sdb1"]) == [Path("/media/x")]
    monkeypatch.setattr(files, "run", lambda cmd, ctx=None: calls.append(cmd))
    target = tmp_path / "d" / "f.img"
    files.create_sparse_file(target, "1G")
    assert target.parent.exists()


def test_stick_service_status_manual_dry_run(monkeypatch):
    monkeypatch.setattr("usb_stick.service.which", lambda cmd: f"/bin/{cmd}")
    monkeypatch.setattr("usb_stick.service.device_exists", lambda path: True)
    monkeypatch.setattr("usb_stick.service.is_mounted", lambda path: False)
    monkeypatch.setattr("usb_stick.service.mapper_exists", lambda name: False)
    service = StickService()
    assert "blue-stick" in "\n".join(service.create_status("blue", "/dev/x").lines)
    assert "sudo parted" in "\n".join(service.create_manual("blue", "/dev/x").lines)
    assert "Dry-run only. No changes were made." in service.create("blue", "/dev/x", dry_run=True).lines
    assert "Dry-run only. No changes were made." in service.mount("blue", "/dev/x", dry_run=True).lines
    assert "Dry-run only. No changes were made." in service.unmount("blue", dry_run=True).lines


def test_stick_create_mount_unmount_execution(monkeypatch):
    monkeypatch.setattr("usb_stick.service.device_exists", lambda path: True)
    monkeypatch.setattr("usb_stick.service.confirm", lambda message: True)
    monkeypatch.setattr("usb_stick.service.is_mounted", lambda path: False)
    monkeypatch.setattr("usb_stick.service.mapper_exists", lambda name: False)
    calls = []
    for name in ["create_gpt", "create_primary_partition", "reread_partition_table"]:
        monkeypatch.setattr(f"usb_stick.service.{name}", lambda path, _name=name, **kw: calls.append((_name, path)))
    monkeypatch.setattr("usb_stick.service.first_partition_path", lambda path, **kw: "/dev/sdb1")
    monkeypatch.setattr("usb_stick.service.luks_format", lambda path, **kw: calls.append(("luks", path)))
    monkeypatch.setattr("usb_stick.service.open_mapper", lambda path, name, **kw: calls.append(("open", name)))
    monkeypatch.setattr("usb_stick.service.make_ext4_filesystem", lambda path, label, **kw: calls.append(("mkfs", label)))
    monkeypatch.setattr("usb_stick.service.close_mapper", lambda name, **kw: calls.append(("close", name)))
    assert StickService().create("blue", "/dev/x").ok
    assert calls[-1] == ("close", "map-blue-stick")
    calls.clear()
    monkeypatch.setattr("usb_stick.service.ensure_mount_dir", lambda path, **kw: calls.append(("mkdir", str(path))))
    monkeypatch.setattr("usb_stick.service.mount_device", lambda source, target, **kw: calls.append(("mount", str(target))))
    monkeypatch.setattr("usb_stick.service.chown_path", lambda path, recursive=False, **kw: calls.append(("chown", str(path), recursive)))
    assert StickService().mount("blue", "/dev/x").ok
    assert calls[-1] == ("chown", "/media/blue-stick", False)
    monkeypatch.setattr("usb_stick.service.is_mounted", lambda path: True)
    monkeypatch.setattr("usb_stick.service.mapper_exists", lambda name: True)
    calls.clear()
    monkeypatch.setattr("usb_stick.service.unmount_path", lambda path, **kw: calls.append(("umount", str(path))))
    monkeypatch.setattr("usb_stick.service.remove_empty_dir", lambda path, **kw: calls.append(("rmdir", str(path))))
    assert StickService().unmount("blue").ok
    assert calls == [("umount", "/media/blue-stick"), ("close", "map-blue-stick"), ("rmdir", "/media/blue-stick")]


def test_stick_service_failure_paths(monkeypatch):
    monkeypatch.setattr("usb_stick.service.device_exists", lambda path: False)
    assert not StickService().create("blue", "/dev/x").ok
    monkeypatch.setattr("usb_stick.service.device_exists", lambda path: True)
    monkeypatch.setattr("usb_stick.service.confirm", lambda message: False)
    assert StickService().create("blue", "/dev/x").lines == ["Cancelled."]
    monkeypatch.setattr("usb_stick.service.confirm", lambda message: True)
    monkeypatch.setattr("usb_stick.service.create_gpt", lambda path, **kw: (_ for _ in ()).throw(subprocess.CalledProcessError(1, ["x"], stderr="boom")))
    assert StickService().create("blue", "/dev/x").lines[-1].endswith("boom")


def test_vault_service_status_manual_dry_run(monkeypatch):
    monkeypatch.setattr("usb_vault.service.which", lambda cmd: f"/bin/{cmd}")
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: True)
    monkeypatch.setattr("usb_vault.service.mapper_exists", lambda name: False)
    monkeypatch.setattr("usb_vault.service.path_exists", lambda path: False)
    service = VaultService()
    assert "blue-personal-vault" in "\n".join(service.status("blue", "/media/blue-stick", "personal").lines)
    assert "truncate -s 8G" in "\n".join(service.create_manual("blue", "/media/blue-stick", "personal", "8G", "personal data").lines)
    assert "Dry-run only. No changes were made." in service.create("blue", "/media/blue-stick", "personal", "8G", "personal data", dry_run=True).lines
    assert "Dry-run only. No changes were made." in service.mount("blue", "/media/blue-stick", "personal", dry_run=True).lines
    assert "Dry-run only. No changes were made." in service.unmount("blue", "personal", dry_run=True).lines


def test_vault_service_execution(monkeypatch):
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == "/media/blue-stick")
    monkeypatch.setattr("usb_vault.service.path_exists", lambda path: False)
    monkeypatch.setattr("usb_vault.service.confirm", lambda message: True)
    monkeypatch.setattr("usb_vault.service.is_writable_path", lambda path: True)
    monkeypatch.setattr("usb_vault.service.mapper_exists", lambda name: True)
    calls = []
    monkeypatch.setattr("usb_vault.service.ensure_dir", lambda path: calls.append(("mkdir", str(path))))
    monkeypatch.setattr("usb_vault.service.create_sparse_file", lambda path, size, **kw: calls.append(("truncate", size)))
    monkeypatch.setattr("usb_vault.service.luks_format", lambda path, **kw: calls.append(("luks", str(path))))
    monkeypatch.setattr("usb_vault.service.open_mapper", lambda path, name, **kw: calls.append(("open", name)))
    monkeypatch.setattr("usb_vault.service.make_ext4_filesystem", lambda path, label, **kw: calls.append(("mkfs", label)))
    monkeypatch.setattr("usb_vault.service.close_mapper", lambda name, **kw: calls.append(("close", name)))
    assert VaultService().create("blue", "/media/blue-stick", "personal", "8G", "personal data").ok
    assert calls[-1] == ("close", "map-blue-personal-vault")




def test_vault_create_rejects_unwritable_stick_mount(monkeypatch):
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == "/media/blue-stick")
    monkeypatch.setattr("usb_vault.service.path_exists", lambda path: False)
    monkeypatch.setattr("usb_vault.service.is_writable_path", lambda path: False)
    result = VaultService().create("blue", "/media/blue-stick", "personal", "8G", "personal data")
    text = "\n".join(result.lines)
    assert not result.ok
    assert "Media mount is not writable by current user: /media/blue-stick" in text
    assert "sudo chown -R $USER:$USER /media/blue-stick" in text


def test_vault_create_failure_after_image_creation_removes_partial_image(monkeypatch, tmp_path):
    mount = tmp_path / "blue-stick"
    mount.mkdir()

    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == str(mount))
    monkeypatch.setattr("usb_vault.service.confirm", lambda message: True)
    monkeypatch.setattr("usb_vault.service.is_writable_path", lambda path: True)
    monkeypatch.setattr("usb_vault.service.luks_format", lambda path, **kw: (_ for _ in ()).throw(subprocess.CalledProcessError(1, ["cryptsetup"], stderr="luks failed")))

    result = VaultService().create("blue", str(mount), "personal", "1M", "personal data")
    image = mount / "personal" / "personal.img"
    text = "\n".join(result.lines)

    assert not result.ok
    assert not image.exists()
    assert "Failed to create vault: luks failed" in text
    assert f"Removed partial vault image: {image}" in text


def test_vault_create_failure_after_mapper_open_closes_mapper_before_cleanup(monkeypatch, tmp_path):
    mount = tmp_path / "blue-stick"
    mount.mkdir()
    calls = []

    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == str(mount))
    monkeypatch.setattr("usb_vault.service.confirm", lambda message: True)
    monkeypatch.setattr("usb_vault.service.is_writable_path", lambda path: True)
    monkeypatch.setattr("usb_vault.service.luks_format", lambda path, **kw: calls.append(("luks", path)))
    monkeypatch.setattr("usb_vault.service.open_mapper", lambda path, name, **kw: calls.append(("open", name)))
    monkeypatch.setattr("usb_vault.service.make_ext4_filesystem", lambda path, label, **kw: (_ for _ in ()).throw(subprocess.CalledProcessError(1, ["mkfs"], stderr="mkfs failed")))
    monkeypatch.setattr("usb_vault.service.close_mapper", lambda name, **kw: calls.append(("close", name)))

    result = VaultService().create("blue", str(mount), "personal", "1M", "personal data")
    image = mount / "personal" / "personal.img"
    text = "\n".join(result.lines)

    assert not result.ok
    assert not image.exists()
    assert calls == [("luks", str(image)), ("open", "map-blue-personal-vault"), ("close", "map-blue-personal-vault")]
    assert "Closed mapper after failed creation: map-blue-personal-vault" in text
    assert f"Removed partial vault image: {image}" in text


def test_vault_create_preexisting_image_is_never_removed(monkeypatch, tmp_path):
    mount = tmp_path / "blue-stick"
    image = mount / "personal" / "personal.img"
    image.parent.mkdir(parents=True)
    image.write_text("existing")

    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == str(mount))

    def fail_prompt(message):
        raise AssertionError("vault create prompted despite pre-existing image")

    monkeypatch.setattr("usb_vault.service.confirm", fail_prompt)
    result = VaultService().create("blue", str(mount), "personal", "1M", "personal data")

    assert not result.ok
    assert image.read_text() == "existing"
    assert result.lines == [f"Vault image already exists: {image}"]


def test_vault_create_cleanup_failure_is_reported(monkeypatch, tmp_path):
    mount = tmp_path / "blue-stick"
    mount.mkdir()

    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == str(mount))
    monkeypatch.setattr("usb_vault.service.confirm", lambda message: True)
    monkeypatch.setattr("usb_vault.service.is_writable_path", lambda path: True)
    monkeypatch.setattr("usb_vault.service.luks_format", lambda path, **kw: (_ for _ in ()).throw(subprocess.CalledProcessError(1, ["cryptsetup"], stderr="luks failed")))
    monkeypatch.setattr(Path, "unlink", lambda self: (_ for _ in ()).throw(PermissionError("nope")))

    result = VaultService().create("blue", str(mount), "personal", "1M", "personal data")
    image = mount / "personal" / "personal.img"
    text = "\n".join(result.lines)

    assert not result.ok
    assert image.exists()
    assert f"Partial vault image may remain: {image}" in text
    assert "Remove it manually if needed." in text

def test_vault_mount_unmount_execution(monkeypatch):
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == "/media/blue-stick")
    monkeypatch.setattr("usb_vault.service.path_exists", lambda path: str(path).endswith("personal.img"))
    monkeypatch.setattr("usb_vault.service.mapper_exists", lambda name: False)
    calls = []
    monkeypatch.setattr("usb_vault.service.open_mapper", lambda path, name, **kw: calls.append(("open", name)))
    monkeypatch.setattr("usb_vault.service.ensure_mount_dir", lambda path, **kw: calls.append(("mkdir", str(path))))
    monkeypatch.setattr("usb_vault.service.mount_device", lambda source, target, **kw: calls.append(("mount", str(target))))
    assert VaultService().mount("blue", "/media/blue-stick", "personal").ok
    assert calls[-1] == ("mount", "/media/blue-personal-vault")
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == "/media/blue-personal-vault")
    monkeypatch.setattr("usb_vault.service.mapper_exists", lambda name: True)
    calls.clear()
    monkeypatch.setattr("usb_vault.service.unmount_path", lambda path, **kw: calls.append(("umount", str(path))))
    monkeypatch.setattr("usb_vault.service.close_mapper", lambda name, **kw: calls.append(("close", name)))
    monkeypatch.setattr("usb_vault.service.remove_empty_dir", lambda path, **kw: calls.append(("rmdir", str(path))))
    assert VaultService().unmount("blue", "personal").ok
    assert calls == [("umount", "/media/blue-personal-vault"), ("close", "map-blue-personal-vault"), ("rmdir", "/media/blue-personal-vault")]



def test_vault_mount_keepass_opens_secret_and_pauses_before_mapper(monkeypatch):
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == "/media/blue-stick")
    monkeypatch.setattr("usb_vault.service.path_exists", lambda path: str(path).endswith(("personal.img", "personal.kdbx")))
    monkeypatch.setattr("usb_vault.service.mapper_exists", lambda name: False)
    calls = []
    monkeypatch.setattr("usb_vault.service.open_path", lambda path: calls.append(("xdg-open", str(path))))
    monkeypatch.setattr("usb_vault.service.pause_for_enter", lambda message: calls.append(("pause", message)))
    monkeypatch.setattr("usb_vault.service.open_mapper", lambda path, name, **kw: calls.append(("open", name)))
    monkeypatch.setattr("usb_vault.service.ensure_mount_dir", lambda path, **kw: calls.append(("mkdir", str(path))))
    monkeypatch.setattr("usb_vault.service.mount_device", lambda source, target, **kw: calls.append(("mount", str(target))))

    result = VaultService().mount("blue", "/media/blue-stick", "personal", keepass=True)

    assert result.ok
    assert calls[:3] == [
        ("xdg-open", "/media/blue-stick/personal/personal.kdbx"),
        ("pause", "Press Enter when ready to open personal.img..."),
        ("open", "map-blue-personal-vault"),
    ]


def test_vault_mount_keepass_falls_back_to_vault_dir(monkeypatch):
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == "/media/blue-stick")
    monkeypatch.setattr("usb_vault.service.path_exists", lambda path: str(path).endswith("personal.img"))
    monkeypatch.setattr("usb_vault.service.mapper_exists", lambda name: False)
    calls = []
    monkeypatch.setattr("usb_vault.service.open_path", lambda path: calls.append(("xdg-open", str(path))))
    monkeypatch.setattr("usb_vault.service.pause_for_enter", lambda message: calls.append(("pause", message)))
    monkeypatch.setattr("usb_vault.service.open_mapper", lambda path, name, **kw: calls.append(("open", name)))
    monkeypatch.setattr("usb_vault.service.ensure_mount_dir", lambda path, **kw: calls.append(("mkdir", str(path))))
    monkeypatch.setattr("usb_vault.service.mount_device", lambda source, target, **kw: calls.append(("mount", str(target))))

    result = VaultService().mount("blue", "/media/blue-stick", "personal", keepass=True)

    assert result.ok
    assert calls[0] == ("xdg-open", "/media/blue-stick/personal")
    assert calls[1] == ("pause", "Press Enter when ready to open personal.img...")


def test_vault_mount_keepass_dry_run_and_manual_show_pause(monkeypatch):
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: str(path) == "/media/blue-stick")
    monkeypatch.setattr("usb_vault.service.path_exists", lambda path: str(path).endswith("personal.img"))
    service = VaultService()

    dry_run = "\n".join(service.mount("blue", "/media/blue-stick", "personal", keepass=True, dry_run=True).lines)
    manual = "\n".join(service.mount_manual("blue", "/media/blue-stick", "personal", keepass=True).lines)

    assert "Operator pause:    Press Enter when ready to open personal.img..." in dry_run
    assert "- Press Enter when ready to open personal.img..." in dry_run
    assert "$ read -r -p 'Press Enter when ready to open personal.img...'" in manual


def test_wipe_stick_status_manual_dryrun_execution(monkeypatch):
    identity = type("I", (), {"resolved_path": "/dev/sdb", "size": "8G", "vendor": "A", "model": "B", "transport": "usb", "serial": "1"})()
    monkeypatch.setattr("usb_wipe.service.device_exists", lambda path: True)
    monkeypatch.setattr("usb_wipe.service.is_block_device", lambda path: True)
    monkeypatch.setattr("usb_wipe.service.device_identity", lambda path, **kw: identity)
    monkeypatch.setattr("usb_wipe.service.list_block_nodes", lambda path, **kw: ["/dev/sdb1"])
    monkeypatch.setattr("usb_wipe.service.list_mapper_names_for_device", lambda path, **kw: [])
    monkeypatch.setattr("usb_wipe.service.mounted_targets_for_sources", lambda sources: [Path("/media/x")])
    monkeypatch.setattr("usb_wipe.service.is_mounted", lambda path: True)
    service = WipeService()
    assert "Mounted targets:   /media/x" in service.stick("/dev/x", status=True).lines
    assert "sudo wipefs" in "\n".join(service.stick("/dev/x", fast=True, manual=True).lines)
    assert "Dry-run only. No changes were made." in service.stick("/dev/x", fast=True, dry_run=True).lines
    monkeypatch.setattr("usb_wipe.service.prompt_text", lambda message: "/dev/x")
    calls = []
    monkeypatch.setattr("usb_wipe.service.force_unmount_path", lambda path, **kw: calls.append(("umount", str(path))))
    monkeypatch.setattr("usb_wipe.service.wipe_signatures", lambda path, **kw: calls.append(("wipe", path)))
    monkeypatch.setattr("usb_wipe.service.zero_device_head", lambda path, **kw: calls.append(("head", path)))
    monkeypatch.setattr("usb_wipe.service.zero_device_tail", lambda path, **kw: calls.append(("tail", path)))
    assert service.stick("/dev/x", fast=True).ok
    assert calls[0] == ("umount", "/media/x")


def test_wipe_vault_and_dir_file_paths(monkeypatch, tmp_path):
    mount = tmp_path / "blue-stick"
    vault_dir = mount / "personal"
    vault_dir.mkdir(parents=True)
    (vault_dir / "personal.img").write_text("x")
    (vault_dir / "personal.kdbx").write_text("y")
    service = WipeService()
    assert str(vault_dir) in "\n".join(service.vault("blue", str(mount), "personal", status=True).lines)
    assert "rm -rf" in "\n".join(service.vault("blue", str(mount), "personal", manual=True).lines)
    assert "Dry-run only. No changes were made." in service.vault("blue", str(mount), "personal", dry_run=True).lines
    monkeypatch.setattr("usb_wipe.service.prompt_text", lambda message: "YES")
    monkeypatch.setattr("usb_wipe.service.is_mounted", lambda path: str(path) == str(mount))
    monkeypatch.setattr("usb_wipe.service.mapper_exists", lambda name: False)
    assert service.vault("blue", str(mount), "personal", full=True).ok
    assert not vault_dir.exists()
    directory = tmp_path / "dir"
    directory.mkdir()
    file_path = tmp_path / "file"
    file_path.write_text("secret")
    assert "Dry-run only. No changes were made." in service.dir(str(directory), dry_run=True).lines
    assert "Dry-run only. No changes were made." in service.file(str(file_path), dry_run=True).lines
    monkeypatch.setattr("usb_wipe.service.prompt_text", lambda message: str(directory))
    assert service.dir(str(directory)).ok
    monkeypatch.setattr("usb_wipe.service.prompt_text", lambda message: str(file_path))
    assert service.file(str(file_path)).ok



def test_wipe_vault_requires_active_media_mount_before_prompt(monkeypatch, tmp_path):
    mount = tmp_path / "blue-stick"
    vault_dir = mount / "personal"
    vault_dir.mkdir(parents=True)
    (vault_dir / "personal.img").write_text("x")

    monkeypatch.setattr("usb_wipe.service.is_mounted", lambda path: False)

    def fail_prompt(message):
        raise AssertionError("wipe vault prompted before validating active media mount")

    monkeypatch.setattr("usb_wipe.service.prompt_text", fail_prompt)
    result = WipeService().vault("blue", str(mount), "personal")
    text = "\n".join(result.lines)

    assert not result.ok
    assert f"Media mount is not active: {mount}" in text
    assert vault_dir.exists()


def test_wipe_vault_status_manual_and_dry_run_show_mount_safety(monkeypatch, tmp_path):
    mount = tmp_path / "blue-stick"
    vault_dir = mount / "personal"
    vault_dir.mkdir(parents=True)
    monkeypatch.setattr("usb_wipe.service.is_mounted", lambda path: str(path) == str(mount))

    service = WipeService()
    status = "\n".join(service.vault("blue", str(mount), "personal", status=True).lines)
    manual = "\n".join(service.vault("blue", str(mount), "personal", manual=True).lines)
    dry_run = "\n".join(service.vault("blue", str(mount), "personal", dry_run=True).lines)

    assert "Media mounted:     YES" in status
    assert "Ready:             YES" in status
    assert f"Media mount must be active: {mount}" in manual
    assert "Close the matching KeePassXC database before wiping." in manual
    assert f"Would require active media mount: {mount}" in dry_run
    assert "Close the matching KeePassXC database before wiping." in dry_run


def test_wipe_stick_missing_device_fails_before_confirmation(monkeypatch):
    monkeypatch.setattr("usb_wipe.service.device_exists", lambda path: False)
    monkeypatch.setattr("usb_wipe.service.is_block_device", lambda path: False)

    def fail_prompt(message):
        raise AssertionError("wipe stick prompted before validating device path")

    monkeypatch.setattr("usb_wipe.service.prompt_text", fail_prompt)
    result = WipeService().stick("/dev/disk/by-id/missing", fast=True)
    text = "\n".join(result.lines)

    assert not result.ok
    assert "Configured device path does not exist: /dev/disk/by-id/missing" in text


def test_wipe_stick_valid_device_still_requires_confirmation(monkeypatch):
    identity = type("I", (), {"resolved_path": "/dev/sdb"})()
    prompts = []

    monkeypatch.setattr("usb_wipe.service.device_exists", lambda path: True)
    monkeypatch.setattr("usb_wipe.service.is_block_device", lambda path: True)
    monkeypatch.setattr("usb_wipe.service.device_identity", lambda path, **kw: identity)
    monkeypatch.setattr("usb_wipe.service.list_block_nodes", lambda path, **kw: ["/dev/sdb", "/dev/sdb1"])
    monkeypatch.setattr("usb_wipe.service.list_mapper_names_for_device", lambda path, **kw: [])
    monkeypatch.setattr("usb_wipe.service.mounted_targets_for_sources", lambda sources: [])
    monkeypatch.setattr("usb_wipe.service.prompt_text", lambda message: prompts.append(message) or "wrong")

    result = WipeService().stick("/dev/disk/by-id/test", fast=True)

    assert not result.ok
    assert prompts == ["Type the exact path to continue: /dev/disk/by-id/test"]


def test_wipe_stick_rejects_non_block_device_before_confirmation(monkeypatch):
    monkeypatch.setattr("usb_wipe.service.device_exists", lambda path: True)
    monkeypatch.setattr("usb_wipe.service.is_block_device", lambda path: False)

    def fail_prompt(message):
        raise AssertionError("wipe stick prompted before validating block-device target")

    monkeypatch.setattr("usb_wipe.service.prompt_text", fail_prompt)
    result = WipeService().stick("/tmp/not-a-block-device", fast=True)
    text = "\n".join(result.lines)

    assert not result.ok
    assert "Configured path is not a block device: /tmp/not-a-block-device" in text


def test_wipe_stick_closes_discovered_mappers_before_wiping(monkeypatch):
    identity = type("I", (), {"resolved_path": "/dev/sdb"})()
    calls = []

    monkeypatch.setattr("usb_wipe.service.device_exists", lambda path: True)
    monkeypatch.setattr("usb_wipe.service.is_block_device", lambda path: True)
    monkeypatch.setattr("usb_wipe.service.device_identity", lambda path, **kw: identity)
    monkeypatch.setattr("usb_wipe.service.list_block_nodes", lambda path, **kw: ["/dev/sdb", "/dev/sdb1"])
    monkeypatch.setattr("usb_wipe.service.list_mapper_names_for_device", lambda path, **kw: ["map-blue-stick"])
    monkeypatch.setattr("usb_wipe.service.mounted_targets_for_sources", lambda sources: [])
    monkeypatch.setattr("usb_wipe.service.prompt_text", lambda message: "/dev/disk/by-id/test")
    monkeypatch.setattr("usb_wipe.service.mapper_exists", lambda name: True)
    monkeypatch.setattr("usb_wipe.service.close_mapper", lambda name, **kw: calls.append(("close", name)))
    monkeypatch.setattr("usb_wipe.service.wipe_signatures", lambda path, **kw: calls.append(("wipe", path)))
    monkeypatch.setattr("usb_wipe.service.zero_device_head", lambda path, **kw: calls.append(("head", path)))
    monkeypatch.setattr("usb_wipe.service.zero_device_tail", lambda path, **kw: calls.append(("tail", path)))

    result = WipeService().stick("/dev/disk/by-id/test", fast=True)

    assert result.ok
    assert calls[0] == ("close", "map-blue-stick")
    assert ("wipe", "/dev/disk/by-id/test") in calls


def test_wipe_dir_and_file_reject_protected_and_symlink_targets(tmp_path):
    service = WipeService()

    protected_dir = service.dir("/etc", dry_run=True)
    assert not protected_dir.ok
    assert "Refusing to wipe protected path" in "\n".join(protected_dir.lines)

    real_file = tmp_path / "real.txt"
    real_file.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real_file)
    symlink_file = service.file(str(link), dry_run=True)
    assert not symlink_file.ok
    assert "Refusing to wipe symlink target" in "\n".join(symlink_file.lines)

    wrong_kind = service.file(str(tmp_path), dry_run=True)
    assert not wrong_kind.ok
    assert "Target is not a regular file" in "\n".join(wrong_kind.lines)

def test_root_manual_is_available_on_all_apps():
    runner = CliRunner()
    for app, expected, shared_phrase in [
        (stick_app, "Stick manual procedures:", "Use command-level --manual"),
        (vault_app, "Vault manual procedures:", "Use command-level --manual"),
        (wipe_app, "Wipe manual procedures:", "Note:"),
        (forge_app, "Forge manual procedures:", "Use command-level --manual"),
    ]:
        result = runner.invoke(app, ["--manual"])
        assert result.exit_code == 0
        assert expected in result.stdout
        assert shared_phrase in result.stdout


def test_wipe_vault_accepts_fast_flag_for_non_recursive_container_cleanup(tmp_path, monkeypatch):
    mount = tmp_path / "media"
    vault_dir = mount / "personal"
    vault_dir.mkdir(parents=True)
    monkeypatch.setattr("usb_wipe.service.is_mounted", lambda path: Path(path) == mount)
    result = CliRunner().invoke(
        wipe_app,
        [
            "vault",
            "--media-id",
            "blue",
            "--mount",
            str(mount),
            "--vault",
            "personal",
            "--fast",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "$ rm -f" in result.output
    assert "$ rm -rf" not in result.output


def test_vault_unmount_status_is_status_not_manual(monkeypatch):
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: False)
    monkeypatch.setattr("usb_vault.service.mapper_exists", lambda name: False)
    result = VaultService().unmount_status("blue", "personal")
    text = "\n".join(result.lines)
    assert "Vault unmount status:" in text
    assert "Manual procedure:" not in text


def test_scenario_script_manual_prints_steps():
    scenario = ScenarioScriptConfig(
        name="open-flow",
        type="scenario",
        help="Open flow",
        steps=[
            ScenarioStepConfig(
                kind="cli",
                tool="stick",
                command=["mount"],
                args=["--id", "blue", "--path", "/dev/sdb"],
            ),
            ScenarioStepConfig(
                kind="cli",
                tool="vault",
                command=["mount"],
                args=[
                    "--media-id",
                    "blue",
                    "--mount",
                    "/media/blue-stick",
                    "--vault",
                    "personal",
                ],
            ),
        ],
    )
    content = _render_scenario_script(scenario, ["lib/src", "lib/usb_shared"])
    assert "--manual" in content
    assert "Scenario manual procedure: open-flow" in content
    assert "python3 -m stick.cli" in content
    assert "python3 -m vault.cli" in content


def test_structured_scenario_step_derives_bound_args():
    step = ScenarioStepConfig("cli", tool="vault", command=["create"], stick_id="blue", vault="personal")
    assert _translated_scenario_cli_args(config(), step) == [
        "create",
        "--media-id",
        "blue",
        "--mount",
        "/media/blue-stick",
        "--vault",
        "personal",
        "--size",
        "8G",
        "--purpose",
        "personal data",
    ]


def test_structured_scenario_vault_unmount_omits_mount_arg():
    step = ScenarioStepConfig("cli", tool="vault", command=["unmount"], stick_id="blue", vault="personal")
    assert _translated_scenario_cli_args(config(), step) == [
        "unmount",
        "--media-id",
        "blue",
        "--vault",
        "personal",
    ]


def test_structured_scenario_step_rejects_duplicate_bound_args():
    step = ScenarioStepConfig(
        "cli",
        tool="vault",
        command=["mount"],
        stick_id="blue",
        vault="personal",
        args=["--mount", "/somewhere"],
    )
    scenario = ScenarioScriptConfig("flow", "scenario", "help", steps=[step])
    with pytest.raises(ValidationError, match="must not set --mount"):
        validate_generation_inputs(config(scenario))


def test_structured_scenario_script_renders_derived_commands():
    scenario = ScenarioScriptConfig(
        "flow",
        "scenario",
        "help",
        steps=[
            ScenarioStepConfig("cli", tool="stick", command=["mount"], stick_id="blue"),
            ScenarioStepConfig("cli", tool="vault", command=["mount"], stick_id="blue", vault="personal"),
        ],
    )
    content = _render_scenario_script(scenario, ["lib/src", "lib/usb_shared"], config=config())
    assert "python3 -m stick.cli 'mount' '--id' 'blue' '--path' '/dev/disk/by-id/blue'" in content
    assert "python3 -m vault.cli 'mount' '--media-id' 'blue' '--mount' '/media/blue-stick' '--vault' 'personal'" in content


def test_package_build_config_uses_package_layout():
    cfg = _load_package_config()
    with Path("suf.toml").open("rb") as fh:
        raw = tomllib.load(fh)
    expected_layout = raw.get("package", {}).get("lib_layout", "tree")
    expected_tools = raw.get("package", {}).get("tools", ["stick", "vault", "wipe", "forge"])
    assert cfg == {
        "tools": expected_tools,
        "output_dir": "dist/suf",
        "lib_layout": expected_layout,
        "include_manifest": raw.get("artifacts", {}).get("include_manifest", True),
    }




def test_package_build_config_allows_package_layout_override(monkeypatch):
    monkeypatch.setenv("SUF_PACKAGE_LIB_LAYOUT", "tree")
    assert _load_package_config()["lib_layout"] == "tree"
    monkeypatch.setenv("SUF_PACKAGE_LIB_LAYOUT", "executable")
    assert _load_package_config()["lib_layout"] == "executable"




def test_package_build_config_allows_package_tools_override(monkeypatch):
    monkeypatch.setenv("SUF_PACKAGE_TOOLS", "stick,forge")
    assert _load_package_config()["tools"] == ["stick", "forge"]


def test_package_build_config_rejects_empty_package_tools_override(monkeypatch):
    monkeypatch.setenv("SUF_PACKAGE_TOOLS", ",,,")
    with pytest.raises(SystemExit, match="SUF_PACKAGE_TOOLS"):
        _load_package_config()

def test_package_build_config_rejects_bad_package_layout_override(monkeypatch):
    monkeypatch.setenv("SUF_PACKAGE_LIB_LAYOUT", "bad")
    with pytest.raises(SystemExit, match="package.lib_layout"):
        _load_package_config()

def test_root_config_package_settings_are_optional(tmp_path):
    toml = tmp_path / "suf.toml"
    toml.write_text(
        """
[sticks.blue]
device_path = "/dev/disk/by-id/blue"
purpose = "test"
""".strip(),
        encoding="utf-8",
    )
    cfg = load_config(toml)
    assert cfg.package.lib_layout == "tree"
    assert cfg.package.tools == ["stick", "vault", "wipe", "forge"]
    assert cfg.sticks["blue"].device_path == "/dev/disk/by-id/blue"



def test_package_build_config_reads_include_manifest(tmp_path, monkeypatch):
    cfg_path = tmp_path / "suf.toml"
    cfg_path.write_text(
        """
[artifacts]
include_manifest = false

[package]
tools = ["stick"]
lib_layout = "tree"

[sticks.blue]
device_path = "/dev/disk/by-id/blue"
purpose = "test"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("tools.package.CONFIG_PATH", cfg_path)
    cfg = _load_package_config()
    assert cfg["include_manifest"] is False
    assert cfg["tools"] == ["stick"]


def test_package_build_config_reads_package_tools(tmp_path, monkeypatch):
    cfg_path = tmp_path / "suf.toml"
    cfg_path.write_text(
        """
[package]
tools = ["stick", "forge"]

[sticks.blue]
device_path = "/dev/disk/by-id/blue"
purpose = "test"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("tools.package.CONFIG_PATH", cfg_path)
    cfg = _load_package_config()
    assert cfg["tools"] == ["stick", "forge"]


def test_package_tools_default_to_runtime_tools_without_dispatcher_or_lab():
    with Path("suf.toml").open("rb") as fh:
        raw = tomllib.load(fh)
    assert raw["package"]["tools"] == ["stick", "vault", "wipe", "forge"]
    assert "suf" not in raw["package"]["tools"]
    assert "lab" not in raw["package"]["tools"]


def test_executable_tool_runtime_invokes_tool_app_directly():
    text = _tool_runtime_script("forge")
    assert "from forge.cli import app" in text
    assert "app(prog_name='forge')" in text
    assert "APPS" not in text

def test_package_validation_rejects_dispatcher_and_lab_tools():
    base = config(script("open", "stick", "mount", stick_id="blue"))
    for tool in ("suf", "lab"):
        bad = SufConfig(
            artifacts=base.artifacts,
            sticks=base.sticks,
            forge=base.forge,
            package=PackageConfig(tools=[tool]),  # type: ignore[list-item]
        )
        with pytest.raises(ValidationError, match="package.tools contains unknown packaged tools"):
            validate_config(bad)


def test_executable_runtime_builds_one_binary_per_selected_tool(tmp_path, monkeypatch):
    built: list[str] = []

    def fake_tool_executable(output, tool, package_keys):
        built.append(tool)
        runtime = output / "lib" / tool
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        runtime.chmod(0o755)
        return runtime

    monkeypatch.setattr("tools.package._write_tool_executable", fake_tool_executable)
    _write_executable_runtime(tmp_path / "package", ["stick", "forge"])
    assert built == ["stick", "forge"]
    assert (tmp_path / "package" / "lib" / "stick").exists()
    assert (tmp_path / "package" / "lib" / "forge").exists()
    assert not (tmp_path / "package" / "lib" / "suf").exists()


def test_package_runtime_docs_are_limited_to_selected_tools(tmp_path):
    out = tmp_path / "package"
    _copy_runtime_docs(out, ["stick", "forge"])
    docs = sorted(path.name for path in (out / "docs").iterdir())
    assert docs == ["forge.md", "stick.md"]


def test_package_writes_runtime_forge_config(tmp_path):
    out = tmp_path / "package"
    _write_packaged_forge_config(out, ["stick", "forge"])
    config_path = out / "config" / "forge.toml"
    text = config_path.read_text()
    assert "[project]" not in text
    assert "[forge.defaults]" not in text
    assert 'output_dir = "generated-scripts"' in text
    assert "[package]" not in text
    assert 'package_tools' not in text




def test_package_source_cli_names_are_limited_to_selected_tools():
    assert _needed_source_cli_names(["stick"]) == ["stick"]
    assert _needed_source_cli_names(["stick", "forge"]) == ["stick", "forge"]
    assert _needed_source_cli_names(["vault"]) == ["vault"]


def test_tree_package_copies_only_selected_source_cli_packages(tmp_path):
    out = tmp_path / "package"
    _write_tree_package(out, ["stick"])
    src_names = sorted(path.name for path in (out / "lib" / "src").iterdir())
    assert src_names == ["stick"]
    package_names = sorted(
        path.name for path in (out / "lib").iterdir() if path.name not in {"src", "vendor"}
    )
    assert package_names == ["usb_linux", "usb_shared", "usb_stick"]
    assert (out / "lib" / "vendor" / "typer").exists()


def test_package_manifest_is_optional(tmp_path):
    out = tmp_path / "package"
    out.mkdir()
    cfg = {
        "tools": ["stick"],
        "output_dir": str(out),
        "lib_layout": "tree",
        "include_manifest": False,
    }
    if cfg["include_manifest"]:
        _write_manifest(out, cfg)
    assert not (out / "manifest.json").exists()


def test_cli_module_entrypoint_files_call_apps():
    root = Path(__file__).resolve().parents[2]
    for rel in ["src/forge/cli.py", "src/vault/cli.py", "tools/e2e_runner.py"]:
        text = (root / rel).read_text(encoding="utf-8")
        assert 'if __name__ == "__main__":' in text
        assert "main()" in text


def test_packaged_forge_generates_scripts_that_call_packaged_bin(tmp_path, monkeypatch):
    package_root = tmp_path / "package"
    (package_root / "config").mkdir(parents=True)
    (package_root / "bin").mkdir(parents=True)
    (package_root / "bin" / "stick").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (package_root / "config" / "forge.toml").write_text("# marker", encoding="utf-8")
    cfg = config(script("open", "stick", "mount", stick_id="blue"), out="generated-scripts")
    monkeypatch.setenv("USB_FACTORY_PACKAGE_ROOT", str(package_root))
    out = stage_artifact(cfg)
    assert out == package_root / "generated-scripts"
    assert (out / "open").exists()
    assert not (out / "lib").exists()
    text = (out / "open").read_text()
    assert '"$ROOT_DIR/../bin/stick"' in text
    assert "PYTHONPATH" not in text


def test_packaged_forge_skips_scripts_without_packaged_tools(tmp_path, monkeypatch):
    package_root = tmp_path / "package"
    bin_dir = package_root / "bin"
    (package_root / "config").mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    (package_root / "config" / "forge.toml").write_text("# marker", encoding="utf-8")
    for tool in ("stick", "forge"):
        path = bin_dir / tool
        path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        path.chmod(0o755)

    scenario = ScenarioScriptConfig(
        "flow",
        "scenario",
        "help",
        steps=[
            ScenarioStepConfig("cli", tool="stick", command=["mount"], stick_id="blue"),
            ScenarioStepConfig("cli", tool="vault", command=["mount"], stick_id="blue", vault="personal"),
        ],
    )
    cfg = config(
        script("open", "stick", "mount", stick_id="blue"),
        script("vault-open", "vault", "mount", stick_id="blue", vault="personal"),
        script("wipe-stick", "wipe", "stick", stick_id="blue", fixed_args=["--fast"]),
        scenario,
        out="generated-scripts",
    )
    notices: list[str] = []
    monkeypatch.setenv("USB_FACTORY_PACKAGE_ROOT", str(package_root))

    out = stage_artifact(cfg, reporter=notices.append)

    assert out == package_root / "generated-scripts"
    assert (out / "open").exists()
    assert not (out / "vault-open").exists()
    assert not (out / "wipe-stick").exists()
    assert not (out / "flow").exists()
    assert notices == [
        "Skipped script: vault-open (missing packaged tool: vault)",
        "Skipped script: wipe-stick (missing packaged tool: wipe)",
        "Skipped script: flow (missing packaged tool: vault)",
        "Not all scripts were generated; missing packaged tools: vault, wipe",
    ]
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["generated_scripts"] == ["open"]
    assert manifest["skipped_scripts"] == [
        {"name": "vault-open", "missing_tools": ["vault"]},
        {"name": "wipe-stick", "missing_tools": ["wipe"]},
        {"name": "flow", "missing_tools": ["vault"]},
    ]


def test_packaged_available_tools_reads_existing_bin_tools(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("stick", "forge", "README"):
        (bin_dir / name).write_text("x", encoding="utf-8")
    assert _packaged_available_tools(tmp_path) == {"stick", "forge"}


def test_tree_packaged_scripts_export_package_root(tmp_path):
    out = tmp_path / "package"
    _write_tree_package(out, ["forge"])
    text = (out / "bin" / "forge").read_text(encoding="utf-8")
    assert 'export SUF_FORGE_CONFIG="${SUF_FORGE_CONFIG:-$ROOT_DIR/config/forge.toml}"' in text
    assert 'export USB_FACTORY_PACKAGE_ROOT="${USB_FACTORY_PACKAGE_ROOT:-$ROOT_DIR}"' in text
    assert 'export SHELL="${SHELL:-/bin/bash}"' in text
    assert '_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION=1' in text


def test_executable_packaged_scripts_delegate_to_lib_runtime(tmp_path, monkeypatch):
    out = tmp_path / "package"

    def fake_runtime(output, tools):
        runtime = output / "lib" / "forge"
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        runtime.chmod(0o755)

    monkeypatch.setattr("tools.package._write_executable_runtime", fake_runtime)
    _write_executable_package(out, ["forge"])
    text = (out / "bin" / "forge").read_text(encoding="utf-8")
    assert 'exec "$ROOT_DIR/lib/forge" "$@"' in text
    assert not (out / "bin" / "stick").exists()
    assert 'export SHELL="${SHELL:-/bin/bash}"' in text
    assert '_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION=1' in text
    assert "PYTHONPATH" not in text


def test_atomic_scripts_forward_completion_to_root_cli():
    wrap = script("open", "stick", "mount", stick_id="blue")
    text = _render_atomic_script(config(wrap), wrap, ["lib/src", "lib/usb_shared"])
    assert 'if [[ ${1:-} == "--show-completion" || ${1:-} == "--install-completion" ]]; then' in text
    assert 'exec python3 -m stick.cli "$@"' in text


def test_stick_unmount_reports_already_unmounted_and_cleanup_warning(monkeypatch):
    monkeypatch.setattr("usb_stick.service.is_mounted", lambda path: False)
    monkeypatch.setattr("usb_stick.service.mapper_exists", lambda name: False)
    calls = []
    monkeypatch.setattr("usb_stick.service.unmount_path", lambda path, **kw: calls.append(("umount", str(path))))
    monkeypatch.setattr("usb_stick.service.close_mapper", lambda name, **kw: calls.append(("close", name)))
    monkeypatch.setattr("usb_stick.service.remove_empty_dir", lambda path, **kw: (_ for _ in ()).throw(OSError("not empty")))

    result = StickService().unmount("blue")
    text = "\n".join(result.lines)

    assert result.ok
    assert calls == []
    assert "Stick was already unmounted: blue-stick" in text
    assert "Could not remove mount directory: /media/blue-stick" in text
    assert "Remove it manually if needed." in text


def test_vault_unmount_reports_already_unmounted_and_cleanup_warning(monkeypatch):
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: False)
    monkeypatch.setattr("usb_vault.service.mapper_exists", lambda name: False)
    calls = []
    monkeypatch.setattr("usb_vault.service.unmount_path", lambda path, **kw: calls.append(("umount", str(path))))
    monkeypatch.setattr("usb_vault.service.close_mapper", lambda name, **kw: calls.append(("close", name)))
    monkeypatch.setattr("usb_vault.service.remove_empty_dir", lambda path, **kw: (_ for _ in ()).throw(OSError("not empty")))

    result = VaultService().unmount("blue", "personal")
    text = "\n".join(result.lines)

    assert result.ok
    assert calls == []
    assert "Vault was already unmounted: blue-personal-vault" in text
    assert "Could not remove mount directory: /media/blue-personal-vault" in text
    assert "Remove it manually if needed." in text



def test_forge_inspect_output_is_labeled_and_expanded():
    open_script = script("open", "stick", "mount", stick_id="blue")
    scenario = ScenarioScriptConfig(
        "flow",
        "scenario",
        "help",
        steps=[ScenarioStepConfig("cli", tool="stick", command=["mount"])],
    )
    cfg = config(open_script, scenario)
    lines = inspect_plan(cfg).splitlines()
    assert "Forge inspection:" in lines
    assert "Output artifact: build/suf" in lines
    assert "Library layout: tree" in lines
    assert "Atomic scripts:" in lines
    assert "- open: stick mount target=blue args=(none)" in lines
    assert "Scenario scripts:" in lines
    assert "- flow: 1 step(s), stop-on-error=YES" in lines
    assert "Packages in lib/: src, usb_shared, usb_linux, usb_stick" in lines
    # Keep the compact compatibility summary for older operator notes/tests.
    assert "Scripts generated: open, flow" in lines


def test_forge_validate_cli_reports_config_path_and_counts(tmp_path, monkeypatch):
    config_path = tmp_path / "suf.toml"
    config_path.write_text('[artifacts]\noutput_dir="out"\n[sticks.blue]\ndevice_path="/dev/blue"\npurpose="test"\n[forge.scripts.open]\ntype="atomic"\ntool="stick"\ncommand="mount"\nhelp="open"\nstick_id="blue"\n')
    monkeypatch.setenv("SUF_FORGE_CONFIG", str(config_path))
    result = CliRunner().invoke(forge_app, ["validate"])
    assert result.exit_code == 0
    assert "Forge validation:" in result.output
    assert f"Config file: {config_path}" in result.output
    assert "Result: OK" in result.output
    assert "Scripts checked: 1" in result.output
    assert "Packages planned: src, usb_shared, usb_linux, usb_stick" in result.output


def test_forge_validate_cli_reports_config_failures(tmp_path, monkeypatch):
    config_path = tmp_path / "bad.toml"
    config_path.write_text('[artifacts]\narchive_format="rar"\n[sticks.blue]\ndevice_path="/dev/blue"\npurpose="test"\n')
    monkeypatch.setenv("SUF_FORGE_CONFIG", str(config_path))
    result = CliRunner().invoke(forge_app, ["validate"])
    assert result.exit_code == 1
    assert "Forge validation:" in result.output
    assert "Result: FAILED" in result.output
    assert "artifacts.archive_format" in result.output


def test_forge_inspect_cli_uses_expanded_output(tmp_path, monkeypatch):
    config_path = tmp_path / "suf.toml"
    config_path.write_text('[artifacts]\noutput_dir="out"\n[sticks.blue]\ndevice_path="/dev/blue"\npurpose="test"\n[forge.scripts.open]\ntype="atomic"\ntool="stick"\ncommand="mount"\nhelp="open"\nstick_id="blue"\n')
    monkeypatch.setenv("SUF_FORGE_CONFIG", str(config_path))
    result = CliRunner().invoke(forge_app, ["inspect"])
    assert result.exit_code == 0
    assert f"Config file: {config_path}" in result.output
    assert "Forge inspection:" in result.output
    assert "- open: stick mount target=blue args=(none)" in result.output
    assert "Scripts generated: open" in result.output


def _load_e2e_common_module():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "e2e" / "common.py"
    spec = importlib.util.spec_from_file_location("e2e_common_for_unit_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_e2e_confirm_device_answers_matches_wipe_stick_prompt():
    common = _load_e2e_common_module()
    device_path = "/dev/disk/by-id/test"

    [(pattern, response)] = common.confirm_device_answers(device_path)

    assert re.search(pattern, f"Type the exact path to continue: {device_path}")
    assert response == device_path


def test_e2e_yes_answer_matches_vault_wipe_prompt_with_context():
    common = _load_e2e_common_module()

    answers = dict(common.yes_answer())
    yes_pattern = next(pattern for pattern, response in common.yes_answer() if response == "YES")

    assert answers[r"Proceed with .*\? \[y/N\]:"] == "y"
    assert re.search(yes_pattern, "Type YES to continue wiping vault green-test1-vault::")
    assert re.search(yes_pattern, "Type YES to continue:")


def test_e2e_scenarios_refuse_placeholder_configuration():
    common = _load_e2e_common_module()
    cfg = common.ScenarioConfig(
        stick_id="green",
        device_path="/dev/disk/by-id/REPLACE_ME",
        passphrase="REPLACE_ME",
    )

    with pytest.raises(SystemExit) as exc:
        common.require_operator_ready(cfg, ["device_path", "passphrase"])

    message = str(exc.value)
    assert "E2E scenario is not configured" in message
    assert "device_path" in message
    assert "passphrase" in message
    assert "SUF_E2E_*" in message


def test_e2e_scenarios_accept_environment_overrides(monkeypatch):
    common = _load_e2e_common_module()
    monkeypatch.setenv("SUF_E2E_DEVICE_PATH", "/dev/disk/by-id/test-stick")

    cfg = common.ScenarioConfig(
        stick_id="green",
        device_path=common.env_value("SUF_E2E_DEVICE_PATH", "/dev/disk/by-id/REPLACE_ME") or "",
        passphrase="real-passphrase-for-test",
    )

    common.require_operator_ready(cfg, ["device_path", "passphrase"])
    assert cfg.device_path == "/dev/disk/by-id/test-stick"



def test_e2e_vault_scenarios_mount_stick_before_vault_create():
    root = Path(__file__).resolve().parents[1] / "e2e"
    for name in ["scenario_vault_lifecycle.py", "scenario_full_e2e.py"]:
        text = (root / name).read_text(encoding="utf-8")
        stick_mount = 'build_command(cfg, "stick", "mount"'
        vault_create = '"vault",\n            "create"'

        assert stick_mount in text, name
        assert vault_create in text, name
        assert text.index(stick_mount) < text.index(vault_create), name


def test_e2e_vault_mount_uses_vault_passphrase_only():
    root = Path(__file__).resolve().parents[1] / "e2e"
    for name in ["scenario_vault_lifecycle.py", "scenario_full_e2e.py"]:
        text = (root / name).read_text(encoding="utf-8")
        vault_mount = text[text.index('"vault",\n            "mount"') :]

        assert 'passphrases=[cfg.vault_passphrase or ""]' in vault_mount
        assert 'passphrases=[cfg.passphrase or ""]' not in vault_mount




def test_wipe_cli_verbose_streams_vault_progress(monkeypatch, tmp_path):
    from typer.testing import CliRunner
    from wipe.cli import app as wipe_app

    mount = tmp_path / "blue-stick"
    vault_dir = mount / "personal"
    vault_dir.mkdir(parents=True)
    (vault_dir / "personal.img").write_text("x")

    monkeypatch.setattr("usb_wipe.service.is_mounted", lambda path: str(path) == str(mount))
    monkeypatch.setattr("usb_wipe.service.prompt_text", lambda message: "YES")
    monkeypatch.setattr("usb_wipe.service.mapper_exists", lambda name: False)

    result = CliRunner().invoke(
        wipe_app,
        ["vault", "--media-id", "blue", "--mount", str(mount), "--vault", "personal", "--full", "-V"],
    )

    assert result.exit_code == 0
    assert "[1/3] Ensuring vault mount is not active" in result.output
    assert "[3/3] Executing destructive wipe" in result.output

def test_e2e_default_vault_size_is_small():
    common = _load_e2e_common_module()

    assert common.E2E_DEFAULT_VAULT_SIZE == "64M"
    assert common.parse_size_bytes(common.E2E_DEFAULT_VAULT_SIZE) == 64 * 1024 * 1024


def test_e2e_vault_full_wipe_is_limited_to_tiny_vaults():
    common = _load_e2e_common_module()
    cfg = common.ScenarioConfig(stick_id="green", device_path="/dev/test")

    tiny_args = common.e2e_vault_wipe_args(cfg, "test1", "8M")
    default_args = common.e2e_vault_wipe_args(cfg, "test1", common.E2E_DEFAULT_VAULT_SIZE)

    assert "--full" in tiny_args
    assert "--fast" not in tiny_args
    assert "--dry-run" not in tiny_args
    assert "--full" not in default_args
    assert "--fast" in default_args
    assert "--dry-run" not in default_args
    assert default_args[-1] == "-V"



def test_e2e_vault_fast_wipe_requires_volume_at_least_fast_span():
    common = _load_e2e_common_module()

    assert common.E2E_FAST_WIPE_MIN_BYTES == common.E2E_FULL_WIPE_MAX_BYTES
    assert common.parse_size_bytes("64M") >= common.E2E_FAST_WIPE_MIN_BYTES


def test_e2e_vault_cleanup_uses_size_aware_wipe_args():
    root = Path(__file__).resolve().parents[1] / "e2e"
    for name in ["scenario_vault_lifecycle.py", "scenario_full_e2e.py"]:
        text = (root / name).read_text(encoding="utf-8")
        assert "base_config()" in text
        assert "e2e_vault_wipe_args(cfg, vault, vault_size)" in text
        assert 'step(7, "Wipe vault container files")' in text

def _make_fake_package_bin(tmp_path: Path, monkeypatch) -> Path:
    bin_dir = tmp_path / "dist" / "suf" / "bin"
    bin_dir.mkdir(parents=True)
    for name in ["stick", "vault", "wipe"]:
        path = bin_dir / name
        path.write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
        path.chmod(0o755)
    monkeypatch.setenv("SUF_E2E_TOOL_DIR", str(bin_dir))
    return bin_dir




def test_e2e_smoke_runs_real_battlefield_commands():
    text = (Path(__file__).resolve().parents[1] / "e2e" / "scenario_smoke.py").read_text(encoding="utf-8")

    assert "--help" not in text
    assert "--status" not in text
    assert "--dry-run" not in text
    assert 'build_command(cfg, "wipe", "stick"' in text
    assert 'build_command(cfg, "stick", "create"' in text
    assert 'build_command(cfg, "stick", "mount"' in text
    assert 'build_command(cfg, "stick", "unmount"' in text
    assert "require_operator_ready" in text
    assert "confirm_device_answers" in text


def test_e2e_runner_manual_output():
    from tools.e2e_runner import app as e2e_app

    result = CliRunner().invoke(e2e_app, ["e2e-fresh-stick", "--manual"])

    assert result.exit_code == 0
    assert "E2E manual procedure: e2e-fresh-stick" in result.output
    assert "SUF_E2E_DEVICE_PATH" in result.output


def test_e2e_runner_executes_selected_scenario(tmp_path, monkeypatch):
    from tools import e2e_runner

    calls = []

    class Result:
        returncode = 0

    _make_fake_package_bin(tmp_path, monkeypatch)
    monkeypatch.setenv("SUF_E2E_DEVICE_PATH", "/dev/disk/by-id/test")
    monkeypatch.setenv("SUF_E2E_STICK_PASSPHRASE", "test-passphrase")

    def fake_run(command, cwd, text, env):
        calls.append((command, cwd, text, env.get("PYTHONUNBUFFERED")))
        return Result()

    monkeypatch.setattr(e2e_runner.subprocess, "run", fake_run)
    env_file = tmp_path / "e2e.env"
    env_file.write_text("SUF_E2E_DEVICE_PATH=/dev/disk/by-id/test\nSUF_E2E_STICK_PASSPHRASE=test-passphrase\n", encoding="utf-8")

    result = CliRunner().invoke(e2e_runner.app, ["e2e-fresh-stick", "--env-file", str(env_file)])

    assert result.exit_code == 0
    assert "E2E scenario: e2e-fresh-stick" in result.output
    assert "Packaged tools:" in result.output
    assert "Output streams live below" in result.output
    assert calls == [
        (
            [sys.executable, "-u", str(e2e_runner.ROOT / "tests" / "e2e" / "scenario_fresh_stick.py")],
            e2e_runner.ROOT,
            True,
            "1",
        )
    ]


def test_e2e_runner_loads_env_file(tmp_path, monkeypatch):
    from tools import e2e_runner

    _make_fake_package_bin(tmp_path, monkeypatch)
    env_file = tmp_path / "e2e.env"
    env_file.write_text("SUF_E2E_DEVICE_PATH=/dev/disk/by-id/test\nSUF_E2E_STICK_ID=blue\n", encoding="utf-8")
    monkeypatch.delenv("SUF_E2E_DEVICE_PATH", raising=False)
    loaded = e2e_runner._load_env_file(env_file)

    assert loaded == ["SUF_E2E_DEVICE_PATH", "SUF_E2E_STICK_ID"]
    assert os.environ["SUF_E2E_DEVICE_PATH"] == "/dev/disk/by-id/test"


def test_e2e_runner_reports_configuration_help(tmp_path, monkeypatch):
    from tools import e2e_runner

    _make_fake_package_bin(tmp_path, monkeypatch)
    calls = []
    monkeypatch.delenv("SUF_E2E_DEVICE_PATH", raising=False)
    monkeypatch.delenv("SUF_E2E_STICK_PASSPHRASE", raising=False)
    monkeypatch.delenv("SUF_E2E_VAULT_PASSPHRASE", raising=False)
    monkeypatch.setattr(e2e_runner.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    result = CliRunner().invoke(e2e_runner.app, ["e2e-full"])

    assert result.exit_code == 1
    assert "E2E config not found" in result.output
    assert "make e2e-config" in result.output
    assert "tests/e2e/e2e.env" in result.output
    assert calls == []



def test_e2e_runner_loads_env_and_streams_live(tmp_path, monkeypatch):
    from tools import e2e_runner

    _make_fake_package_bin(tmp_path, monkeypatch)
    env_file = tmp_path / "e2e.env"
    env_file.write_text(
        "SUF_E2E_DEVICE_PATH=/dev/disk/by-id/live-test\n"
        "SUF_E2E_STICK_PASSPHRASE=test-passphrase\n",
        encoding="utf-8",
    )
    calls = []

    class Result:
        returncode = 0

    def fake_run(command, cwd, text, env):
        calls.append((command, cwd, text, env["PYTHONUNBUFFERED"]))
        return Result()

    monkeypatch.delenv("SUF_E2E_DEVICE_PATH", raising=False)
    monkeypatch.delenv("SUF_E2E_STICK_PASSPHRASE", raising=False)
    monkeypatch.setattr(e2e_runner.subprocess, "run", fake_run)

    result = CliRunner().invoke(e2e_runner.app, ["e2e-fresh-stick", "--env-file", str(env_file)])

    assert result.exit_code == 0
    assert "Env file:" in result.output
    assert "2 values loaded" in result.output
    assert "Device path: /dev/disk/by-id/live-test" in result.output
    assert calls[0][0][1] == "-u"
    assert calls[0][3] == "1"


def test_e2e_interactive_run_prints_heartbeat_on_idle(monkeypatch, capsys):
    common = _load_e2e_common_module()

    class FakeChild:
        logfile_read = None
        timeout = 0
        exitstatus = 0
        signalstatus = None

        def __init__(self):
            self._results = [1, 0]
            self.closed = False

        def expect(self, _patterns):
            return self._results.pop(0)

        def close(self, force=False):
            self.closed = True

        def isalive(self):
            return not self.closed

        def sendintr(self):
            self.closed = True

    fake_child = FakeChild()
    times = iter([0.0, 1.0, 1.1, 1.2, 1.3])
    monkeypatch.setattr(common, "spawn_command", lambda command, timeout: fake_child)
    monkeypatch.setattr(common.time, "monotonic", lambda: next(times))

    common.interactive_run(["dummy"], timeout=3, heartbeat=1)

    output = capsys.readouterr().out
    assert "Still running" in output
    assert "dummy" in output


def test_e2e_interactive_run_times_out_and_closes_child(monkeypatch):
    common = _load_e2e_common_module()

    class FakeChild:
        logfile_read = None
        timeout = 0
        exitstatus = None
        signalstatus = None

        def __init__(self):
            self.closed_forcefully = False
            self.interrupted = False

        def expect(self, _patterns, timeout=None):
            if timeout is not None:
                raise common.pexpect.TIMEOUT("still running")
            return 1

        def close(self, force=False):
            self.closed_forcefully = force

        def isalive(self):
            return True

        def sendintr(self):
            self.interrupted = True

    fake_child = FakeChild()
    times = iter([0.0, 1.0, 1.1, 1.2, 2.1])
    monkeypatch.setattr(common, "spawn_command", lambda command, timeout: fake_child)
    monkeypatch.setattr(common.time, "monotonic", lambda: next(times))

    with pytest.raises(SystemExit) as exc:
        common.interactive_run(["dummy"], timeout=2, heartbeat=1)

    assert "Command timed out after 2s" in str(exc.value)
    assert fake_child.interrupted is True
    assert fake_child.closed_forcefully is True

def test_packaged_root_detects_executable_lib_runtime(tmp_path, monkeypatch):
    package_root = tmp_path / "suf"
    runtime = package_root / "lib" / "forge"
    (package_root / "config").mkdir(parents=True)
    (package_root / "config" / "forge.toml").write_text("[artifacts]\n", encoding="utf-8")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("binary placeholder", encoding="utf-8")

    monkeypatch.delenv("USB_FACTORY_PACKAGE_ROOT", raising=False)
    monkeypatch.setattr(sys, "executable", str(runtime))

    assert _packaged_root() == package_root.resolve()


def test_repo_root_resolution_error_is_actionable(monkeypatch):
    import usb_forge.packager as packager

    monkeypatch.setattr(packager, "__file__", "/x.py")

    with pytest.raises(RuntimeError) as exc:
        _repo_root_from_source()

    assert "USB_FACTORY_PACKAGE_ROOT" in str(exc.value)
