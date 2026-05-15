from __future__ import annotations

from getpass import getpass
from pathlib import Path

from usb_shared.execution import ExecutionContext
from usb_shared.subprocesses import run, run_with_input


def mapper_path(name: str) -> Path:
    return Path('/dev/mapper').joinpath(name)


def mapper_exists(name: str) -> bool:
    return mapper_path(name).exists()


def _prompt_new_passphrase() -> str:
    first = getpass('Enter new LUKS passphrase: ')
    second = getpass('Repeat new LUKS passphrase: ')
    if first != second:
        raise ValueError('Passphrases do not match.')
    if not first:
        raise ValueError('Passphrase must not be empty.')
    return first


def _prompt_existing_passphrase() -> str:
    value = getpass('Enter LUKS passphrase: ')
    if not value:
        raise ValueError('Passphrase must not be empty.')
    return value


def open_mapper(source: str, name: str, ctx: ExecutionContext | None = None) -> None:
    passphrase = _prompt_existing_passphrase()
    run_with_input(['sudo', 'cryptsetup', 'open', source, name], input_text=passphrase + '\n', ctx=ctx)


def close_mapper(name: str, ctx: ExecutionContext | None = None) -> None:
    run(['sudo', 'cryptsetup', 'close', name], ctx=ctx)


def luks_format(path: str, ctx: ExecutionContext | None = None) -> None:
    passphrase = _prompt_new_passphrase()
    run_with_input(
        ['sudo', 'cryptsetup', 'luksFormat', '--batch-mode', '--type', 'luks2', path],
        input_text=passphrase + '\n',
        ctx=ctx,
    )


def make_ext4_filesystem(device: str, label: str, ctx: ExecutionContext | None = None) -> None:
    run(['sudo', 'mkfs.ext4', '-L', label, device], ctx=ctx)
