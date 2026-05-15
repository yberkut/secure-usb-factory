---
last updated: 2026-05-13
tags:
---
# Secure USB Factory — Public CLI contract

> [!summary]
> Current public command families and compatibility boundary.
>
> This document is the quick map for the active CLI surface. The detailed behavior contracts remain in the per-tool requirement documents.

---

## Current public command families

The current public CLI families are:

```text
stick
vault
wipe
forge
```

These are the names used by source-tree commands, packaged commands, operator scripts, tests, and operator documentation.

The retired public families are not part of the current contract:

```text
manager
builder
eraser
```

Do not add new docs, tests, scripts, examples, or package behavior using those names.

---

## Tool map

| Tool | Owns | Does not own |
| --- | --- | --- |
| `stick` | SUF-created outer LUKS stick lifecycle | vault lifecycle, generic media, vault wiping |
| `vault` | vault images on already-mounted media | outer media lifecycle, destructive wiping |
| `wipe` | destructive cleanup paths | normal mount/create workflows |
| `forge` | script/config/artifact composition | runtime behavior of `stick`, `vault`, or `wipe` |

---

## Uniform flag expectations

All current public tool roots should support:

```text
--help
-h
--version
--manual
-M
```

Version output uses the centralized SemVer project version. In this release, each public root reports `1.0.0`, for example:

```text
stick 1.0.0
vault 1.0.0
wipe 1.0.0
forge 1.0.0
```

Action commands should support `--verbose` / `-V` where extra execution detail is useful.

Action commands may also support:

```text
--status
-S
--dry-run
-D
```

`--status`, `--dry-run`, and `--manual` must not perform the main state-changing operation.

---

## Current command shape

### `stick`

```text
stick create --id <id> --path <device-path>
stick mount --id <id> --path <device-path>
stick unmount --id <id>
```

`stick` is only for SUF-created managed LUKS sticks.

### `vault`

```text
vault create --media-id <id> --mount <mount-path> --vault <basename> --size <size> --purpose <text>
vault mount --media-id <id> --mount <mount-path> --vault <basename>
vault unmount --media-id <id> --vault <basename>
```

`vault` works with any already-mounted media path, including a SUF stick, a plain USB drive, VeraCrypt media, or another mounted encrypted filesystem.

`--stick-id` may remain as a compatibility alias for `--media-id`, but new docs and examples should prefer `--media-id`.

### `wipe`

```text
wipe stick --path <device-path> --fast
wipe stick --path <device-path> --full
wipe stick --path <device-path> --status

wipe vault --media-id <id> --mount <mount-path> --vault <basename>
wipe dir --path <path>
wipe file --path <path>
```

`wipe stick` requires exactly one of `--fast` or `--full` for destructive execution, dry-run, and command-level manual output. `--status` does not require a wipe mode. Destructive execution must validate that the selected device path exists before asking for exact-path confirmation.

`wipe vault` requires `--mount` to point at an active mounted media path before destructive execution. It must fail before prompting if the media mount is not active.

`wipe dir` and `wipe file` are best-effort host filesystem cleanup helpers. They must not expose `--fast` or `--full`.

### `forge`

```text
forge validate
forge inspect
forge generate
```

`forge` reads the source `suf.toml` in the repo and the packaged `config/forge.toml` inside packaged artifacts.

---

## Test boundary

Contract tests should protect the current public command families and reject retired public roots.

Integration tests may exercise packaged command behavior, packaged forge behavior, and operator script behavior, but they should remain separate from the local pre-archive `make check` gate until they are consistently boring.

---

## Cross-reference guidance

Use this document together with:

- `30 - stick - requirements.md`
- `40 - vault - requirements.md`
- `50 - wipe - requirements.md`
- `60 - forge - requirements.md`
- `20 - conventions and glossary.md`
