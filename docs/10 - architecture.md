---
last updated: 2026-05-03
tags:
---
# Secure USB Factory — Architecture

## Layers

1. **CLI layer** — `stick`, `vault`, `wipe`, and `forge`.
2. **Implementation packages** — `usb_*` packages under `packages/`.
3. **Generated package layer** — optional package output under `dist/suf`.

## Package ownership

```text
src/stick      -> packages/usb_stick
src/vault      -> packages/usb_vault
src/wipe       -> packages/usb_wipe
src/forge      -> packages/usb_forge
tools/e2e_runner.py -> tests/e2e scenario files
usb_* packages -> usb_shared and usb_linux as needed
```

Tool packages must not depend on each other for policy. Shared primitives belong in `usb_shared`; Linux command adapters belong in `usb_linux`.

## Config and generation

The repository config is `suf.toml`.

`forge` uses that config to generate operator scripts. `make package` is separate build tooling; it reads `[package].lib_layout` for the runtime form and `[package].tools` for packaged CLI entrypoints, but there is no separate runtime config table.

When `forge` is included in a package, the package contains `config/forge.toml`. That packaged config is for script regeneration only and uses the same simplified `[artifacts]`, `[sticks]`, and `[forge.scripts]` model.

## Generated package shape

```text
dist/suf/
├── bin/
├── lib/
├── docs/
├── config/        # present when forge is packaged
└── manifest.json
```

`lib/` is either copied Python package trees (`lib_layout = "tree"`) or one PyInstaller executable per selected package tool (`lib_layout = "executable"`). `[package].tools` selects the packaged CLI entrypoints. `docs/` contains runtime docs only for selected packaged tools.
