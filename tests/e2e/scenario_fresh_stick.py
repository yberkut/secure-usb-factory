from __future__ import annotations

from common import (
    base_config,
    build_command,
    confirm_device_answers,
    interactive_run,
    require_operator_ready,
    step,
    yes_answer,
)


cfg = base_config()


def main() -> None:
    require_operator_ready(cfg, ["device_path", "passphrase"])

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

    step(3, "Unmount stick")
    interactive_run(
        build_command(cfg, "stick", "unmount", "--id", cfg.stick_id, "-V"),
        timeout=cfg.timeout,
    )

    step(4, "Remount stick")
    interactive_run(
        build_command(cfg, "stick", "mount", "--id", cfg.stick_id, "--path", cfg.device_path, "-V"),
        timeout=cfg.timeout,
        heartbeat=cfg.heartbeat,
        passphrases=[cfg.passphrase or ""],
    )

    step(5, "Final unmount")
    interactive_run(
        build_command(cfg, "stick", "unmount", "--id", cfg.stick_id, "-V"),
        timeout=cfg.timeout,
    )


if __name__ == "__main__":
    main()
