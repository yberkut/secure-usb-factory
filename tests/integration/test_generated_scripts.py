from __future__ import annotations

import subprocess
import tomllib

from tests.integration.package_support import PACKAGE, package_env, run_completion


def _configured_green_device_path() -> str:
    data = tomllib.loads((PACKAGE / "config" / "forge.toml").read_text(encoding="utf-8"))
    return str(data["sticks"]["green"]["device_path"])


def _run_script_help(name: str, *, force_color: bool = False, no_color: bool = False) -> subprocess.CompletedProcess[str]:
    env = package_env()
    if force_color:
        env["CLICOLOR_FORCE"] = "1"
    if no_color:
        env["NO_COLOR"] = "1"
    return subprocess.run(
        [str(PACKAGE / "generated-scripts" / name), "--help"],
        cwd=PACKAGE,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        timeout=30,
        check=True,
    )


def test_generated_script_completion_works(generated_scripts: None) -> None:
    script_completion = run_completion([
        str(PACKAGE / "generated-scripts" / "green-stick-mount"),
        "--show-completion",
        "bash",
    ])
    assert "_stick_completion" in script_completion.stdout


def test_generated_atomic_script_help_is_specific(generated_scripts: None) -> None:
    result = _run_script_help("green-vault-personal-mount")
    assert "green-vault-personal-mount" in result.stdout
    assert "Purpose:" in result.stdout
    assert "Mount personal on the configured green stick." in result.stdout
    assert "Bound target:" in result.stdout
    assert "Media ID: green" in result.stdout
    assert "Vault:    personal" in result.stdout
    assert "Runs:" in result.stdout
    assert "vault mount --media-id green --mount /media/green-stick --vault personal" in result.stdout
    assert "Usage:" in result.stdout




def test_generated_vault_unmount_script_does_not_pass_mount(generated_scripts: None) -> None:
    script = PACKAGE / "generated-scripts" / "green-vault-personal-unmount"
    text = script.read_text(encoding="utf-8")
    assert "vault unmount --media-id green --vault personal" in _run_script_help("green-vault-personal-unmount").stdout
    assert "'unmount' '--media-id' 'green' '--vault' 'personal'" in text
    assert "'unmount' '--media-id' 'green' '--mount'" not in text


def test_generated_destructive_script_help_warns(generated_scripts: None) -> None:
    device_path = _configured_green_device_path()
    result = _run_script_help("green-stick-wipe-fast")
    assert "WARNING:" in result.stdout
    assert "destructive wipe operation" in result.stdout
    assert f"Device:   {device_path}" in result.stdout
    assert f"wipe stick --path {device_path} --fast" in result.stdout


def test_generated_scenario_script_help_is_specific(generated_scripts: None) -> None:
    result = _run_script_help("green-vault-personal-open-session")
    assert "green-vault-personal-open-session" in result.stdout
    assert "Scenario:" in result.stdout
    assert "Steps: 2" in result.stdout
    assert "Stop on error: YES" in result.stdout
    assert "Equivalent commands:" in result.stdout


def test_generated_script_help_can_be_colorized(generated_scripts: None) -> None:
    result = _run_script_help("green-vault-personal-mount", force_color=True)
    assert "\x1b[" in result.stdout


def test_generated_script_help_honors_no_color(generated_scripts: None) -> None:
    result = _run_script_help("green-vault-personal-mount", force_color=True, no_color=True)
    assert "\x1b[" not in result.stdout


def test_generated_panic_destroy_scenario_is_configured(generated_scripts: None) -> None:
    result = _run_script_help("green-panic-destroy-all-fast")
    assert "green-panic-destroy-all-fast" in result.stdout
    assert "WARNING:" in result.stdout
    assert "destructive wipe operations" in result.stdout
    assert "Steps: 3" in result.stdout
    assert "'vault' '--media-id' 'green' '--mount' '/media/green-stick' '--vault' 'personal' '--fast' '--panic' '-V'" in result.stdout
    assert "'vault' '--media-id' 'green' '--mount' '/media/green-stick' '--vault' 'work' '--fast' '--panic' '-V'" in result.stdout
    assert "'stick' '--path'" in result.stdout
    assert "'--fast' '--panic' '-V'" in result.stdout

    script = PACKAGE / "generated-scripts" / "green-panic-destroy-all-fast"
    text = script.read_text(encoding="utf-8")
    assert "'vault' '--media-id' 'green' '--mount' '/media/green-stick' '--vault' 'personal' '--fast' '--panic' '-V'" in text
    assert "'vault' '--media-id' 'green' '--mount' '/media/green-stick' '--vault' 'work' '--fast' '--panic' '-V'" in text
    assert "'stick' '--path'" in text
    assert "'--fast' '--panic' '-V'" in text


def test_generated_recreate_confirmed_scenario_is_configured(generated_scripts: None) -> None:
    result = _run_script_help("green-stick-recreate-with-confirmation")
    assert "green-stick-recreate-with-confirmation" in result.stdout
    assert "WARNING:" in result.stdout
    assert "Steps: 2" in result.stdout
    assert "'stick' '--path'" in result.stdout
    assert "'--fast' '-V'" in result.stdout
    assert "'create' '--id' 'green' '--path'" in result.stdout
    assert "'-V'" in result.stdout

    script = PACKAGE / "generated-scripts" / "green-stick-recreate-with-confirmation"
    text = script.read_text(encoding="utf-8")
    assert "'stick' '--path'" in text
    assert "'--fast' '-V'" in text
    assert "'create' '--id' 'green' '--path'" in text
