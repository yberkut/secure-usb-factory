from __future__ import annotations

from pathlib import Path
import tomllib

from .schema import (
    ArtifactsConfig,
    AtomicScriptConfig,
    ForgeConfig,
    PackageConfig,
    ScenarioScriptConfig,
    ScenarioStepConfig,
    StickConfig,
    SufConfig,
    VaultConfig,
)


def _load_vaults(raw_vaults: dict) -> dict[str, VaultConfig]:
    return {
        vault_name: VaultConfig(size=raw["size"], purpose=raw["purpose"])
        for vault_name, raw in raw_vaults.items()
    }


def _load_sticks(raw_sticks: dict) -> dict[str, StickConfig]:
    return {
        stick_id: StickConfig(
            device_path=raw["device_path"],
            purpose=raw.get("purpose", ""),
            vaults=_load_vaults(raw.get("vaults", {})),
        )
        for stick_id, raw in raw_sticks.items()
    }


def _load_steps(raw_steps: list[dict]) -> list[ScenarioStepConfig]:
    return [
        ScenarioStepConfig(
            kind=step["kind"],
            tool=step.get("tool"),
            command=step.get("command", []),
            module=step.get("module"),
            callable=step.get("callable"),
            args=step.get("args", []),
            path=step.get("path"),
            stick_id=step.get("stick_id"),
            vault=step.get("vault"),
            fixed_args=step.get("fixed_args", []),
        )
        for step in raw_steps
    ]


def _load_script(script_id: str, raw: dict):
    script_type = raw["type"]
    if script_type == "atomic":
        return AtomicScriptConfig(
            name=script_id,
            type="atomic",
            tool=raw["tool"],
            command=raw["command"],
            help=raw["help"],
            stick_id=raw.get("stick_id"),
            vault=raw.get("vault"),
            fixed_args=raw.get("fixed_args", []),
            disabled=raw.get("disabled", False),
        )
    if script_type == "scenario":
        return ScenarioScriptConfig(
            name=script_id,
            type="scenario",
            help=raw["help"],
            stop_on_error=raw.get("stop_on_error", True),
            steps=_load_steps(raw.get("steps", [])),
            disabled=raw.get("disabled", False),
        )
    raise ValueError(f"Unknown script type: {script_type}")


def load_config(path: str | Path = "suf.toml") -> SufConfig:
    with Path(path).open("rb") as fh:
        raw = tomllib.load(fh)

    artifacts = ArtifactsConfig(**raw.get("artifacts", {}))
    package = PackageConfig(**raw.get("package", {}))
    sticks = _load_sticks(raw.get("sticks", {}))
    raw_forge = raw.get("forge", {})
    scripts = {
        script_id: _load_script(script_id, script_raw)
        for script_id, script_raw in raw_forge.get("scripts", {}).items()
    }
    return SufConfig(artifacts=artifacts, package=package, sticks=sticks, forge=ForgeConfig(scripts=scripts))
