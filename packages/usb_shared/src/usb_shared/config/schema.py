from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

LibraryLayout = Literal["tree", "executable"]
ArchiveFormat = Literal["none", "zip", "tar.gz"]
PackagedToolName = Literal["stick", "vault", "wipe", "forge"]
ScriptType = Literal["atomic", "scenario"]
ToolName = Literal["stick", "vault", "wipe", "forge"]
StepKind = Literal["cli", "entrypoint", "python"]


@dataclass(frozen=True)
class ArtifactsConfig:
    output_dir: str = "build/scripts"
    include_manifest: bool = True
    archive_format: ArchiveFormat = "none"


@dataclass(frozen=True)
class PackageConfig:
    lib_layout: LibraryLayout = "tree"
    tools: list[PackagedToolName] = field(default_factory=lambda: ["stick", "vault", "wipe", "forge"])


@dataclass(frozen=True)
class VaultConfig:
    size: str
    purpose: str


@dataclass(frozen=True)
class StickConfig:
    device_path: str
    purpose: str
    vaults: dict[str, VaultConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class AtomicScriptConfig:
    name: str
    type: ScriptType
    tool: ToolName
    command: str
    help: str
    stick_id: str | None = None
    vault: str | None = None
    fixed_args: list[str] = field(default_factory=list)
    disabled: bool = False


@dataclass(frozen=True)
class ScenarioStepConfig:
    kind: StepKind
    tool: ToolName | None = None
    command: list[str] = field(default_factory=list)
    module: str | None = None
    callable: str | None = None
    args: list[str] = field(default_factory=list)
    path: str | None = None
    stick_id: str | None = None
    vault: str | None = None
    fixed_args: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScenarioScriptConfig:
    name: str
    type: ScriptType
    help: str
    stop_on_error: bool = True
    steps: list[ScenarioStepConfig] = field(default_factory=list)
    disabled: bool = False


ScriptConfig = AtomicScriptConfig | ScenarioScriptConfig


@dataclass(frozen=True)
class ForgeConfig:
    scripts: dict[str, ScriptConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class SufConfig:
    artifacts: ArtifactsConfig
    sticks: dict[str, StickConfig]
    forge: ForgeConfig
    package: PackageConfig = field(default_factory=PackageConfig)
