---
last updated: 2026-05-03
tags:
---
# Secure USB Factory — Operator workflow

## Working model

- one SUF-created stick is identified by Stick ID
- vaults are identified by media ID plus vault basename
- one or more vault image files can live on the mounted stick
- each vault has a matching KeePassXC `*.kdbx` secret file

## Daily commands

```bash
stick mount --id green --path /dev/disk/by-id/<DEVICE_ID>
vault mount --media-id green --mount /media/green-stick --vault personal
vault unmount --media-id green --mount /media/green-stick --vault personal
stick unmount --id green
```

Use `--status` before guessing:

```bash
stick mount --id green --path /dev/disk/by-id/<DEVICE_ID> --status
vault mount --media-id green --mount /media/green-stick --vault personal --status
wipe vault --media-id green --mount /media/green-stick --vault personal --status
```

Use `--manual` to print equivalent operator commands without mutation:

```bash
stick --manual
vault --manual
wipe --manual
forge --manual
```

## Creation

```bash
stick create --id green --path /dev/disk/by-id/<DEVICE_ID>
vault create --media-id green --mount /media/green-stick --vault personal --size 256M --purpose "personal data"
```

## Wiping

```bash
wipe stick --path /dev/disk/by-id/<DEVICE_ID> --fast
wipe stick --path /dev/disk/by-id/<DEVICE_ID> --full
wipe vault --media-id green --mount /media/green-stick --vault personal
wipe dir --path /path/to/target
wipe file --path /path/to/file
```

`wipe dir` and `wipe file` are best-effort operations and do not accept `--fast` or `--full`.

## Mounted stick ownership

If vault creation fails with `Permission denied` under `/media/<id>-stick`, repair ownership after mounting:

```bash
sudo chown -R "$USER":"$USER" /media/green-stick
find /media/green-stick -type d -exec chmod 700 {} \;
find /media/green-stick -type f -exec chmod 600 {} \;
```

## Packaging

Build the configured package from the repository:

```bash
make package
```

The package contains selected CLIs under `bin/`, runtime support under `lib/`, runtime docs under `docs/`, and, when `forge` is selected, runtime forge config under `config/forge.toml`.

Package builds clean generated `build/` and `dist/` output before running. `[package].tools` selects the packaged CLI entrypoints. The runtime under `dist/suf/lib/` follows `[package].lib_layout`: `tree` copies Python package trees; `executable` writes one PyInstaller executable per selected tool, such as `dist/suf/lib/stick` and `dist/suf/lib/forge`. Packaged `forge` can regenerate operator scripts but does not rebuild those runtime executables.


## Operator scripts

Operator scripts are generated from `[forge.scripts.<script-name>]` tables in `suf.toml`. Each configured script should set `disabled = false` explicitly when enabled. Set `disabled = true` to keep a script validated but skip executable generation.

Generate scripts from the repository with:

```bash
forge validate
forge inspect
forge generate
```

The default source-tree output path is configured in `[artifacts].output_dir`, currently `build/scripts`.
