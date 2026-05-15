from __future__ import annotations

from collections.abc import Sequence

from usb_shared.config.schema import AtomicScriptConfig, ScenarioStepConfig, ScenarioScriptConfig, SufConfig
from usb_shared.config.validate import validate_config
from usb_shared.errors import ValidationError
from usb_shared.validation import validate_stick_id, validate_vault_basename

ALLOWED_COMMANDS: dict[str, set[tuple[str, ...]]] = {
    "stick": {("create",), ("mount",), ("unmount",)},
    "vault": {("create",), ("mount",), ("unmount",)},
    "wipe": {("stick",), ("vault",), ("dir",), ("file",)},
    "forge": {("validate",), ("inspect",), ("generate",)},
}

_VALUE_OPTIONS = {
    "--id",
    "--stick-id",
    "--media-id",
    "--mount",
    "--path",
    "--vault",
    "--size",
    "--purpose",
}


def _command_tokens(command: str) -> tuple[str, ...]:
    return tuple(part for part in command.split() if part)


def _option_value(args: Sequence[str], *names: str) -> str | None:
    for index, arg in enumerate(args):
        if arg in names:
            if index + 1 >= len(args):
                raise ValidationError(f"Option requires a value: {arg}")
            return args[index + 1]
        for name in names:
            prefix = f"{name}="
            if arg.startswith(prefix):
                return arg[len(prefix):]
    return None


def _has_option(args: Sequence[str], *names: str) -> bool:
    return _option_value(args, *names) is not None or any(arg in names for arg in args)


def _validate_option_values(args: Sequence[str], context: str) -> None:
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg in _VALUE_OPTIONS:
            if index + 1 >= len(args):
                raise ValidationError(f"{context} option requires a value: {arg}")
            skip_next = True
        elif any(arg.startswith(f"{option}=") for option in _VALUE_OPTIONS):
            if arg.endswith("="):
                raise ValidationError(f"{context} option requires a value: {arg.split('=', 1)[0]}")


def _forbid_fixed_args(script_id: str, script: AtomicScriptConfig, *options: str) -> None:
    for option in options:
        if _has_option(script.fixed_args, option):
            raise ValidationError(
                f"Script {script_id} must not set {option} in fixed_args; "
                "forge derives bound target arguments from stick_id/vault config."
            )


def _combined_step_args(step: ScenarioStepConfig) -> list[str]:
    return [*step.args, *step.fixed_args]


def _forbid_step_args(step: ScenarioStepConfig, *options: str) -> None:
    args = _combined_step_args(step)
    for option in options:
        if _has_option(args, option):
            raise ValidationError(
                f"Scenario step must not set {option} in args/fixed_args when structured target fields are used."
            )


def validate_generation_inputs(config: SufConfig) -> None:
    validate_config(config)
    for script_id, script in config.forge.scripts.items():
        if isinstance(script, AtomicScriptConfig):
            _validate_atomic_script(config, script_id, script)
        if isinstance(script, ScenarioScriptConfig):
            for step in script.steps:
                _validate_step(config, step)


def _validate_atomic_script(config: SufConfig, script_id: str, script: AtomicScriptConfig) -> None:
    command_tokens = _command_tokens(script.command)
    allowed = ALLOWED_COMMANDS.get(script.tool)
    if allowed is None or (allowed and command_tokens not in allowed):
        raise ValidationError(
            f"Invalid atomic script command: script={script_id} tool={script.tool} command={script.command}"
        )

    _validate_option_values(script.fixed_args, f"Script {script_id} fixed_args")

    if script.stick_id is not None:
        validate_stick_id(script.stick_id)
        if script.stick_id not in config.sticks:
            raise ValidationError(f"Unknown Stick ID in script {script_id}: {script.stick_id}")

    if script.vault is not None:
        validate_vault_basename(script.vault)
        if script.stick_id is None:
            raise ValidationError(f"Script {script_id} defines vault without stick_id.")
        if script.vault not in config.sticks[script.stick_id].vaults:
            raise ValidationError(f"Unknown vault reference: stick_id={script.stick_id} vault={script.vault}")

    if script.tool == "stick":
        if script.stick_id is None:
            raise ValidationError(f"Stick script {script_id} requires stick_id.")
        _forbid_fixed_args(script_id, script, "--id", "--stick-id")
        if command_tokens in {("create",), ("mount",)}:
            _forbid_fixed_args(script_id, script, "--path")
    elif script.tool == "vault":
        if script.stick_id is None or script.vault is None:
            raise ValidationError(f"Vault script {script_id} requires stick_id and vault.")
        _forbid_fixed_args(script_id, script, "--media-id", "--stick-id", "--mount", "--vault")
        if command_tokens == ("create",):
            _forbid_fixed_args(script_id, script, "--size", "--purpose")
    elif script.tool == "wipe":
        if command_tokens == ("stick",):
            has_explicit_path = _has_option(script.fixed_args, "--path")
            if script.stick_id is None and not has_explicit_path:
                raise ValidationError(f"Wipe script {script_id} requires stick_id or explicit --path for wipe stick.")
            if script.stick_id is not None:
                _forbid_fixed_args(script_id, script, "--path")
        elif command_tokens == ("vault",):
            if script.stick_id is None or script.vault is None:
                raise ValidationError(f"Wipe script {script_id} requires stick_id and vault for wipe vault.")
            _forbid_fixed_args(script_id, script, "--media-id", "--stick-id", "--mount", "--vault")
        elif command_tokens in {("dir",), ("file",)}:
            if not _has_option(script.fixed_args, "--path"):
                raise ValidationError(f"Wipe script {script_id} requires fixed_args including --path for wipe {command_tokens[0]}.")


