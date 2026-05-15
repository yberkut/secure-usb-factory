from __future__ import annotations

from common import (
    base_config,
    build_command,
    e2e_vault_wipe_args,
    interactive_run,
    require_mounted_media,
    require_operator_ready,
    require_value,
    step,
    yes_answer,
)


cfg = base_config()


def main() -> None:
    require_operator_ready(cfg, ["vault", "vault_size", "vault_purpose", "vault_passphrase"])
    external_mount = require_value(cfg.external_mount, "cfg.external_mount")
    require_mounted_media(external_mount)

    vault = require_value(cfg.vault, "cfg.vault")
    vault_size = require_value(cfg.vault_size, "cfg.vault_size")
    vault_purpose = require_value(cfg.vault_purpose, "cfg.vault_purpose")

    step(1, "Create vault on already-mounted media")
    interactive_run(
        build_command(
            cfg,
            "vault",
            "create",
            "--media-id",
            cfg.stick_id,
            "--mount",
            external_mount,
            "--vault",
            vault,
            "--size",
            vault_size,
            "--purpose",
            vault_purpose,
            "-V",
        ),
        timeout=cfg.timeout,
        heartbeat=cfg.heartbeat,
        answers=yes_answer(),
        passphrases=[cfg.vault_passphrase or "", cfg.vault_passphrase or "", cfg.vault_passphrase or ""],
    )

    step(2, "Mount vault")
    interactive_run(
        build_command(
            cfg,
            "vault",
            "mount",
            "--media-id",
            cfg.stick_id,
            "--mount",
            external_mount,
            "--vault",
            vault,
            "-V",
        ),
        timeout=cfg.timeout,
        heartbeat=cfg.heartbeat,
        passphrases=[cfg.vault_passphrase or ""],
    )

    step(3, "Unmount vault")
    interactive_run(
        build_command(cfg, "vault", "unmount", "--media-id", cfg.stick_id, "--vault", vault, "-V"),
        timeout=cfg.timeout,
    )

    step(4, "Wipe vault container files")
    interactive_run(
        build_command(cfg, *e2e_vault_wipe_args(cfg, vault, vault_size, mount=external_mount)),
        timeout=cfg.timeout,
        heartbeat=cfg.heartbeat,
        answers=yes_answer(),
    )


if __name__ == "__main__":
    main()
