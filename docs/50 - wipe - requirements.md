---
last updated: 2026-04-21
tags:
---
# Secure USB Factory — Wipe requirements and public contract

> [!summary]
> Behavior contract for the `wipe` CLI.

---

## Purpose

`wipe` owns destructive operations.

Target families:

- `wipe stick` for SUF-created LUKS stick whole-device cleanup
- `wipe vault` for vault data on any already-mounted media
- `wipe dir`
- `wipe file`

---

## Uniform flags

`wipe` must support:

- `--help`, `-h`
- `--version`
- `--verbose`, `-V`
- `--manual`, `-M`

Where relevant it must also support:

- `--status`, `-S`
- `--dry-run`, `-D`
- `--panic`, `-P`

Mode flags are only for targets that support modes:

- `wipe stick` for SUF-created LUKS stick whole-device cleanup supports `--fast`, `-f` and `--full`, `-F`
- `wipe stick` for SUF-created LUKS stick whole-device cleanup requires exactly one of `--fast` or `--full` for wipe, dry-run, and manual output; `--status` does not require a wipe mode
- `wipe vault` for vault data on any already-mounted media supports `--full`, `-F` where supported
- `wipe dir` and `wipe file` do **not** support `--fast` or `--full`

---

## Command shape

Supported groups:

```text
wipe stick ...
wipe vault ...
wipe dir ...
wipe file ...
```

### `wipe stick`

Use:

- `--path`, `-p`
- exactly one of `--fast`, `-f` or `--full`, `-F` for destructive execution, dry-run, and command-level manual output
- `--panic`, `-P`
- `--status`, `-S` without a wipe mode for readiness only

Examples:

```text
wipe stick --path /dev/disk/by-id/... --fast
wipe stick --path /dev/disk/by-id/... --full
wipe stick --path /dev/disk/by-id/... --fast --panic
wipe stick --path /dev/disk/by-id/... --fast --manual
wipe stick --path /dev/disk/by-id/... --status
```

### `wipe vault`

Use:

- `--media-id`, `-s`
- `--stick-id` as a compatibility alias for `--media-id`
- `--mount`, `-m`
- `--vault`, `-v`
- `--full`, `-F` where supported

Examples:

```text
wipe vault --media-id green --mount /media/green-stick --vault personal
wipe vault --media-id green --mount /media/green-stick --vault personal --full
wipe vault --media-id green --mount /media/green-stick --vault personal --status
```

### `wipe dir`

Use:

- `--path`, `-p`
- `--status`, `-S`
- `--dry-run`, `-D`
- `--manual`, `-M`
- `--verbose`, `-V`

Examples:

```text
wipe dir --path /some/path
wipe dir --path /some/path --dry-run
wipe dir --path /some/path --status
```

`wipe dir` is always best-effort. It removes the selected directory tree after explicit confirmation.
It must not expose `--fast` or `--full`, because host-filesystem directory removal cannot promise mode-specific wipe guarantees. It always performs the best-effort directory removal procedure.

### `wipe file`

Use:

- `--path`, `-p`
- `--status`, `-S`
- `--dry-run`, `-D`
- `--manual`, `-M`
- `--verbose`, `-V`

Examples:

```text
wipe file --path /some/file
wipe file --path /some/file --dry-run
wipe file --path /some/file --status
```

`wipe file` is always best-effort. It removes the selected file after explicit confirmation.
It must not expose `--fast` or `--full`, because host-filesystem file removal cannot promise mode-specific wipe guarantees. It always performs the best-effort file removal procedure.

---

## Semantics

### `wipe stick --fast`

Fast reset for a whole device intended for SUF-created LUKS stick reuse.

Before destructive confirmation, `wipe stick --fast` must validate that the selected device path exists. If it does not, the command must fail before prompting.

### `wipe stick --full`

Strongest whole-device destructive path for SUF-created LUKS stick workflows.

Before destructive confirmation, `wipe stick --full` must validate that the selected device path exists. If it does not, the command must fail before prompting.

### `wipe vault`

Remove the managed vault target on the provided mounted media.

Destructive execution must require the provided `--mount` path to be an active mount. If it is not mounted, the command must fail before prompting and must not delete the vault directory.

Plans, dry-runs, manual output, and destructive execution output must remind the operator to close the matching KeePassXC database before wiping.

### `wipe vault --full`

Destroy the encrypted vault container itself and remove the matching managed `.kdbx` too.

### `wipe dir`

Best-effort directory-tree removal only.

### `wipe file`

Best-effort file removal only.

`wipe dir` and `wipe file` must not claim universal guaranteed unrecoverability.

---

## Confirmation model

### Stick

Strongest confirmation.

### Vault

Strong confirmation.

### Dir and file

Additional confirmation because these are general-purpose destructive utilities.

---

## Status model

`--status` must show readiness only and perform no mutation.

`wipe vault --status` must report whether the provided media mount is active. Readiness requires both an active media mount and the derived vault directory to exist.

It should be available on:

- `wipe stick` for SUF-created LUKS stick whole-device cleanup
- `wipe vault` for vault data on any already-mounted media
- `wipe dir`
- `wipe file`
