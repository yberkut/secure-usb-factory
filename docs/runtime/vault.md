# vault runtime guide

`vault` creates, mounts, unmounts, and checks encrypted vault image files on any already-mounted media.

The mounted media can be a SUF-created stick, a plain USB drive, a mounted VeraCrypt volume, or another mounted encrypted filesystem. `vault` only needs a stable media ID and the mounted path.

## Common commands

```bash
vault create --media-id green --mount /media/green-stick --vault personal --size 256M --purpose "personal data"
vault create --media-id veracrypt1 --mount /media/veracrypt1 --vault personal --status
vault mount --media-id plain-usb --mount /media/plain-usb --vault personal
vault mount --media-id green --mount /media/green-stick --vault personal --keepass
vault unmount --media-id green --vault personal
vault unmount --media-id green --vault personal --status
```

`--stick-id` remains accepted as a compatibility alias for `--media-id`, but new commands should prefer `--media-id`.

## Manual output

```bash
vault mount --media-id green --mount /media/green-stick --vault personal --manual
```

## Safety notes

- The media path must already be mounted before creating or mounting a vault.
- `vault create` creates the encrypted image but does not create the KeePassXC secret for you.
- If `vault create` fails after creating an image, it closes any mapper it opened and removes the partial image when safe. If cleanup fails, it reports the exact partial image path to remove manually.
- Keep the image and secret basenames matched, for example `personal.img` and `personal.kdbx`.
- `vault mount --keepass` opens the matching `.kdbx` when present, falls back to opening the vault directory, then waits for Enter before opening the vault image.
- Plain `vault mount` does not open KeePassXC or a file manager.
- Close apps and shells using the vault before unmounting.
- `vault unmount` is idempotent: if the vault is already closed, it reports that and returns success.
- If empty mount-directory cleanup fails after unmount, remove the directory manually if needed.
