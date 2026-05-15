---
last updated: 2026-05-13
tags:
---
# Secure USB Factory — Overview

Secure USB Factory is a Linux-first toolkit for portable encrypted vault workflows.

## Primary CLIs

```text
stick
vault
wipe
forge
```

- `stick` creates, opens, checks, and closes SUF-created LUKS USB sticks
- `vault` manages encrypted vault image files on any already-mounted media
- `wipe` performs destructive cleanup operations
- `forge` validates config and generates operator scripts

Operator scripts are generated convenience entrypoints. The primary CLIs remain the source of truth.

## Documentation map

- `25 - public CLI contract.md` — active command-family map and compatibility boundary
- `30 - stick - requirements.md` — stick behavior
- `40 - vault - requirements.md` — vault behavior
- `50 - wipe - requirements.md` — wipe behavior
- `60 - forge - requirements.md` — forge behavior
- `65 - e2e runner - requirements.md` — packaged-tool battlefield E2E runner boundary
- `70 - operator manual - Linux workflow.md` — operator workflow
- `80 - developer workflow - uv.md` — development, bootstrap, tests, packaging
- `runtime/` — minimal docs copied into generated packages

## Core model

- one Stick ID names one SUF-managed LUKS stick
- a media ID names the mounted media namespace used by vaults
- a mounted SUF stick path is normally `/media/<stick-id>-stick`
- a vault basename identifies one vault image and matching secret on mounted media
- script names are package conveniences, not canonical identity
