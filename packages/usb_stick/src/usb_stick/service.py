from __future__ import annotations

from shutil import which
from subprocess import CalledProcessError

from usb_shared.execution import make_context
from usb_linux.blockdev import create_gpt, create_primary_partition, device_exists, first_partition_path, reread_partition_table
from usb_linux.luks import close_mapper, luks_format, make_ext4_filesystem, mapper_exists, open_mapper, mapper_path
from usb_linux.files import chown_path
from usb_linux.mounts import ensure_mount_dir, is_mounted, mount_device, remove_empty_dir, unmount_path
from usb_shared.models import CommandResult
from usb_shared.naming import derive_stick_names
from usb_shared.prompts import confirm
from usb_shared.subprocesses import format_process_error


class StickService:
    def _required_commands(self, commands: list[str]) -> str:
        missing = [cmd for cmd in commands if which(cmd) is None]
        return "OK" if not missing else "MISSING: " + ", ".join(missing)

    def create_status(self, stick_id: str, path: str) -> CommandResult:
        names = derive_stick_names(stick_id)
        lines = [
            "Stick create status:",
            f"Required commands: {self._required_commands(['cryptsetup','parted','partprobe','mount','umount','sudo'])}",
            f"ID:                {stick_id}",
            f"Path:              {path}",
            f"Path exists:       {'YES' if device_exists(path) else 'NO'}",
            f"Stick:             {names.stick_name}",
            f"Mapper:            {names.stick_mapper}",
            f"Filesystem label:  {names.stick_fs_label}",
            f"Mount path:        {names.stick_mount}",
            f"Ready:             {'YES' if device_exists(path) else 'NO'}",
        ]
        return CommandResult(ok=True, lines=lines)

    def create_manual(self, stick_id: str, path: str) -> CommandResult:
        names = derive_stick_names(stick_id)
        part1 = f"{path}-part1"
        lines = [
            "Manual procedure:",
            f"Target ID:         {stick_id}",
            f"Target path:       {path}",
            "1. Create GPT partition table",
            "2. Create one primary partition spanning the usable area",
            "3. Re-read the partition table",
            "4. Format the first partition as LUKS2",
            "5. Open the mapper",
            "6. Create ext4 filesystem",
            "Equivalent commands:",
            f"$ sudo parted -s {path} mklabel gpt",
            f"$ sudo parted -s {path} mkpart primary 1MiB 100%",
            f"$ sudo partprobe {path}",
            "$ udevadm settle",
            f"$ sudo cryptsetup luksFormat --batch-mode --type luks2 {part1}",
            f"$ sudo cryptsetup open {part1} {names.stick_mapper}",
            f"$ sudo mkfs.ext4 -L {names.stick_fs_label} /dev/mapper/{names.stick_mapper}",
            "Interactive notes:",
            "- cryptsetup will ask for a new LUKS passphrase",
            "- cryptsetup open will ask for the existing LUKS passphrase",
            "- mounting is a separate `stick mount` step",
        ]
        return CommandResult(ok=True, lines=lines)

    def create(self, stick_id: str, path: str, dry_run: bool = False, verbose: bool = False, logger=None) -> CommandResult:
        names = derive_stick_names(stick_id)
        ctx = make_context(verbose=verbose, sink=logger)
        lines = self.create_status(stick_id, path).lines + [
            "Plan:",
            f"1. Create GPT on: {path}",
            "2. Create one primary partition spanning the usable area",
            f"3. Format first partition as LUKS2 using mapper: {names.stick_mapper}",
            f"4. Create ext4 filesystem label: {names.stick_fs_label}",
            "5. Leave the stick unmounted",
        ]
        if dry_run:
            lines.extend([
                "Interactive prompts that would appear:",
                "- Proceed with creation confirmation",
                "- Enter new LUKS passphrase",
                "- Repeat new LUKS passphrase",
                "- Enter LUKS passphrase",
                "Equivalent commands:",
                f"$ sudo parted -s {path} mklabel gpt",
                f"$ sudo parted -s {path} mkpart primary 1MiB 100%",
                f"$ sudo partprobe {path}",
                "$ udevadm settle",
                f"$ sudo cryptsetup luksFormat --batch-mode --type luks2 {path}-part1",
                f"$ sudo cryptsetup open {path}-part1 {names.stick_mapper}",
                f"$ sudo mkfs.ext4 -L {names.stick_fs_label} /dev/mapper/{names.stick_mapper}",
                f"$ sudo cryptsetup close {names.stick_mapper}",
                "Dry-run only. No changes were made.",
            ])
            return CommandResult(ok=True, lines=lines)
        if not device_exists(path):
            return CommandResult(ok=False, exit_code=1, lines=[f"Configured path does not exist: {path}"])
        if not confirm(f"Proceed with creation for stick: {names.stick_name} ?"):
            return CommandResult(ok=False, exit_code=1, lines=["Cancelled."])
        try:
            if verbose:
                ctx.info(f"[1/6] Creating GPT on: {path}")
            create_gpt(path, ctx=ctx)
            if verbose:
                ctx.info(f"[2/6] Creating primary partition on: {path}")
            create_primary_partition(path, ctx=ctx)
            if verbose:
                ctx.info(f"[3/6] Re-reading partition table for: {path}")
            reread_partition_table(path, ctx=ctx)
            part1 = first_partition_path(path, ctx=ctx)
            if verbose:
                ctx.info(f"Resolved first partition path: {part1}")
                ctx.info(f"[4/6] Formatting LUKS2 on: {part1}")
                ctx.info("Interactive step: Python will ask for the new LUKS passphrase now.")
            luks_format(part1, ctx=ctx)
            if verbose:
                ctx.info(f"[5/6] Opening mapper: {names.stick_mapper}")
                ctx.info("Interactive step: Python will ask for the existing LUKS passphrase now.")
            open_mapper(part1, names.stick_mapper, ctx=ctx)
            try:
                if verbose:
                    ctx.info(f"[6/6] Creating ext4 filesystem label: {names.stick_fs_label}")
                make_ext4_filesystem(f"/dev/mapper/{names.stick_mapper}", names.stick_fs_label, ctx=ctx)
            finally:
                if verbose:
                    ctx.info(f"Closing mapper: {names.stick_mapper}")
                close_mapper(names.stick_mapper, ctx=ctx)
        except CalledProcessError as exc:
            return CommandResult(ok=False, exit_code=1, lines=lines + [f"Failed to create stick: {format_process_error(exc)}"])
        except Exception as exc:
            return CommandResult(ok=False, exit_code=1, lines=lines + [f"Failed to create stick: {exc}"])
        return CommandResult(ok=True, lines=lines + [f"Created stick: {names.stick_name}", "Stick remains unmounted."])

    def mount_status(self, stick_id: str, path: str) -> CommandResult:
        names = derive_stick_names(stick_id)
        mounted = is_mounted(names.stick_mount)
        lines = [
            "Stick mount status:",
            f"ID:                {stick_id}",
            f"Path:              {path}",
            f"Path exists:       {'YES' if device_exists(path) else 'NO'}",
            f"Mapper:            {'OPEN' if mapper_exists(names.stick_mapper) else 'CLOSED'} ({names.stick_mapper})",
            f"Mount path:        {names.stick_mount}",
            f"Mounted:           {'YES' if mounted else 'NO'}",
            f"Ready:             {'YES' if device_exists(path) else 'NO'}",
        ]
        return CommandResult(ok=True, lines=lines)

    def mount_manual(self, stick_id: str, path: str) -> CommandResult:
        names = derive_stick_names(stick_id)
        lines = [
            "Manual procedure:",
            f"Target ID:         {stick_id}",
            f"Target path:       {path}",
            "1. Resolve the first partition of the device",
            "2. Open the LUKS mapper",
            "3. Create the mount directory",
            "4. Mount the mapper",
            "Equivalent commands:",
            f"$ sudo cryptsetup open {path}-part1 {names.stick_mapper}",
            f"$ sudo mkdir -p {names.stick_mount}",
            f"$ sudo mount /dev/mapper/{names.stick_mapper} {names.stick_mount}",
            f"$ sudo chown $USER:$USER {names.stick_mount}",
            "Interactive notes:",
            "- cryptsetup open will ask for the existing LUKS passphrase",
            "- sudo may ask for your password",
        ]
        return CommandResult(ok=True, lines=lines)

    def mount(self, stick_id: str, path: str, dry_run: bool = False, verbose: bool = False, logger=None) -> CommandResult:
        names = derive_stick_names(stick_id)
        ctx = make_context(verbose=verbose, sink=logger)
        lines = self.mount_status(stick_id, path).lines + [
            "Plan:",
            f"1. Resolve first partition for: {path}",
            f"2. Open mapper: {names.stick_mapper}",
            f"3. Ensure mount path exists: {names.stick_mount}",
            f"4. Mount /dev/mapper/{names.stick_mapper} at {names.stick_mount}",
        ]
        if dry_run:
            lines.extend([
                "Interactive prompts that would appear:",
                "- Enter LUKS passphrase",
                "Equivalent commands:",
                f"$ sudo cryptsetup open {path}-part1 {names.stick_mapper}",
                f"$ sudo mkdir -p {names.stick_mount}",
                f"$ sudo mount /dev/mapper/{names.stick_mapper} {names.stick_mount}",
                f"$ sudo chown $USER:$USER {names.stick_mount}",
                "Dry-run only. No changes were made.",
            ])
            return CommandResult(ok=True, lines=lines)
        if not device_exists(path):
            return CommandResult(ok=False, exit_code=1, lines=[f"Configured path does not exist: {path}"])
        if is_mounted(names.stick_mount):
            return CommandResult(ok=True, lines=lines + [f"Stick was already mounted: {names.stick_name}"])
        try:
            part1 = first_partition_path(path, ctx=ctx)
            if verbose:
                ctx.info(f"Resolved first partition path: {part1}")
            if not mapper_exists(names.stick_mapper):
                if verbose:
                    ctx.info(f"Opening mapper: {names.stick_mapper}")
                    ctx.info("Interactive step: Python will ask for the existing LUKS passphrase now.")
                open_mapper(part1, names.stick_mapper, ctx=ctx)
            if verbose:
                ctx.info(f"Ensuring mount directory exists: {names.stick_mount}")
            ensure_mount_dir(names.stick_mount, ctx=ctx)
            if verbose:
                ctx.info(f"Mounting mapper at: {names.stick_mount}")
            mount_device(str(mapper_path(names.stick_mapper)), names.stick_mount, ctx=ctx)
            if verbose:
                ctx.info(f"Ensuring mounted stick is writable by current user: {names.stick_mount}")
            chown_path(names.stick_mount, recursive=False, ctx=ctx)
        except CalledProcessError as exc:
            return CommandResult(ok=False, exit_code=1, lines=lines + [f"Failed to mount stick: {format_process_error(exc)}"])
        except Exception as exc:
            return CommandResult(ok=False, exit_code=1, lines=lines + [f"Failed to mount stick: {exc}"])
        return CommandResult(ok=True, lines=lines + [f"Mounted stick: {names.stick_name}", f"Stick mount is writable by current user: {names.stick_mount}"])

    def unmount_status(self, stick_id: str) -> CommandResult:
        names = derive_stick_names(stick_id)
        lines = [
            "Stick unmount status:",
            f"ID:                {stick_id}",
            f"Mapper:            {'OPEN' if mapper_exists(names.stick_mapper) else 'CLOSED'} ({names.stick_mapper})",
            f"Mount path:        {names.stick_mount}",
            f"Mounted:           {'YES' if is_mounted(names.stick_mount) else 'NO'}",
            f"Ready:             {'YES' if is_mounted(names.stick_mount) or mapper_exists(names.stick_mapper) else 'NO'}",
        ]
        return CommandResult(ok=True, lines=lines)

    def unmount_manual(self, stick_id: str) -> CommandResult:
        names = derive_stick_names(stick_id)
        lines = [
            "Manual procedure:",
            f"Target ID:         {stick_id}",
            "1. Unmount the stick mount path",
            "2. Close the mapper",
            "3. Remove the empty mount directory if possible",
            "Equivalent commands:",
            f"$ sudo umount {names.stick_mount}",
            f"$ sudo cryptsetup close {names.stick_mapper}",
            f"$ sudo rmdir {names.stick_mount}",
        ]
        return CommandResult(ok=True, lines=lines)

    def unmount(self, stick_id: str, dry_run: bool = False, verbose: bool = False, logger=None) -> CommandResult:
        names = derive_stick_names(stick_id)
        ctx = make_context(verbose=verbose, sink=logger)
        lines = self.unmount_status(stick_id).lines + [
            "Plan:",
            f"1. Unmount path: {names.stick_mount}",
            f"2. Close mapper: {names.stick_mapper}",
            f"3. Remove empty mount directory: {names.stick_mount}",
        ]
        if dry_run:
            lines.extend([
                "Equivalent commands:",
                f"$ sudo umount {names.stick_mount}",
                f"$ sudo cryptsetup close {names.stick_mapper}",
                f"$ sudo rmdir {names.stick_mount}",
                "Dry-run only. No changes were made.",
            ])
            return CommandResult(ok=True, lines=lines)
        was_mounted = is_mounted(names.stick_mount)
        was_open = mapper_exists(names.stick_mapper)
        cleanup_lines: list[str] = []
        try:
            if was_mounted:
                if verbose:
                    ctx.info(f"Unmounting path: {names.stick_mount}")
                unmount_path(names.stick_mount, ctx=ctx)
            if was_open:
                if verbose:
                    ctx.info(f"Closing mapper: {names.stick_mapper}")
                close_mapper(names.stick_mapper, ctx=ctx)
            try:
                remove_empty_dir(names.stick_mount, ctx=ctx)
            except Exception:
                cleanup_lines.extend([
                    f"Could not remove mount directory: {names.stick_mount}",
                    "Remove it manually if needed.",
                ])
        except CalledProcessError as exc:
            return CommandResult(ok=False, exit_code=1, lines=lines + [f"Failed to unmount stick: {format_process_error(exc)}"])
        except Exception as exc:
            return CommandResult(ok=False, exit_code=1, lines=lines + [f"Failed to unmount stick: {exc}"])
        if not was_mounted and not was_open:
            return CommandResult(ok=True, lines=lines + [f"Stick was already unmounted: {names.stick_name}"] + cleanup_lines)
        return CommandResult(ok=True, lines=lines + [f"Unmounted stick: {names.stick_name}"] + cleanup_lines)
