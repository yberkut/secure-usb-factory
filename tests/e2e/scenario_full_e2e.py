from __future__ import annotations

from common import (
    base_config,
    build_command,
    confirm_device_answers,
    e2e_vault_wipe_args,
    interactive_run,
    require_operator_ready,
    require_value,
    step,
    yes_answer,
)


cfg = base_config()


def main() -> None:
    require_operator_ready(
        cfg,
        ["device_path", "passphrase", "vault", "vault_size", "vault_purpose", "vault_passphrase"],
    )

    vault = require_value(cfg.vault, "cfg.vault")
    vault_size = require_value(cfg.vault_size, "cfg.vault_size")
    vault_purpose = require_value(cfg.vault_purpose, "cfg.vault_purpose")

    step(1, "Whole-stick fast wipe")
    interactive_run(
        build_command(cfg, "wipe", "stick", "--path", cfg.device_path, "--fast", "-V"),
        timeout=cfg.timeout,
        heartbeat=cfg.heartbeat,
        answers=confirm_device_answers(cfg.device_path),
    )

    step(2, "Create stick")
    interactive_run(
        build_command(cfg, "stick", "create", "--id", cfg.stick_id, "--path", cfg.device_path, "-V"),
        timeout=cfg.timeout,
        heartbeat=cfg.heartbeat,
        answers=yes_answer(),
        passphrases=[cfg.passphrase or "", cfg.passphrase or "", cfg.passphrase or ""],
    )

    step(3, "Mount stick")
    interactive_run(
        build_command(cfg, "stick", "mount", "--id", cfg.stick_id, "--path", cfg.device_path, "-V"),
        timeout=cfg.timeout,
        heartbeat=cfg.heartbeat,
        passphrases=[cfg.passphrase or ""],
    )

    step(4, "Create vault")
    interactive_run(
        build_command(
            cfg,
            "vault",
            "create",
            "--media-id",
            cfg.stick_id,
            "--mount",
            cfg.media_mount,
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

    step(5, "Mount vault")
    interactive_run(
        build_command(
            cfg,
            "vault",
            "mount",
            "--media-id",
            cfg.stick_id,
            "--mount",
            cfg.media_mount,
            "--vault",
            vault,
            "-V",
        ),
        timeout=cfg.timeout,
        heartbeat=cfg.heartbeat,
        passphrases=[cfg.vault_passphrase or ""],
    )

    step(6, "Unmount vault")
    interactive_run(
        build_command(cfg, "vault", "unmount", "--media-id", cfg.stick_id, "--vault", vault, "-V"),
        timeout=cfg.timeout,
    )

    step(7, "Wipe vault container files")
    interactive_run(
        build_command(cfg, *e2e_vault_wipe_args(cfg, vault, vault_size)),
        timeout=cfg.timeout,
        heartbeat=cfg.heartbeat,
        answers=yes_answer(),
    )

    step(8, "Final unmount")
    interactive_run(
        build_command(cfg, "stick", "unmount", "--id", cfg.stick_id, "-V"),
        timeout=cfg.timeout,
    )

    step(9, "Final whole-stick wipe")
    interactive_run(
        build_command(cfg, "wipe", "stick", "--path", cfg.device_path, "--fast", "-V"),
        timeout=cfg.timeout,
        heartbeat=cfg.heartbeat,
        answers=confirm_device_answers(cfg.device_path),
    )


if __name__ == "__main__":
    main()
