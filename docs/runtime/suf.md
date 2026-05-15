# Secure USB Factory runtime summary

Secure USB Factory helps you keep portable-storage vault workflows explicit and repeatable on Linux.

The core idea is simple:

1. choose a mounted media location
2. keep one or more encrypted vault image files on that media
3. keep one matching KeePassXC `*.kdbx` secret next to each vault image
4. use short commands or operator scripts for repeatable daily operations

## Where the media can come from

### SUF-created encrypted USB stick

Use `stick` when you want SUF to create, mount, check, or unmount the outer LUKS USB stick layer. This is the most integrated workflow.

### Existing plain USB stick or external drive

Mount it normally with your desktop or Linux tools. Then use `vault --media-id <id> --mount <path> ...` to place encrypted vaults on it. The media itself is not encrypted by SUF, but each vault image is encrypted.

### VeraCrypt or other encrypted media

Mount the VeraCrypt container/device with VeraCrypt first. Then point `vault` or `wipe vault` at the mounted path. SUF does not need to know how the outer media was mounted.

### Existing LUKS or other encrypted device

Open and mount it with your usual tools, then use `vault --media-id <id> --mount <path> ...` inside the mounted filesystem.

## Tool roles

- `stick` manages only SUF-created LUKS USB sticks.
- `vault` manages encrypted vault images on any already-mounted media.
- `wipe vault` removes managed vault data on any already-mounted media.
- `wipe stick` is for whole-device destructive operations intended for SUF stick workflows.
- `wipe dir` and `wipe file` are best-effort host filesystem cleanup helpers.
- `forge` validates config and generates operator scripts plus artifact trees.

## Safety reminders

- Check status before changing state.
- Read destructive plans carefully.
- Keep media IDs and vault basenames stable.
- Keep each matching KeePassXC secret complete enough to recover the vault later.
