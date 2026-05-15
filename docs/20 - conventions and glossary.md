---
last updated: 2026-04-21
tags:
---
# Secure USB Factory — Conventions and glossary

> [!summary]
> Shared terminology and naming for the current multi-CLI model.

---

## Project and CLI naming

Project name:

- **Secure USB Factory**

Top-level CLIs:

- `stick`
- `vault`
- `wipe`
- `forge`

---

## Shared CLI flags

Common public flags:

- `--help`, `-h`
- `--version`
- `--verbose`, `-V`
- `--manual`, `-M`

Common workflow flags where relevant:

- `--status`, `-S`
- `--dry-run`, `-D`

Common short aliases:

- `--path`, `-p`
- `--mount`, `-m`
- `--vault`, `-v`
- `--stick-id`, `-s` for `stick` compatibility paths
- `--media-id`, `-s` for mounted-media vault workflows
- `--keepass`, `-k`
- `--panic`, `-P`

Wipe mode flags are target-specific:

- `wipe stick`: `--fast`, `-f`; `--full`, `-F`
- `wipe vault`: `--full`, `-F` where supported
- `wipe dir` and `wipe file`: no mode flags; always best-effort

Boolean short options may be clustered.

Value-taking short options must not be clustered as if they were boolean.

---

## Stick ID

A **Stick ID** is the logical stable identity of a SUF-created LUKS stick.

Examples:

```text
green
blue
travel
```

`stick` uses `--id` for its own operations.

## Media ID

A **media ID** is the logical stable identity used by vault workflows for any mounted media namespace. It may refer to a SUF-created stick, a plain USB filesystem, a mounted VeraCrypt volume, or another mounted encrypted filesystem.

Examples:

```text
green
plain-usb
veracrypt1
archive
```

`vault` and `wipe vault` use `--media-id`. `--stick-id` remains accepted as a compatibility alias for SUF-stick-backed vault workflows.

---

## Path

A **path** is a runtime location.

Examples:

- block-device path: `/dev/disk/by-id/...`
- mount path: `/media/green-stick`
- file path: `/some/file`

`wipe stick`, `wipe dir`, and `wipe file` use `--path`.

---

## Mount

A **mount** is the runtime mounted media filesystem path used by `vault` and `wipe vault`.

Example:

```text
/media/green-stick
/media/veracrypt1
```

`vault` uses `--mount`.

---

## Vault basename

A **vault basename** is the short vault identifier within a media namespace.

Example:

```text
personal
```

---

## Canonical naming

Given:

```text
media-id = green
vault = personal
```

Derived names:

```text
Media name:  green
Vault name:  green-personal-vault
Mapper:      map-green-personal-vault
Vault mount: /media/green-personal-vault
```

---

## Wipe semantics

### `wipe stick --full`
Strongest whole-stick destructive path.

### `wipe vault --full`
Destroy the encrypted vault container itself and remove the matching managed `.kdbx`.

### `wipe dir`
Best-effort directory-tree removal only. No `--fast` or `--full` mode.

### `wipe file`
Best-effort file removal only. No `--fast` or `--full` mode.

## Operator script

An **operator script** is a `forge`-generated convenience entrypoint.

Operator scripts may be atomic scripts that bind one tool command, or scenario scripts that run ordered steps. They are not the source of truth for behavior; the public CLIs remain the source of truth.

Script names are executable names and should be unique under `[forge.scripts.<script-name>]`.

Each script table should declare `disabled` explicitly:

```toml
disabled = false
```

Use `disabled = true` to validate but skip generation.
