from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from shutil import which
from subprocess import CalledProcessError

from usb_shared.execution import make_context
from usb_linux.desktop import open_path
from usb_linux.files import create_sparse_file, ensure_dir, is_writable_path, path_exists
from usb_linux.luks import close_mapper, luks_format, make_ext4_filesystem, mapper_exists, open_mapper, mapper_path
from usb_linux.mounts import ensure_mount_dir, is_mounted, mount_device, remove_empty_dir, unmount_path
from usb_shared.models import CommandResult
from usb_shared.naming import derive_vault_names
from usb_shared.prompts import confirm, pause_for_enter
from usb_shared.subprocesses import format_process_error


class VaultService:
    def _required_commands(self, commands: list[str]) -> str:
        missing = [cmd for cmd in commands if which(cmd) is None]
        return "OK" if not missing else "MISSING: " + ", ".join(missing)

    def _names(self, media_id: str, mount: str, vault: str):
        names = derive_vault_names(media_id, vault)
        vault_dir = Path(mount) / vault
        return replace(
            names,
            vault_dir=vault_dir,
            vault_image=vault_dir / f"{vault}.img",
            secret_path=vault_dir / f"{vault}.kdbx",
        )

    def status(self, media_id: str, mount: str, vault: str, keepass: bool = False) -> CommandResult:
        names = self._names(media_id, mount, vault)
        _ = keepass
        lines = [
            "Vault status:",
            f"Required commands: {self._required_commands(['cryptsetup','mount','umount','sudo'])}",
            f"Media ID:          {media_id}",
            f"Media mount:       {mount}",
            f"Media mounted:     {'YES' if is_mounted(Path(mount)) else 'NO'}",
            f"Vault:             {names.vault_name}",
            f"Vault dir:         {names.vault_dir}",
            f"Vault image:       {names.vault_image}",
            f"Secret path:       {names.secret_path}",
            f"Mapper:            {'OPEN' if mapper_exists(names.vault_mapper) else 'CLOSED'} ({names.vault_mapper})",
            f"Vault mount:       {names.vault_mount}",
            f"Mounted:           {'YES' if is_mounted(names.vault_mount) else 'NO'}",
            f"Ready:             {'YES' if is_mounted(Path(mount)) and path_exists(names.vault_image) else 'NO'}",
        ]
        return CommandResult(ok=True, lines=lines)

    def create_manual(self, media_id: str, mount: str, vault: str, size: str, purpose: str) -> CommandResult:
        names = self._names(media_id, mount, vault)
        lines = [
            "Manual procedure:",
            f"Media ID:          {media_id}",
            f"Media mount:       {mount}",
            f"Vault:             {vault}",
            f"Requested size:    {size}",
            f"Purpose:           {purpose}",
            "1. Create the vault directory if needed",
            "2. Create a sparse image file",
            "3. Format the image as LUKS2",
            "4. Open the mapper",
            "5. Create ext4 filesystem",
            "6. Close the mapper",
            "Equivalent commands:",
            f"$ mkdir -p {names.vault_dir}",
            f"$ truncate -s {size} {names.vault_image}",
            f"$ sudo cryptsetup luksFormat --batch-mode --type luks2 {names.vault_image}",
            f"$ sudo cryptsetup open {names.vault_image} {names.vault_mapper}",
            f"$ sudo mkfs.ext4 -L {names.vault_fs_label} /dev/mapper/{names.vault_mapper}",
            f"$ sudo cryptsetup close {names.vault_mapper}",
            "Interactive notes:",
            "- cryptsetup will ask for a new passphrase",
            "- cryptsetup open will ask for the existing passphrase",
            "- matching .kdbx remains a manual operator step",
        ]
        return CommandResult(ok=True, lines=lines)

    def create(self, media_id: str, mount: str, vault: str, size: str, purpose: str, dry_run: bool = False, verbose: bool = False, logger=None) -> CommandResult:
        names = self._names(media_id, mount, vault)
        ctx = make_context(verbose=verbose, sink=logger)
        lines = self.status(media_id, mount, vault).lines + [
            f"Requested size:    {size}",
            f"Purpose:           {purpose}",
            "Plan:",
            f"1. Ensure vault directory exists: {names.vault_dir}",
            f"2. Create sparse image: {names.vault_image}",
            f"3. Format image as LUKS2 and open mapper: {names.vault_mapper}",
            f"4. Create ext4 filesystem label: {names.vault_fs_label}",
            f"5. Close mapper: {names.vault_mapper}",
            f"6. Leave matching secret manual at: {names.secret_path}",
        ]
        if dry_run:
            lines.extend([
                "Interactive prompts that would appear:",
                "- Proceed with creation confirmation",
                "- Enter new LUKS passphrase",
                "- Repeat new LUKS passphrase",
                "- Enter LUKS passphrase",
                "Equivalent commands:",
                f"$ mkdir -p {names.vault_dir}",
                f"$ truncate -s {size} {names.vault_image}",
                f"$ sudo cryptsetup luksFormat --batch-mode --type luks2 {names.vault_image}",
                f"$ sudo cryptsetup open {names.vault_image} {names.vault_mapper}",
                f"$ sudo mkfs.ext4 -L {names.vault_fs_label} /dev/mapper/{names.vault_mapper}",
                f"$ sudo cryptsetup close {names.vault_mapper}",
                "Dry-run only. No changes were made.",
            ])
            return CommandResult(ok=True, lines=lines)
        if not is_mounted(Path(mount)):
            return CommandResult(ok=False, exit_code=1, lines=[f"Media mount must already be mounted: {mount}"])
        if path_exists(names.vault_image):
            return CommandResult(ok=False, exit_code=1, lines=[f"Vault image already exists: {names.vault_image}"])
        writable_target = names.vault_dir if names.vault_dir.exists() else Path(mount)
        if not is_writable_path(writable_target):
            return CommandResult(
                ok=False,
                exit_code=1,
                lines=lines
                + [
                    f"Media mount is not writable by current user: {mount}",
                    "Fix ownership after mounting, then retry:",
                    f"  sudo chown -R $USER:$USER {mount}",
                    f"  find {mount} -type d -exec chmod 700 {{}} \\;",
                    f"  find {mount} -type f -exec chmod 600 {{}} \\;",
                ],
            )
        if not confirm(f"Proceed with creation for vault: {names.vault_name} ?"):
            return CommandResult(ok=False, exit_code=1, lines=["Cancelled."])
        created_image = False
        opened_mapper = False

        def failure_lines(message: str) -> list[str]:
            cleanup_lines = ["Vault creation failed."]
            if opened_mapper:
                try:
                    close_mapper(names.vault_mapper, ctx=ctx)
                    cleanup_lines.append(f"Closed mapper after failed creation: {names.vault_mapper}")
                except Exception:
                    cleanup_lines.extend([
                        f"Could not close mapper after failed creation: {names.vault_mapper}",
                        "Close it manually if needed.",
                    ])
            if created_image and path_exists(names.vault_image):
                try:
                    names.vault_image.unlink()
                    cleanup_lines.append(f"Removed partial vault image: {names.vault_image}")
                except Exception:
                    cleanup_lines.extend([
                        f"Partial vault image may remain: {names.vault_image}",
                        "Remove it manually if needed.",
                    ])
            return lines + [message] + cleanup_lines

        try:
            ensure_dir(names.vault_dir)
            create_sparse_file(names.vault_image, size, ctx=ctx)
            created_image = True
            if verbose:
                ctx.info(f"Formatting LUKS2 on image: {names.vault_image}")
                ctx.info("Interactive step: Python will ask for the new LUKS passphrase now.")
            luks_format(str(names.vault_image), ctx=ctx)
            if verbose:
                ctx.info(f"Opening mapper: {names.vault_mapper}")
                ctx.info("Interactive step: Python will ask for the existing LUKS passphrase now.")
            open_mapper(str(names.vault_image), names.vault_mapper, ctx=ctx)
            opened_mapper = True
            make_ext4_filesystem(f"/dev/mapper/{names.vault_mapper}", names.vault_fs_label, ctx=ctx)
            close_mapper(names.vault_mapper, ctx=ctx)
            opened_mapper = False
        except CalledProcessError as exc:
            return CommandResult(ok=False, exit_code=1, lines=failure_lines(f"Failed to create vault: {format_process_error(exc)}"))
        except PermissionError as exc:
            return CommandResult(
                ok=False,
                exit_code=1,
                lines=failure_lines(f"Failed to create vault: {exc}")
                + [
                    f"Media mount is not writable by current user: {mount}",
                    "Fix ownership after mounting, then retry:",
                    f"  sudo chown -R $USER:$USER {mount}",
                    f"  find {mount} -type d -exec chmod 700 {{}} \\;",
                    f"  find {mount} -type f -exec chmod 600 {{}} \\;",
                ],
            )
        except Exception as exc:
            return CommandResult(ok=False, exit_code=1, lines=failure_lines(f"Failed to create vault: {exc}"))
        return CommandResult(ok=True, lines=lines + [f"Created vault: {names.vault_name}", f"Expected secret path: {names.secret_path}"])

    def mount_manual(self, media_id: str, mount: str, vault: str, keepass: bool = False) -> CommandResult:
        names = self._names(media_id, mount, vault)
        lines = [
            "Manual procedure:",
            f"Media ID:          {media_id}",
            f"Media mount:       {mount}",
            f"Vault:             {vault}",
            "1. Optionally open the matching KeePassXC database",
            "2. Open the encrypted vault container",
            "3. Create the vault mount directory",
            "4. Mount the mapper",
            "Equivalent commands:",
        ]
        if keepass:
            lines.extend([
                f"$ xdg-open {names.secret_path} || xdg-open {names.vault_dir}",
                f"$ read -r -p 'Press Enter when ready to open {vault}.img...'",
            ])
        lines.extend([
            f"$ sudo cryptsetup open {names.vault_image} {names.vault_mapper}",
            f"$ sudo mkdir -p {names.vault_mount}",
            f"$ sudo mount /dev/mapper/{names.vault_mapper} {names.vault_mount}",
        ])
        return CommandResult(ok=True, lines=lines)

    def mount(self, media_id: str, mount: str, vault: str, keepass: bool = False, dry_run: bool = False, verbose: bool = False, logger=None) -> CommandResult:
        names = self._names(media_id, mount, vault)
        ctx = make_context(verbose=verbose, sink=logger)
        lines = self.status(media_id, mount, vault).lines + [
            "Plan:",
            f"1. Open encrypted image: {names.vault_image}",
            f"2. Ensure mount directory exists: {names.vault_mount}",
            f"3. Mount /dev/mapper/{names.vault_mapper} at {names.vault_mount}",
        ]
        if keepass:
            status_len = len(self.status(media_id, mount, vault).lines)
            lines.insert(status_len, f"Keepass helper:    {names.secret_path}")
            lines.insert(status_len + 1, f"Keepass fallback:  {names.vault_dir}")
            lines.insert(status_len + 2, f"Operator pause:    Press Enter when ready to open {vault}.img...")
        if dry_run:
            prompts = ["Interactive prompts that would appear:"]
            if keepass:
                prompts.append(f"- Press Enter when ready to open {vault}.img...")
            prompts.append("- Enter LUKS passphrase")
            lines.extend(prompts + [
                "Equivalent commands:",
                *([
                    f"$ xdg-open {names.secret_path} || xdg-open {names.vault_dir}",
                    f"$ read -r -p 'Press Enter when ready to open {vault}.img...'",
                ] if keepass else []),
                f"$ sudo cryptsetup open {names.vault_image} {names.vault_mapper}",
                f"$ sudo mkdir -p {names.vault_mount}",
                f"$ sudo mount /dev/mapper/{names.vault_mapper} {names.vault_mount}",
                "Dry-run only. No changes were made.",
            ])
            return CommandResult(ok=True, lines=lines)
        if not is_mounted(Path(mount)):
            return CommandResult(ok=False, exit_code=1, lines=[f"Media mount must already be mounted: {mount}"])
        if not path_exists(names.vault_image):
            return CommandResult(ok=False, exit_code=1, lines=[f"Vault image not found: {names.vault_image}"])
        if keepass:
            target = names.secret_path if path_exists(names.secret_path) else names.vault_dir
            try:
                open_path(target)
            except Exception:
                pass
            pause_for_enter(f"Press Enter when ready to open {vault}.img...")
        try:
            if not mapper_exists(names.vault_mapper):
                if verbose:
                    ctx.info(f"Opening mapper: {names.vault_mapper}")
                    ctx.info("Interactive step: Python will ask for the existing LUKS passphrase now.")
                open_mapper(str(names.vault_image), names.vault_mapper, ctx=ctx)
            ensure_mount_dir(names.vault_mount, ctx=ctx)
            mount_device(str(mapper_path(names.vault_mapper)), names.vault_mount, ctx=ctx)
        except CalledProcessError as exc:
            return CommandResult(ok=False, exit_code=1, lines=lines + [f"Failed to mount vault: {format_process_error(exc)}"])
        except Exception as exc:
            return CommandResult(ok=False, exit_code=1, lines=lines + [f"Failed to mount vault: {exc}"])
        return CommandResult(ok=True, lines=lines + [f"Mounted vault: {names.vault_name}"])

    def unmount_status(self, media_id: str, vault: str) -> CommandResult:
        names = derive_vault_names(media_id, vault)
        lines = [
            "Vault unmount status:",
            f"Media ID:          {media_id}",
            f"Vault:             {names.vault_name}",
            f"Mapper:            {'OPEN' if mapper_exists(names.vault_mapper) else 'CLOSED'} ({names.vault_mapper})",
            f"Vault mount:       {names.vault_mount}",
            f"Mounted:           {'YES' if is_mounted(names.vault_mount) else 'NO'}",
            f"Ready:             {'YES' if is_mounted(names.vault_mount) or mapper_exists(names.vault_mapper) else 'NO'}",
        ]
        return CommandResult(ok=True, lines=lines)

    def unmount_manual(self, media_id: str, vault: str) -> CommandResult:
        names = derive_vault_names(media_id, vault)
        lines = [
            "Manual procedure:",
            f"Media ID:          {media_id}",
            f"Vault:             {vault}",
            "1. Unmount the vault mount path",
            "2. Close the mapper",
            "3. Remove the empty vault mount directory if possible",
            "Equivalent commands:",
            f"$ sudo umount {names.vault_mount}",
            f"$ sudo cryptsetup close {names.vault_mapper}",
            f"$ sudo rmdir {names.vault_mount}",
        ]
        return CommandResult(ok=True, lines=lines)

    def unmount(self, media_id: str, vault: str, dry_run: bool = False, verbose: bool = False, logger=None) -> CommandResult:
        names = derive_vault_names(media_id, vault)
        ctx = make_context(verbose=verbose, sink=logger)
        lines = [
            "Vault unmount status:",
            f"Media ID:          {media_id}",
            f"Vault:             {names.vault_name}",
            f"Mapper:            {'OPEN' if mapper_exists(names.vault_mapper) else 'CLOSED'} ({names.vault_mapper})",
            f"Vault mount:       {names.vault_mount}",
            f"Mounted:           {'YES' if is_mounted(names.vault_mount) else 'NO'}",
            "Plan:",
            f"1. Unmount path: {names.vault_mount}",
            f"2. Close mapper: {names.vault_mapper}",
            f"3. Remove empty mount directory: {names.vault_mount}",
        ]
        if dry_run:
            lines.extend([
                "Equivalent commands:",
                f"$ sudo umount {names.vault_mount}",
                f"$ sudo cryptsetup close {names.vault_mapper}",
                f"$ sudo rmdir {names.vault_mount}",
                "Dry-run only. No changes were made.",
            ])
            return CommandResult(ok=True, lines=lines)
        was_mounted = is_mounted(names.vault_mount)
        was_open = mapper_exists(names.vault_mapper)
        cleanup_lines: list[str] = []
        try:
            if was_mounted:
                unmount_path(names.vault_mount, ctx=ctx)
            if was_open:
                close_mapper(names.vault_mapper, ctx=ctx)
            try:
                remove_empty_dir(names.vault_mount, ctx=ctx)
            except Exception:
                cleanup_lines.extend([
                    f"Could not remove mount directory: {names.vault_mount}",
                    "Remove it manually if needed.",
                ])
        except CalledProcessError as exc:
            return CommandResult(ok=False, exit_code=1, lines=lines + [f"Failed to unmount vault: {format_process_error(exc)}"])
        except Exception as exc:
            return CommandResult(ok=False, exit_code=1, lines=lines + [f"Failed to unmount vault: {exc}"])
        if not was_mounted and not was_open:
            return CommandResult(ok=True, lines=lines + [f"Vault was already unmounted: {names.vault_name}"] + cleanup_lines)
        return CommandResult(ok=True, lines=lines + [f"Unmounted vault: {names.vault_name}"] + cleanup_lines)
