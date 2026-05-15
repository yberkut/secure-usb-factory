# forge runtime guide

`forge` generates operator scripts from `config/forge.toml`.

Use it when you want short, repeatable commands such as `green-stick-mount` or `green-vault-personal-create` instead of typing the full `stick`, `vault`, or `wipe` command every time.

Packaged `forge` regenerates operator scripts only. It reuses the package runtime already built under `dist/suf/lib/` and does not rebuild Python libraries or PyInstaller binaries.

## Common commands

```bash
forge validate
forge inspect
forge generate
```

## Validate before generating

```bash
forge validate
```

Successful validation prints the config file, script counts, packages planned for `lib/`, and output artifact path.

Failed validation returns non-zero and prints a direct error:

```text
Forge validation:
Result: FAILED
Error: <specific error>
```

## Inspect the resolved plan

```bash
forge inspect
```

Inspection prints the resolved generation plan in sections:

- artifact layout
- atomic scripts
- scenario scripts
- disabled scripts
- packages planned for `lib/`
- referenced targets

Use this before `forge generate` when changing script config.

## Manual output

```bash
forge generate --manual
```

## Config location

In a packaged artifact, forge reads:

```text
config/forge.toml
```

That config contains the target, script, and runtime-layout information needed for operator script regeneration. Packaged forge reuses the existing runtime under `lib/`; it does not rebuild the package runtime.

## Destructive operator scenarios

The default config includes two high-risk scenario scripts for the configured green stick:

```bash
green-panic-destroy-all-fast
```

Panic flow. It first runs the configured personal and work vault wipes with `--fast --panic -V`, then runs the configured stick wipe with `--fast --panic -V`. It is intended for immediate destruction when a vault may still be mounted. It does not ask for confirmation prompts; use only against the configured disposable/target stick.

```bash
green-stick-recreate-with-confirmation
```

Recreate flow. It first runs `wipe stick --fast -V` for the configured stick, which requires the exact device path confirmation, then runs `stick create -V`, which asks for the normal creation confirmation and LUKS passphrases. Use this when an existing partition layout should be destroyed before provisioning a fresh encrypted stick.
