# Security policy

This project handles encrypted removable-media workflows and destructive wipe commands.

## Reporting vulnerabilities

Open a private report if your hosting platform supports it, or contact the maintainer directly. Do not include passphrases, recovery keys, full hardware serials, or sensitive mount paths in public issues.

## Operator safety

- Use disposable media for E2E tests.
- Read every destructive prompt.
- Treat `--panic` as immediate destructive mode.
- Keep generated packages and configs out of untrusted hands when they contain real device paths.
