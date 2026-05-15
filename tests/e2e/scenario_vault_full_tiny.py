from __future__ import annotations

import os

from common import E2E_FULL_WIPE_MAX_BYTES, base_config, e2e_vault_wipe_args, parse_size_bytes

os.environ.setdefault("SUF_E2E_VAULT_SIZE", "8M")

from scenario_vault_lifecycle import main as vault_lifecycle_main  # noqa: E402


cfg = base_config()


def main() -> None:
    size = cfg.vault_size or "8M"
    if parse_size_bytes(size) > E2E_FULL_WIPE_MAX_BYTES:
        raise SystemExit("E2E tiny full-wipe scenario requires SUF_E2E_VAULT_SIZE <= 8M.")
    # The shared lifecycle already calls e2e_vault_wipe_args(), which chooses --full for <= 8M.
    e2e_vault_wipe_args(cfg, cfg.vault or "test1", size)
    vault_lifecycle_main()


if __name__ == "__main__":
    main()
