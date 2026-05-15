---
last updated: 2026-05-15
tags:
---
# Secure USB Factory — E2E runner developer tool

> [!summary]
> E2E tests are local battlefield checks for disposable hardware. The runner is a repository developer helper, not a packaged public CLI.

---

## Purpose

E2E scenarios verify that the packaged operator tools work together on real storage devices. They are intentionally closer to an operator rehearsal than to a unit test: they execute generated package commands, answer confirmation prompts, stream command output, and fail loudly when a step blocks or exits unexpectedly.

The runner itself lives in the source tree and is launched through Make targets. The tools under test must come from a package bin directory, normally:

```text
dist/suf/bin
```

Override the package bin directory with `SUF_E2E_TOOL_DIR` when testing another packaged artifact.

## Preconditions

E2E does not build packages and does not create local configuration automatically during a run.

Before running a scenario:

```bash
make e2e-config
# edit tests/e2e/e2e.env with disposable target values
make package
```

The runner verifies both prerequisites before executing scenario steps:

```text
tests/e2e/e2e.env exists
configured package bin directory exists
```

If the config is missing, the runner prints:

```text
E2E config not found: tests/e2e/e2e.env
Run `make e2e-config` first, then edit tests/e2e/e2e.env with disposable target values.
```

If the package bin is missing, the runner prints:

```text
Package not found: dist/suf/bin
Run `make package` first.
```

## Scenario model

Scenarios are small Python orchestration files under `tests/e2e/`. Each scenario declares the packaged tools it needs and then runs real commands through the configured package bin directory.

A scenario may be:

- a full destructive stick lifecycle;
- a vault lifecycle on a managed disposable stick;
- a bounded full-wipe check with a tiny vault;
- a vault-only check on already-mounted external media, such as a VeraCrypt-mounted volume;
- a grouped scenario that runs several smaller scenarios in order.

The exact step list belongs in code, not in this document. Keep this document focused on the contract: real devices, packaged tools, explicit configuration, bounded timeouts, and visible progress.

## Safety contract

E2E scenarios are allowed to destroy data on configured targets. Operators must use disposable media only.

The runner should preserve the same safety shape as the public tools:

- exact path confirmations stay exact;
- `YES` confirmations are answered only for the expected prompt;
- passphrases come from `tests/e2e/e2e.env` or exported `SUF_E2E_*` overrides;
- long-running steps print heartbeat messages;
- timeouts report the blocked command and suggest checking for hidden sudo, passphrase, busy mount, or storage prompts.

## Tool resolution

Scenario commands must resolve packaged tools like this:

```text
<SUF_E2E_TOOL_DIR or dist/suf/bin>/stick
<SUF_E2E_TOOL_DIR or dist/suf/bin>/vault
<SUF_E2E_TOOL_DIR or dist/suf/bin>/wipe
```

They must not substitute source-tree entrypoints, `uv run <tool>`, or `--help`-only checks for battlefield validation.

If a scenario-specific packaged tool is missing, that scenario may be skipped with a clear message. Missing package bin or missing E2E config is a preflight error.

## Configuration

`make e2e-config` copies `tests/e2e/e2e.env.example` to `tests/e2e/e2e.env` if it does not already exist.

The config provides disposable device identity, mount paths, vault names, vault sizes, passphrases, and optional external mounted-media values. Exported environment values may override file values for one-off runs.

## Make targets

Use Make targets as the stable interface. Typical targets include:

```text
make e2e-smoke
make e2e-stick
make e2e-vault
make e2e-vault-full-tiny
make e2e-mounted-media
make e2e-full
make e2e-all
```

Manual variants print the scenario procedure without running it.

## Documentation rule

Do not duplicate detailed step sequences here unless they are part of the runner contract. Scenario details evolve in `tests/e2e/`; this document explains the intent and mechanics that every scenario must respect.
