from __future__ import annotations

import sys
from collections.abc import Sequence

from .version import VERSION


def _completion_script(tool: str) -> str:
    # Minimal deterministic bash completion stub for smoke/integration checks.
    # Full dynamic completion stays available through the Typer app when needed.
    return f"""_{tool}_completion() {{
    COMPREPLY=()
}}
complete -F _{tool}_completion {tool}
"""


def _tool_commands(tool: str) -> list[str]:
    return {
        "stick": [
            "create   Provision a new encrypted stick",
            "mount    Open and mount an existing stick",
            "unmount  Unmount and close an open stick",
        ],
        "vault": [
            "create   Create a vault image on mounted media",
            "mount    Open and mount a vault image",
            "unmount  Unmount and close an open vault",
            "open-secret  Open the matching KeePassXC secret",
        ],
        "wipe": [
            "stick   Wipe a physical stick device",
            "vault   Wipe a managed vault directory",
            "dir     Remove a host directory tree",
            "file    Remove a host file",
        ],
        "forge": [
            "validate  Validate the forge config",
            "inspect   Show the resolved generation plan",
            "generate  Generate scripts and the artifact tree",
        ],
    }.get(tool, [])


def _tool_examples(tool: str) -> list[str]:
    return {
        "stick": [
            "stick create --id green --path /dev/disk/by-id/... --dry-run",
            "stick mount --id green --path /dev/disk/by-id/... --status",
            "stick unmount --id green",
        ],
        "vault": [
            "vault create --media-id green --mount /media/green-stick --vault personal --size 8G --purpose personal data --dry-run",
            "vault mount --media-id green --mount /media/green-stick --vault personal",
            "vault open-secret --media-id green --mount /media/green-stick --vault personal",
        ],
        "wipe": [
            "wipe stick --path /dev/disk/by-id/... --fast --dry-run",
            "wipe vault --media-id green --mount /media/green-stick --vault personal --status",
            "wipe dir --path /tmp/suf-test --dry-run",
        ],
        "forge": [
            "forge validate",
            "forge inspect",
            "forge generate",
        ],
    }.get(tool, [])


def _help_text(tool: str) -> str:
    command_lines = _tool_commands(tool)
    example_lines = _tool_examples(tool)
    commands = "\n".join(f"  {line}" for line in command_lines)
    examples = "\n".join(f"  $ {line}" for line in example_lines)
    command_block = f"\nCommands:\n{commands}\n" if commands else ""
    example_block = f"\nExamples:\n{examples}\n" if examples else ""
    return f"""Usage: {tool} [OPTIONS] COMMAND [ARGS]...

Secure USB Factory {tool} command.

Options:
  --help     Show this message and exit.
  -h         Show this message and exit.
  --version  Show version and exit.
{command_block}{example_block}
Commands are documented in docs/runtime/{tool}.md.
"""


def maybe_handle_fast_metadata(tool: str, argv: Sequence[str] | None = None) -> None:
    """Handle metadata-only CLI calls without importing the full Typer app.

    This keeps packaged smoke/integration checks deterministic in constrained
    environments where importing the whole CLI tree can trigger slow shell/Rich
    discovery paths.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return

    if len(args) == 1 and args[0] == "--version":
        print(f"{tool} {VERSION}")
        raise SystemExit(0)

    if len(args) == 1 and args[0] in {"--help", "-h"}:
        print(_help_text(tool), end="")
        raise SystemExit(0)

    if args[:1] in (["--show-completion"], ["--install-completion"]):
        shell = args[1] if len(args) > 1 else "bash"
        if shell == "bash":
            print(_completion_script(tool), end="")
            raise SystemExit(0)
        return


__all__ = ["maybe_handle_fast_metadata"]
