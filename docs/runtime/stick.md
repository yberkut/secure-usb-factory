# stick runtime guide

`stick` is the tool for the USB device itself.

Think of it as the front door to the stick. It creates, opens, checks, and closes the outer encrypted USB layer. You normally use it before working with any vaults stored on that stick.

## Common commands

```bash
stick create --id green --path /dev/disk/by-id/...
stick create --id green --path /dev/disk/by-id/... --status
stick mount --id green --path /dev/disk/by-id/...
stick mount --id green --path /dev/disk/by-id/... --status
stick unmount --id green
stick unmount --id green --status
```

## Manual output

Use `--manual` to print the equivalent commands you would run by hand:

```bash
stick mount --id green --path /dev/disk/by-id/... --manual
```

## Safety notes

- `stick create` is a destructive provisioning workflow. Read the plan before confirming.
- Prefer stable device paths under `/dev/disk/by-id/`.
- If the mounted stick is not writable, fix ownership with `sudo chown -R "$USER":"$USER" /media/<id>-stick`.
- `stick unmount` is idempotent: if the stick is already closed, it reports that and returns success.
- If empty mount-directory cleanup fails after unmount, remove the directory manually if needed.
