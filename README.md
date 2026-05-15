# Secure USB Factory

Secure USB Factory is a Linux-first toolkit for portable encrypted vault workflows.

## CLI tools

- `stick` — create, open, check, and close SUF-created LUKS USB sticks
- `vault` — create, mount, unmount, and inspect encrypted vault image files on any already-mounted media
- `wipe` — wipe SUF stick devices, vault data on mounted media, arbitrary directories, and files
- `forge` — validate config and generate operator scripts

Operator scripts are generated convenience entrypoints. The tool CLIs above are the source of truth. Operator scripts provide script-specific help for bound targets; tool CLIs remain the source of truth for command behavior.

## Repository layout

- `src/stick/`, `src/vault/`, `src/wipe/`, `src/forge/` — public CLI shims
- `packages/usb_shared/` — shared primitives
- `packages/usb_linux/` — Linux adapters
- `packages/usb_stick/` — stick implementation
- `packages/usb_vault/` — vault implementation
- `packages/usb_wipe/` — wipe implementation
- `packages/usb_forge/` — script/artifact generation implementation
- `docs/` — project and runtime documentation

## Bootstrap

After unpacking an archive, make helper scripts executable once:

```bash
chmod +x ./tools/*.sh
```

Bootstrap creates or updates `.venv` with runtime dependencies plus the `dev`, `lint`, and `build` extras:

```bash
make bootstrap
```

It does not activate your current shell. Use Make targets directly; they run through `uv run`. For interactive work, activate manually after bootstrap:

```bash
source .venv/bin/activate
```

The bootstrap script uses public PyPI by default:

```bash
uv sync --extra dev --extra lint --extra build --index-url https://pypi.org/simple
```

Override the index intentionally with `UV_INDEX_URL`:

```bash
UV_INDEX_URL=https://your.index/simple ./tools/bootstrap.sh
```

If an SSH VM or IDE remote environment points at an unreachable package mirror, inspect the environment:

```bash
env | grep -E 'UV_|PIP_|HTTP|HTTPS|NO_PROXY'
pip config list 2>/dev/null || true
cat ~/.config/uv/uv.toml 2>/dev/null || true
cat uv.toml 2>/dev/null || true
```

## Common development commands

```bash
make smoke        # smoke tests only, via uv run
make unit         # smoke + unit tests, via uv run
make integration  # automated package/forge integration tests, via uv run
make test         # full pytest suite, via uv run
make test-quiet
make lint
make package
```

These commands do not require an activated shell.

E2E scenarios are development helpers only and they are battlefield hardware tests. Run `make e2e-config` once, edit `tests/e2e/e2e.env`, run `make package`, then use targets such as `make e2e-smoke`, `make e2e-stick`, `make e2e-vault`, `make e2e-mounted-media`, or `make e2e-full`. E2E executes packaged tools from `dist/suf/bin` by default; override with `SUF_E2E_TOOL_DIR` when testing another packaged bin directory.

## Package command

`make package` builds the standard developer/runtime package at `dist/suf`.

Packaging is configured through the root `[package]` table. `[package].tools` controls which CLI entrypoints are packaged. `suf` is not packageable; packaged tools are standalone operator CLIs.

`[package].lib_layout` controls the runtime form used by `make package`:

- `tree` copies Python source package trees into `dist/suf/lib/` for inspection.
- `executable` builds one PyInstaller runtime per selected tool, for example `dist/suf/lib/stick`, and points each `dist/suf/bin/<tool>` at its matching runtime.

Package builds remove generated `build/` and `dist/` directories before running so stale files cannot mix with a new package.

For a release-style packaging check that exercises both runtime layouts, run:

```bash
make package-review
```

That command tests both `tree` and `executable` in an isolated temporary checkout, leaves the working `build/` and `dist/` directories untouched, and verifies packaged `forge generate` plus operator script help for each layout. The temporary checkout is deleted when the review exits.

## Package docs and config

A package contains runtime documentation only:

```text
dist/suf/docs/<tool>.md
```

Tool docs are copied only for configured packaged tools.

If `forge` is included, the package also contains:

```text
dist/suf/config/forge.toml
```

Packaged `forge` uses that config to validate, inspect, and regenerate scripts. It does not rebuild the full package runtime. Use repository `make package` for full package builds; that packaging step honors `[package].lib_layout` and creates either raw Python libraries or one PyInstaller runtime under `dist/suf/lib/`.

## Forge scripts

Script names should use a clear target-domain-action shape, for example `green-stick-create` and `green-vault-personal-mount`. Scripts can be kept in config but skipped during generation:

```toml
[forge.scripts.green-vault-personal-create]
type = "atomic"
disabled = false
tool = "vault"
command = "create"
help = "Create personal vault on the configured green stick."
stick_id = "green"
vault = "personal"
```

Set `disabled = true` to keep a script in config while skipping generation. Disabled scripts are validated and listed by `forge inspect`, but no executable script is generated for them.

## Mounted media ownership

Mounted media can be owned by `root` after privileged mount operations. If vault creation fails with `Permission denied` under the selected mount path, repair ownership after mounting:

```bash
sudo chown -R "$USER":"$USER" /media/green-stick
find /media/green-stick -type d -exec chmod 700 {} \;
find /media/green-stick -type f -exec chmod 600 {} \;
```

Use the real mounted media path instead of `/media/green-stick`.
