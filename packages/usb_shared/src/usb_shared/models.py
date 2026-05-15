from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class StickIdentity:
    stick_id: str


@dataclass(frozen=True)
class VaultIdentity:
    stick_id: str
    vault: str


@dataclass(frozen=True)
class StickNames:
    stick_id: str
    stick_name: str
    stick_mapper: str
    stick_mount: Path
    stick_fs_label: str


@dataclass(frozen=True)
class VaultNames:
    stick_id: str
    vault: str
    stick_name: str
    vault_name: str
    vault_mapper: str
    vault_mount: Path
    vault_fs_label: str
    vault_dir: Path
    vault_image: Path
    secret_path: Path


@dataclass
class CommandResult:
    ok: bool
    exit_code: int = 0
    lines: list[str] = field(default_factory=list)


@dataclass
class PlanStep:
    text: str


@dataclass
class Plan:
    title: str
    steps: list[PlanStep] = field(default_factory=list)


