from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from subprocess import CalledProcessError

from usb_shared.execution import make_context
from usb_shared.models import CommandResult
from usb_shared.naming import derive_vault_names
from usb_shared.prompts import prompt_text
from usb_shared.subprocesses import format_process_error
from usb_linux.blockdev import (
    device_exists,
    device_identity,
    is_block_device,
    list_block_nodes,
    list_mapper_names_for_device,
    overwrite_device_full,
    wipe_signatures,
    zero_device_head,
    zero_device_tail,
)
from usb_linux.files import path_exists, remove_tree
from usb_linux.luks import close_mapper, mapper_exists
from usb_linux.mounts import (
    force_unmount_path,
    is_mounted,
    mounted_targets_for_sources,
    remove_empty_dir,
)


_PROTECTED_HOST_WIPE_PATHS = {
    Path("/"),
    Path("/bin"),
    Path("/boot"),
    Path("/dev"),
    Path("/etc"),
    Path("/home"),
    Path("/lib"),
    Path("/lib64"),
    Path("/media"),
    Path("/mnt"),
    Path("/opt"),
    Path("/proc"),
    Path("/root"),
    Path("/run"),
    Path("/sbin"),
    Path("/sys"),
    Path("/tmp"),
    Path("/usr"),
    Path("/var"),
}
_PROTECTED_HOST_WIPE_PREFIXES = (
    Path("/dev"),
    Path("/etc"),
    Path("/proc"),
    Path("/run"),
    Path("/sys"),
    Path("/usr"),
)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _host_wipe_rejection(path: Path, *, expected_kind: str) -> str | None:
    if not str(path):
        return "Target path must not be empty."
    if path.is_symlink():
        return f"Refusing to wipe symlink target: {path}"
    try:
        resolved = path.resolve(strict=path.exists())
    except OSError as exc:
        return f"Could not resolve target path: {path} ({exc})"
    if resolved in _PROTECTED_HOST_WIPE_PATHS:
        return f"Refusing to wipe protected path: {resolved}"
    for prefix in _PROTECTED_HOST_WIPE_PREFIXES:
        if _is_relative_to(resolved, prefix):
            return f"Refusing to wipe path under protected system directory: {resolved}"
    if path.exists():
        if expected_kind == "directory" and not path.is_dir():
            return f"Target is not a directory: {path}"
        if expected_kind == "file" and not path.is_file():
            return f"Target is not a regular file: {path}"
    return None


def _safe_host_wipe_ready(path: Path, *, expected_kind: str) -> bool:
    return _host_wipe_rejection(path, expected_kind=expected_kind) is None


