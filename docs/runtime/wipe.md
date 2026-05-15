# wipe runtime guide

`wipe` is for destructive cleanup.

Use it only when you intentionally want to remove data from a selected device, vault directory, directory tree, or file.

## Common commands

```bash
wipe stick --path /dev/disk/by-id/... --fast
wipe stick --path /dev/disk/by-id/... --full
wipe stick --path /dev/disk/by-id/... --status
wipe vault --media-id green --mount /media/green-stick --vault personal --full
wipe vault --media-id veracrypt1 --mount /media/veracrypt1 --vault personal
wipe dir --path /path/to/directory
wipe file --path /path/to/file
```

`--stick-id` remains accepted by `wipe vault` as a compatibility alias for `--media-id`, but new commands should prefer `--media-id`.

## Target behavior

- `wipe stick` is for whole-device destructive operations intended for SUF-created LUKS stick workflows.
- `wipe stick` requires exactly one of `--fast` or `--full`, except for `--status`.
- `wipe stick` validates that the selected device exists before asking for exact-path confirmation.
- `wipe vault` works on any already-mounted media path and refuses destructive execution if `--mount` is not active.
- `wipe vault` supports `--full`.
- `wipe dir` and `wipe file` are best-effort only and do not accept `--fast` or `--full`.

## Manual output

```bash
wipe stick --path /dev/disk/by-id/... --fast --manual
wipe vault --media-id green --mount /media/green-stick --vault personal --manual
```

## Safety notes

- Read destructive plans carefully.
- Back up anything important first.
- Close KeePassXC, file managers, shells, and apps before wiping vault-related data.
- Treat a failed mount precondition as a safety stop, not as something to bypass with `--panic`.