def _validate_step(config: SufConfig, step: ScenarioStepConfig) -> None:
    _validate_option_values(step.args, "Scenario step args")
    _validate_option_values(step.fixed_args, "Scenario step fixed_args")
    if step.kind == "cli":
        if step.tool is None:
            raise ValidationError("CLI scenario step requires tool.")
        if not step.command:
            raise ValidationError("CLI scenario step requires command tokens.")
        allowed = ALLOWED_COMMANDS.get(step.tool)
        command_tokens = tuple(step.command)
        if allowed is None or (allowed and command_tokens not in allowed):
            raise ValidationError(f"Invalid scenario step command: tool={step.tool} command={' '.join(step.command)}")
        _validate_cli_step_references(config, step)
    elif step.kind == "entrypoint":
        if not step.module or not step.callable:
            raise ValidationError("Entrypoint step requires module and callable.")
    elif step.kind == "python":
        if not step.path:
            raise ValidationError("Python step requires path.")
    else:
        raise ValidationError(f"Unknown scenario step kind: {step.kind}")


def _validate_cli_step_references(config: SufConfig, step: ScenarioStepConfig) -> None:
    args = _combined_step_args(step)

    legacy_stick_id = _option_value(args, "--id", "--stick-id", "--media-id")
    legacy_vault = _option_value(args, "--vault")

    if step.stick_id is not None:
        validate_stick_id(step.stick_id)
        if step.stick_id not in config.sticks:
            raise ValidationError(f"Unknown Stick ID in scenario step: {step.stick_id}")
        _forbid_step_args(step, "--id", "--stick-id", "--media-id")
    elif legacy_stick_id is not None:
        validate_stick_id(legacy_stick_id)
        if legacy_stick_id not in config.sticks:
            raise ValidationError(f"Unknown Stick ID in scenario step: {legacy_stick_id}")

    resolved_stick_id = step.stick_id or legacy_stick_id

    if step.vault is not None:
        validate_vault_basename(step.vault)
        if step.stick_id is None:
            raise ValidationError(f"Scenario step references vault without structured stick_id: {step.vault}")
        if step.vault not in config.sticks[step.stick_id].vaults:
            raise ValidationError(f"Unknown vault reference in scenario step: stick_id={step.stick_id} vault={step.vault}")
        _forbid_step_args(step, "--vault")
    elif legacy_vault is not None:
        validate_vault_basename(legacy_vault)
        if resolved_stick_id is None:
            raise ValidationError(f"Scenario step references vault without media/stick id: {legacy_vault}")
        if legacy_vault not in config.sticks[resolved_stick_id].vaults:
            raise ValidationError(f"Unknown vault reference in scenario step: stick_id={resolved_stick_id} vault={legacy_vault}")

    command_tokens = tuple(step.command)
    if step.tool == "stick" and step.stick_id is not None and command_tokens in {("create",), ("mount",)}:
        _forbid_step_args(step, "--path")
    if step.tool == "vault" and (step.stick_id is not None or step.vault is not None):
        if step.stick_id is None or step.vault is None:
            raise ValidationError("Structured vault scenario step requires stick_id and vault.")
        _forbid_step_args(step, "--mount")
        if command_tokens == ("create",):
            _forbid_step_args(step, "--size", "--purpose")
    if step.tool == "wipe" and command_tokens == ("stick",) and step.stick_id is not None:
        _forbid_step_args(step, "--path")
    if step.tool == "wipe" and command_tokens == ("vault",) and (step.stick_id is not None or step.vault is not None):
        if step.stick_id is None or step.vault is None:
            raise ValidationError("Structured wipe-vault scenario step requires stick_id and vault.")
        _forbid_step_args(step, "--media-id", "--stick-id", "--mount", "--vault")
