from __future__ import annotations

from .schema import ScenarioScriptConfig, SufConfig
from usb_shared.errors import ValidationError
from usb_shared.validation import validate_script_name, validate_stick_id, validate_vault_basename


def validate_config(config: SufConfig) -> None:
    if not config.sticks:
        raise ValidationError("At least one stick must be defined.")

    if config.package.lib_layout not in {"tree", "executable"}:
        raise ValidationError("package.lib_layout must be 'tree' or 'executable'.")

    if config.artifacts.archive_format not in {"none", "zip"}:
        raise ValidationError("artifacts.archive_format must be 'none' or 'zip'.")

    allowed_package_tools = {"stick", "vault", "wipe", "forge"}
    unknown_package_tools = sorted(set(config.package.tools) - allowed_package_tools)
    if unknown_package_tools:
        raise ValidationError(f"package.tools contains unknown packaged tools: {', '.join(unknown_package_tools)}")
    if len(config.package.tools) != len(set(config.package.tools)):
        raise ValidationError("package.tools must not contain duplicates.")

    for stick_id, stick in config.sticks.items():
        validate_stick_id(stick_id)
        if not stick.device_path:
            raise ValidationError(f"Stick {stick_id} has empty device_path.")
        for vault_name, vault in stick.vaults.items():
            validate_vault_basename(vault_name)
            if not vault.size:
                raise ValidationError(f"Vault {stick_id}/{vault_name} has empty size.")

    for script_id, script in config.forge.scripts.items():
        validate_script_name(script_id)
        if script.name != script_id:
            raise ValidationError(f"Script name mismatch: {script_id} != {script.name}")
        if isinstance(script, ScenarioScriptConfig) and not script.steps:
            raise ValidationError(f"Scenario script {script_id} must contain at least one step.")
