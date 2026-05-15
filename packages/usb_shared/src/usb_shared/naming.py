from __future__ import annotations

from pathlib import Path

from .models import StickNames, VaultNames
from .validation import validate_stick_id, validate_vault_basename

MOUNT_ROOT = Path("/media")


def derive_stick_names(stick_id: str) -> StickNames:
    stick_id = validate_stick_id(stick_id)
    stick_name = f"{stick_id}-stick"
    return StickNames(
        stick_id=stick_id,
        stick_name=stick_name,
        stick_mapper=f"map-{stick_name}",
        stick_mount=MOUNT_ROOT / stick_name,
        stick_fs_label=stick_name.replace("-", "_"),
    )


def derive_vault_names(stick_id: str, vault: str) -> VaultNames:
    stick_id = validate_stick_id(stick_id)
    vault = validate_vault_basename(vault)
    stick = derive_stick_names(stick_id)
    vault_name = f"{stick_id}-{vault}-vault"
    vault_dir = stick.stick_mount / vault
    return VaultNames(
        stick_id=stick_id,
        vault=vault,
        stick_name=stick.stick_name,
        vault_name=vault_name,
        vault_mapper=f"map-{vault_name}",
        vault_mount=MOUNT_ROOT / vault_name,
        vault_fs_label=vault_name.replace("-", "_"),
        vault_dir=vault_dir,
        vault_image=vault_dir / f"{vault}.img",
        secret_path=vault_dir / f"{vault}.kdbx",
    )