class WipeService:
    def stick(
        self,
        path: str,
        fast: bool = False,
        full: bool = False,
        panic: bool = False,
        status: bool = False,
        manual: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
        logger=None,
    ) -> CommandResult:
        ctx = make_context(verbose=verbose, sink=logger)
        if status:
            lines = ["Wipe stick status:"]
            try:
                identity = device_identity(path, ctx=ctx)
            except Exception:
                identity = None
            exists = device_exists(path)
            block_device = is_block_device(path)
            lines.append(f"Path:              {path}")
            lines.append(f"Exists:            {'YES' if exists else 'NO'}")
            lines.append(f"Block device:      {'YES' if block_device else 'NO'}")
            if identity is not None:
                lines.append(f"Resolved path:     {identity.resolved_path}")
                if identity.size:
                    lines.append(f"Size:              {identity.size}")
                if identity.vendor:
                    lines.append(f"Vendor:            {identity.vendor}")
                if identity.model:
                    lines.append(f"Model:             {identity.model}")
                if identity.transport:
                    lines.append(f"Transport:         {identity.transport}")
                if identity.serial:
                    lines.append(f"Serial:            {identity.serial}")
                sources = list_block_nodes(identity.resolved_path, ctx=ctx)
                mounts = mounted_targets_for_sources(sources)
                lines.append(
                    f"Mounted targets:   {', '.join(str(m) for m in mounts) if mounts else 'NONE'}"
                )
                try:
                    mappers = list_mapper_names_for_device(identity.resolved_path, ctx=ctx)
                except Exception:
                    mappers = []
                lines.append(f"Open mappers:      {', '.join(mappers) if mappers else 'NONE'}")
            lines.append(f"Ready:             {'YES' if exists and block_device else 'NO'}")
            return CommandResult(ok=True, lines=lines)

        if fast == full:
            return CommandResult(
                ok=False,
                exit_code=2,
                lines=[
                    "Choose exactly one of --fast or --full, or use --status without a wipe mode."
                ],
            )

        mode = "full" if full else "fast"
        lines = [
            "Wipe stick status:",
            f"Path:              {path}",
            f"Mode:              {mode.upper()}",
            "Plan:",
            "1. Validate selected path is a block device",
            "2. Resolve block nodes and open mappers for selected device",
            "3. Unmount mounted partitions if needed",
            "4. Close discovered LUKS mappers if needed",
            f"5. {'Overwrite entire device' if full else 'Remove visible signatures and zero device head/tail'}",
        ]
        if manual:
            manual_lines = lines + [
                "Manual procedure:",
                f"Target path:       {path}",
                "Equivalent commands:",
            ]
            if full:
                manual_lines.extend(
                    [
                        f"$ sudo dd if=/dev/zero of={path} bs=16M conv=fsync status=progress",
                    ]
                )
            else:
                manual_lines.extend(
                    [
                        f"$ sudo wipefs -a {path}",
                        f"$ sudo dd if=/dev/zero of={path} bs=1M count=16 conv=fsync status=none",
                        f"$ sudo blockdev --getsize64 {path}",
                        f"$ sudo dd if=/dev/zero of={path} bs=1M seek=<tail-offset> count=16 conv=fsync status=none",
                    ]
                )
            manual_lines.extend(
                [
                    "Interactive notes:",
                    "- sudo may ask for your password",
                    "- mounted targets should be closed before wiping",
                ]
            )
            return CommandResult(ok=True, lines=manual_lines)
        if dry_run:
            lines.extend(
                [
                    "Dry-run procedure:",
                    "- Step 1 would verify that the selected path exists and is a block device.",
                    "- Step 2 would inspect the device identity, block nodes, and open mappers.",
                    "- Step 3 would lazily unmount mounted targets for those block nodes.",
                    "- Step 4 would close discovered LUKS mappers for those block nodes.",
                    *(
                        [
                            f"$ sudo dd if=/dev/zero of={path} bs=16M conv=fsync status=progress",
                        ]
                        if full
                        else [
                            f"$ sudo wipefs -a {path}",
                            f"$ sudo dd if=/dev/zero of={path} bs=1M count=16 conv=fsync status=none",
                            f"$ sudo blockdev --getsize64 {path}",
                            f"$ sudo dd if=/dev/zero of={path} bs=1M seek=<tail-offset> count=16 conv=fsync status=none",
                        ]
                    ),
                    "Interactive prompts:",
                    f"- Type the exact path to continue: {path}",
                    "Dry-run only. No changes were made.",
                ]
            )
            return CommandResult(ok=True, lines=lines)

        if not device_exists(path):
            return CommandResult(
                ok=False,
                exit_code=1,
                lines=lines + [f"Configured device path does not exist: {path}"],
            )
        if not is_block_device(path):
            return CommandResult(
                ok=False,
                exit_code=1,
                lines=lines + [f"Configured path is not a block device: {path}"],
            )

        try:
            ctx.step(1, 5, "Validating selected block device")
            ctx.step(2, 5, "Resolving block nodes and open mappers for selected device")
            identity = device_identity(path, ctx=ctx)
            sources = list_block_nodes(identity.resolved_path, ctx=ctx)
            mapper_names = list_mapper_names_for_device(identity.resolved_path, ctx=ctx)
            lines.append(
                f"Resolved block nodes: {', '.join(sources) if sources else identity.resolved_path}"
            )
            lines.append(
                f"Discovered mappers: {', '.join(mapper_names) if mapper_names else 'NONE'}"
            )
        except CalledProcessError as exc:
            return CommandResult(
                ok=False,
                exit_code=1,
                lines=lines + [f"Failed to inspect stick: {format_process_error(exc)}"],
            )
        except Exception as exc:
            return CommandResult(
                ok=False, exit_code=1, lines=lines + [f"Failed to inspect stick: {exc}"]
            )

        if not panic and prompt_text(f"Type the exact path to continue: {path}") != path:
            return CommandResult(ok=False, exit_code=1, lines=["Cancelled."])

        try:
            ctx.step(3, 5, "Unmounting mounted partitions if needed")
            for target in mounted_targets_for_sources(sources):
                if is_mounted(target):
                    force_unmount_path(target, ctx=ctx)
            ctx.step(4, 5, "Closing discovered LUKS mappers if needed")
            for mapper_name in mapper_names:
                if mapper_exists(mapper_name):
                    close_mapper(mapper_name, ctx=ctx)
            ctx.step(5, 5, "Executing destructive wipe")
            if full:
                overwrite_device_full(path, ctx=ctx)
            else:
                wipe_signatures(path, ctx=ctx)
                zero_device_head(path, ctx=ctx)
                zero_device_tail(path, ctx=ctx)
        except CalledProcessError as exc:
            return CommandResult(
                ok=False,
                exit_code=1,
                lines=lines + [f"Failed to wipe stick: {format_process_error(exc)}"],
            )
        except Exception as exc:
            return CommandResult(
                ok=False, exit_code=1, lines=lines + [f"Failed to wipe stick: {exc}"]
            )
        return CommandResult(ok=True, lines=lines + [f"Wiped stick: {path}"])

    def vault(
        self,
        media_id: str,
        mount: str,
        vault: str,
        fast: bool = False,
        full: bool = False,
        panic: bool = False,
        status: bool = False,
        manual: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
        logger=None,
    ) -> CommandResult:
        ctx = make_context(verbose=verbose, sink=logger)
        base_names = derive_vault_names(media_id, vault)
        vault_dir = Path(mount) / vault
        names = replace(
            base_names,
            vault_dir=vault_dir,
            vault_image=vault_dir / f"{vault}.img",
            secret_path=vault_dir / f"{vault}.kdbx",
        )
        media_mounted = is_mounted(Path(mount))
        if status:
            return CommandResult(
                ok=True,
                lines=[
                    "Wipe vault status:",
                    f"Media ID:          {media_id}",
                    f"Media mount:       {mount}",
                    f"Media mounted:     {'YES' if media_mounted else 'NO'}",
                    f"Vault:             {names.vault_name}",
                    f"Vault dir:         {names.vault_dir}",
                    f"Vault image:       {names.vault_image}",
                    f"Secret path:       {names.secret_path}",
                    f"Ready:             {'YES' if media_mounted and path_exists(names.vault_dir) else 'NO'}",
                ],
            )
        if fast and full:
            return CommandResult(
                ok=False,
                exit_code=2,
                lines=["Choose at most one of --fast or --full for vault wipes."],
            )
        if manual:
            lines = [
                "Manual procedure:",
                f"Media ID:          {media_id}",
                f"Media mount:       {mount}",
                f"Media mounted:     {'YES' if media_mounted else 'NO'}",
                f"Vault:             {vault}",
                "Preconditions:",
                f"- Media mount must be active: {mount}",
                "- Close the matching KeePassXC database before wiping.",
                "Equivalent commands:",
            ]
            if full or fast:
                lines.extend(
                    [
                        f"$ sudo cryptsetup close {names.vault_mapper}  # if open",
                        f"$ rm -f {names.vault_image}",
                        f"$ rm -f {names.secret_path}",
                        f"$ rmdir {names.vault_dir}  # if empty",
                    ]
                )
            else:
                lines.extend(
                    [
                        f"$ sudo cryptsetup close {names.vault_mapper}  # if open",
                        f"$ rm -rf {names.vault_dir}",
                    ]
                )
            return CommandResult(ok=True, lines=lines)
        lines = [
            "Wipe vault status:",
            f"Media ID:          {media_id}",
            f"Media mount:       {mount}",
            f"Media mounted:     {'YES' if media_mounted else 'NO'}",
            f"Vault:             {names.vault_name}",
            "Preconditions:",
            f"- Media mount must be active: {mount}",
            "- Close the matching KeePassXC database before wiping.",
            "Plan:",
            f"1. Attempt to unmount and close: {names.vault_name}",
            f"2. {'Destroy encrypted container and matching secret' if full else 'Remove vault container files' if fast else 'Remove managed vault directory'}",
        ]
        if dry_run:
            lines.extend(
                [
                    "Dry-run procedure:",
                    f"- Would require active media mount: {mount}",
                    f"- Would check and unmount {names.vault_mount} if needed.",
                    f"- Would close mapper {names.vault_mapper} if open.",
                    *(
                        [
                            f"$ rm -f {names.vault_image}",
                            f"$ rm -f {names.secret_path}",
                            f"$ rmdir {names.vault_dir}  # if empty",
                        ]
                        if full or fast
                        else [
                            f"$ rm -rf {names.vault_dir}",
                        ]
                    ),
                    "Interactive prompts:",
                    f"- Type YES to continue wiping vault {names.vault_name}",
                    "Dry-run only. No changes were made.",
                ]
            )
            return CommandResult(ok=True, lines=lines)
        if not media_mounted:
            return CommandResult(
                ok=False, exit_code=1, lines=lines + [f"Media mount is not active: {mount}"]
            )
        if (
            not panic
            and prompt_text(f"Type YES to continue wiping vault {names.vault_name}:") != "YES"
        ):
            return CommandResult(ok=False, exit_code=1, lines=["Cancelled."])
        try:
            ctx.step(1, 3, f"Ensuring vault mount is not active: {names.vault_mount}")
            if is_mounted(names.vault_mount):
                force_unmount_path(names.vault_mount, ctx=ctx)
                try:
                    remove_empty_dir(names.vault_mount, ctx=ctx)
                except Exception:
                    pass
            ctx.step(2, 3, f"Ensuring mapper is closed: {names.vault_mapper}")
            if mapper_exists(names.vault_mapper):
                close_mapper(names.vault_mapper, ctx=ctx)
            ctx.step(3, 3, "Executing destructive wipe")
            if full or fast:
                if names.vault_image.exists():
                    names.vault_image.unlink(missing_ok=True)
                if names.secret_path.exists():
                    names.secret_path.unlink(missing_ok=True)
                if names.vault_dir.exists() and not any(names.vault_dir.iterdir()):
                    names.vault_dir.rmdir()
            else:
                if names.vault_dir.exists():
                    remove_tree(names.vault_dir)
        except CalledProcessError as exc:
            return CommandResult(
                ok=False,
                exit_code=1,
                lines=lines + [f"Failed to wipe vault: {format_process_error(exc)}"],
            )
        except Exception as exc:
            return CommandResult(
                ok=False, exit_code=1, lines=lines + [f"Failed to wipe vault: {exc}"]
            )
        return CommandResult(ok=True, lines=lines + [f"Wiped vault: {names.vault_name}"])

    def dir(
        self,
        path: str,
        status: bool = False,
        manual: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
        logger=None,
    ) -> CommandResult:
        _ = (verbose, logger)
        p = Path(path)
        rejection = _host_wipe_rejection(p, expected_kind="directory")
        ready = rejection is None and p.exists() and p.is_dir()
        if status:
            lines = [
                "Wipe dir status:",
                f"Path:              {path}",
                f"Exists:            {'YES' if p.exists() else 'NO'}",
                f"Protected:         {'YES' if rejection else 'NO'}",
                f"Ready:             {'YES' if ready else 'NO'}",
            ]
            if rejection:
                lines.append(f"Reason:            {rejection}")
            return CommandResult(ok=True, lines=lines)
        if manual:
            lines = [
                "Manual procedure:",
                f"Target path:       {path}",
                "Safety checks:",
                "- Refuse protected system paths.",
                "- Refuse symlink targets.",
                "- Require a directory target.",
                "Equivalent commands:",
                f"$ rm -rf {path}",
                "Note: directory wiping is best-effort on host filesystems.",
            ]
            return CommandResult(ok=True, lines=lines)
        lines = [
            "Wipe dir status:",
            f"Path:              {path}",
            "Plan:",
            f"1. Remove directory tree: {path}",
        ]
        if rejection:
            return CommandResult(ok=False, exit_code=1, lines=lines + [rejection])
        if dry_run:
            lines.extend(
                [
                    "Dry-run procedure:",
                    f"$ rm -rf {path}",
                    "Interactive prompts:",
                    f"- Type the exact path to continue: {path}",
                    "Dry-run only. No changes were made.",
                ]
            )
            return CommandResult(ok=True, lines=lines)
        if not p.exists():
            return CommandResult(ok=False, exit_code=1, lines=[f"Target path not found: {path}"])
        if prompt_text(f"Type the exact path to continue: {path}") != path:
            return CommandResult(ok=False, exit_code=1, lines=["Cancelled."])
        remove_tree(p)
        return CommandResult(ok=True, lines=lines + [f"Wiped directory: {path}"])

    def file(
        self,
        path: str,
        status: bool = False,
        manual: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
        logger=None,
    ) -> CommandResult:
        _ = (verbose, logger)
        p = Path(path)
        rejection = _host_wipe_rejection(p, expected_kind="file")
        ready = rejection is None and p.exists() and p.is_file()
        if status:
            lines = [
                "Wipe file status:",
                f"Path:              {path}",
                f"Exists:            {'YES' if p.exists() else 'NO'}",
                f"Protected:         {'YES' if rejection else 'NO'}",
                f"Ready:             {'YES' if ready else 'NO'}",
            ]
            if rejection:
                lines.append(f"Reason:            {rejection}")
            return CommandResult(ok=True, lines=lines)
        if manual:
            lines = [
                "Manual procedure:",
                f"Target path:       {path}",
                "Safety checks:",
                "- Refuse protected system paths.",
                "- Refuse symlink targets.",
                "- Require a regular file target.",
                "Equivalent commands:",
                f"$ rm -f {path}",
                "Note: file wiping is best-effort on host filesystems.",
            ]
            return CommandResult(ok=True, lines=lines)
        lines = [
            "Wipe file status:",
            f"Path:              {path}",
            "Plan:",
            f"1. Remove file: {path}",
        ]
        if rejection:
            return CommandResult(ok=False, exit_code=1, lines=lines + [rejection])
        if dry_run:
            lines.extend(
                [
                    "Dry-run procedure:",
                    f"$ rm -f {path}",
                    "Interactive prompts:",
                    f"- Type the exact path to continue: {path}",
                    "Dry-run only. No changes were made.",
                ]
            )
            return CommandResult(ok=True, lines=lines)
        if not p.exists():
            return CommandResult(ok=False, exit_code=1, lines=[f"Target path not found: {path}"])
        if prompt_text(f"Type the exact path to continue: {path}") != path:
            return CommandResult(ok=False, exit_code=1, lines=["Cancelled."])
        p.unlink()
        return CommandResult(ok=True, lines=lines + [f"Wiped file: {path}"])
