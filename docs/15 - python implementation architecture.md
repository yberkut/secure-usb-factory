---
last updated: 2026-05-03
tags:
---
# Secure USB Factory — Python implementation architecture

## Source layout

```text
src/
  stick/
  vault/
  wipe/
  forge/
packages/
  usb_shared/
  usb_linux/
  usb_stick/
  usb_vault/
  usb_wipe/
  usb_forge/
tests/
tools/
```

## Responsibilities

- `usb_shared` — config schema/loading, errors, naming, output helpers
- `usb_linux` — Linux command adapters
- `usb_stick` — stick services and CLI implementation
- `usb_vault` — vault services and CLI implementation
- `usb_wipe` — wipe services and CLI implementation
- `usb_forge` — script planning, validation, rendering, artifact staging

## Runtime package behavior

Repository packaging is handled by `tools/package.py` through `make package`. It emits the standard `dist/suf` package shape, reads `[package].tools` to choose packaged CLI entrypoints, and reads `[package].lib_layout` to choose either source-tree runtime libraries or one PyInstaller executable per selected packaged tool.

Packaged `forge` loads `config/forge.toml` and regenerates operator scripts only. It reuses the package runtime already built under `dist/suf/lib/` and does not rebuild `lib/` or invoke PyInstaller.
