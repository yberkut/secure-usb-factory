---
last updated: 2026-04-21
tags:
---
# Secure USB Factory — Vault requirements and public contract

> [!summary]
> Behavior contract for the `vault` CLI.

---

## Purpose

`vault` owns vault lifecycle only.

It is responsible for:

- creating a vault inside an already mounted media filesystem
- mounting a vault
- unmounting a vault
- reporting readiness and runtime state
- optionally opening the matching KeePassXC database helper flow before mounting

It does not own the outer media lifecycle. Use `stick` only for SUF-created LUKS sticks, and mount plain, VeraCrypt, or other encrypted media before using `vault`.

---

## Uniform flags

`vault` must support:

- `--help`, `-h`
- `--version`
- `--verbose`, `-V`
- `--manual`, `-M`

Where relevant it must also support:

- `--status`, `-S`
- `--dry-run`, `-D`

---

## Parameter model

Use:

- `--media-id`, `-s`
- `--stick-id` as a compatibility alias for `--media-id`
- `--mount`, `-m`
- `--vault`, `-v`
- `--keepass`, `-k`

Examples:

```text
vault create --media-id green --mount /media/green-stick --vault personal --size 8G --purpose "personal"
vault mount --media-id green --mount /media/green-stick --vault personal
vault mount --media-id green --mount /media/green-stick --vault personal --keepass
vault mount --media-id green --mount /media/green-stick --vault personal --status
vault unmount --media-id green --vault personal
```

---

## Commands

Supported commands:

```text
vault create --media-id <id> --mount <path> --vault <basename> --size <size> --purpose <text>
vault mount --media-id <id> --mount <path> --vault <basename>
vault mount --media-id <id> --mount <path> --vault <basename> --status
vault unmount --media-id <id> --vault <basename>
```

---

## Create semantics

Successful `vault create` must:

1. validate the media mount path
2. derive canonical names and paths from media-id and vault basename
3. render plan or status when requested
4. require confirmation before mutation
5. create the vault directory if needed
6. create the encrypted vault container file
7. format and initialize the vault
8. leave the vault created
9. not auto-create the matching `.kdbx`

The `.kdbx` remains a manual operator step.

---


### Mounted media ownership precondition

`vault create` requires the provided media mount path to be writable by the current operator. If the mounted media is owned by `root`, the command must fail before mutation with an actionable ownership repair hint, for example:

```bash
sudo chown -R "$USER":"$USER" /media/green-stick
find /media/green-stick -type d -exec chmod 700 {} \;
find /media/green-stick -type f -exec chmod 600 {} \;
```

The tool should not silently create vault directories in a root-owned mounted media tree.

### Partial-artifact cleanup

If `vault create` fails after creating the vault image, the command must make recovery explicit.

Expected failure cleanup behavior:

1. close the vault mapper if this run opened it
2. remove the partial vault image if this run created it
3. never remove a pre-existing vault image
4. report cleanup success or failure clearly

Recommended output when cleanup succeeds:

```text
Vault creation failed.
Removed partial vault image: /media/green-stick/personal/personal.img
```

Recommended output when cleanup fails:

```text
Vault creation failed.
Partial vault image may remain: /media/green-stick/personal/personal.img
Remove it manually if needed.
```

## Mount semantics

Successful `vault mount` must:

1. validate the media mount path
2. locate the vault container file
3. optionally perform the KeePass helper flow when `--keepass` is provided
4. open the vault mapper
5. mount the vault filesystem

### KeePass helper flow

When `vault mount ... --keepass` is used, the command must:

1. try to open the matching `<vault>.kdbx` secret
2. fall back to opening the containing vault directory when the secret is not present
3. pause and wait for the operator to press Enter
4. continue with opening and mounting the vault image

The pause prompt should identify the image that will be opened next, for example:

```text
Press Enter when ready to open personal.img...
```

Plain `vault mount` without `--keepass` must not open KeePassXC, a file manager, or any secret-related UI.

---

## Unmount semantics

Successful `vault unmount` must:

1. unmount the vault filesystem
2. close the vault mapper
3. leave the media mount untouched
4. attempt to remove the empty vault mount directory if appropriate

If the vault is already unmounted and the mapper is already closed, `vault unmount` must return success and report that the vault was already unmounted.

If mount-directory cleanup fails because the directory is missing, busy, or not empty, the unmount operation still counts as success. The output must tell the operator which mount directory could not be removed.
