# Secure USB Factory — Forge requirements

`forge` validates config and generates operator scripts.

It is a runtime composition tool, not the implementation source of truth for `stick`, `vault`, or `wipe` behavior.

## Commands

```bash
forge validate
forge inspect
forge generate
```

All commands support:

```bash
--manual
--verbose
```

`forge` does not build packages. `suf.toml` has two separate areas: `[forge.scripts.*]` for operator script generation, and `[package]` for `make package` / `tools/package.py`. Package building reads `[package].tools` and `[package].lib_layout`; forge only preserves the configured scripts into packaged `config/forge.toml`.

## Config

The active config shape is intentionally small:

- `[artifacts]` controls forge script output, manifest emission, and archive format.
- `[package]` controls package CLI entrypoints and runtime library layout for `make package`; forge validates it for reporting but does not build packages.
- `[sticks.<id>]` defines managed stick targets.
- `[sticks.<id>.vaults.<vault>]` defines vault metadata used by `vault` and `wipe vault` scripts.
- `[forge.scripts.<script-name>]` defines one operator script.

Every script table should set `disabled` explicitly. Use `disabled = false` for enabled scripts and `disabled = true` for scripts that should be validated but not generated.

In the source repo, forge normally reads:

```text
suf.toml
```

Inside a packaged artifact, forge reads:

```text
config/forge.toml
```

The packaged config contains target and script information. Packaged forge can validate, inspect, and regenerate scripts. It reuses the package runtime already built under `dist/suf/lib/` and does not rebuild Python libraries, PyInstaller binaries, or package archives.

## Validation output

`forge validate` must print a labeled validation summary.

Successful validation includes:

```text
Forge validation:
Config file: <path>
Result: OK
Scripts checked: <count>
Atomic scripts: <count>
Scenario scripts: <count>
Disabled scripts: <count>
Packages planned: <packages>
Output artifact: <path>
```

Failed validation must return non-zero and print:

```text
Forge validation:
Result: FAILED
Error: <specific error>
```

The error must be actionable. Examples include invalid config fields, missing references, script command errors, or missing config files.

## Inspection output

`forge inspect` must print a labeled generation plan.

The inspection output includes:

- config file path
- output artifact path
- library layout
- artifact archive format
- atomic script details
- scenario script details
- disabled scripts
- packages planned for `lib/`
- referenced targets

Atomic script details use this shape:

```text
- <name>: <tool> <command> target=<target> args=<args>
```

Scenario script details use this shape:

```text
- <name>: <count> step(s), stop-on-error=YES
```

The compact summary lines are kept at the end for easy scanning and backward compatibility with older tests/operator notes:

```text
Scripts generated: <names>
Scripts disabled: <names>
```

## Script disabling

Each script table uses an explicit disabled flag:

```toml
[forge.scripts.green-stick-mount]
type = "atomic"
disabled = false
tool = "stick"
command = "mount"
help = "Mount the configured green stick."
stick_id = "green"
```

Use `disabled = true` to keep a script in config while skipping generation. Disabled scripts are still validated and reported by `forge inspect`.


## Configured destructive scenarios

Forge config may define high-risk operator scenarios from existing `wipe` and `stick` primitives. The default `suf.toml` includes:

```toml
[forge.scripts.green-panic-destroy-all-fast]
type = "scenario"
disabled = false
help = "Panic-destroy the personal and work vaults if present or mounted, then panic-wipe the configured green stick. No confirmation prompts."
stop_on_error = true
steps = [
  { kind = "cli", tool = "wipe", command = ["vault"], stick_id = "green", vault = "personal", fixed_args = ["--fast", "--panic", "-V"] },
  { kind = "cli", tool = "wipe", command = ["vault"], stick_id = "green", vault = "work", fixed_args = ["--fast", "--panic", "-V"] },
  { kind = "cli", tool = "wipe", command = ["stick"], stick_id = "green", fixed_args = ["--fast", "--panic", "-V"] },
]

[forge.scripts.green-stick-recreate-with-confirmation]
type = "scenario"
disabled = false
help = "Recreate the configured green stick by first wiping existing partition data with confirmation, then creating a fresh encrypted stick."
stop_on_error = true
steps = [
  { kind = "cli", tool = "wipe", command = ["stick"], stick_id = "green", fixed_args = ["--fast", "-V"] },
  { kind = "cli", tool = "stick", command = ["create"], stick_id = "green", fixed_args = ["-V"] },
]
```

Scenario help must warn when any step performs a wipe operation.

## Output

`forge generate` writes operator scripts to the configured artifact output directory.

Operator scripts:

- bind configured target values
- call the current packaged or source CLI tools
- expose script-specific `--help` / `-h` output locally
- expose `--manual` for script/scenario manual command output

## Scenario scripts

Scenario scripts are ordered step sequences. They may call selected CLI tools and stop on error by default.

CLI scenario steps should prefer structured target fields over repeated raw argument arrays where possible:

```toml
steps = [
  { kind = "cli", tool = "stick", command = ["mount"], stick_id = "green" },
  { kind = "cli", tool = "vault", command = ["mount"], stick_id = "green", vault = "personal" },
]
```

Forge derives concrete command arguments such as `--path`, `--mount`, `--vault`, `--size`, and `--purpose` from the configured stick/vault metadata. Legacy raw `args` remain supported when a step truly needs explicit extra arguments.
