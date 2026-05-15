---
last updated: 2026-04-21
tags:
---
# Secure USB Factory — Stick requirements and public contract

> [!summary]
> Behavior contract for the `stick` CLI.

---

## Purpose

`stick` owns the outer managed-stick lifecycle only.

It is responsible for:

- creating a managed encrypted stick
- mounting a managed encrypted stick
- unmounting a managed encrypted stick
- reporting readiness and runtime state

It does not create, mount, unmount, or wipe inner vaults.

---

## Uniform flags

`stick` must support:

- `--help`, `-h`
- `--version`
- `--verbose`, `-V`
- `--manual`, `-M`

Where relevant it must also support:

- `--status`, `-S`
- `--dry-run`, `-D`

`--status` means readiness/status only and must not perform the main action.

`--dry-run` must print the concrete actions and prompts that would occur, without mutation.

`--manual` must print a manual operator procedure and equivalent commands, without mutation. A root-level `--manual` may print a command inventory and examples for the tool.

---

## Parameter model

Use:

- `--id`
- `--path`, `-p`

Examples:

```text
stick create --id green --path /dev/disk/by-id/...
stick mount --id green --path /dev/disk/by-id/...
stick mount --id green --path /dev/disk/by-id/... --status
stick unmount --id green
```

---

## Commands

Supported commands:

```text
stick create --id <id> --path <path>
stick mount --id <id> --path <path>
stick mount --id <id> --path <path> --status
stick unmount --id <id>
```

### `create`

Provision only.

It must not auto-mount the stick after creation.

### `mount`

Mount an already provisioned managed stick.

### `unmount`

Unmount and close the managed stick.

---

## Create semantics

Successful `stick create` must:

1. validate the target path
2. render plan or status when requested
3. require confirmation before mutation
4. partition the device
5. create the outer encrypted container
6. leave the stick provisioned but not mounted

---

## Mount semantics

Successful `stick mount` must:

1. validate the target path
2. resolve the outer encrypted partition/container
3. open the mapper
4. ensure the mount path exists
5. mount the outer filesystem

---


After a successful mount, `stick mount` should make the mount root writable by the current operator, equivalent to:

```bash
sudo chown "$USER":"$USER" /media/green-stick
```

This enables later `vault create` operations to create vault directories without running ordinary file creation as root.
## Unmount semantics

Successful `stick unmount` must:

1. unmount the outer filesystem
2. close the outer mapper
3. attempt to remove the mount directory if appropriate

If the stick is already unmounted and the mapper is already closed, `stick unmount` must return success and report that the stick was already unmounted.

If mount-directory cleanup fails because the directory is missing, busy, or not empty, the unmount operation still counts as success. The output must tell the operator which mount directory could not be removed.
