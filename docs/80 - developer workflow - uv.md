---
last updated: 2026-05-03
tags:
---
# Secure USB Factory — Developer workflow

## Bootstrap

```bash
chmod +x ./tools/*.sh
make bootstrap
```

Bootstrap creates or updates `.venv` by running:

```bash
uv sync --extra dev --extra lint --extra build --index-url https://pypi.org/simple
```

It does not activate your current shell. A child process cannot activate its parent shell. Use Make targets directly, or activate manually for an interactive session:

```bash
source .venv/bin/activate
```

Set `UV_INDEX_URL` to use another package index intentionally.

## Tests and lint

```bash
make quick
make check
make smoke
make unit
make integration
make test
make test-quiet
make lint
make clean
make clean-package
make clean-test-artifacts
```

Make targets run through `uv run`; they do not require an activated shell.

`make quick` runs Python compile checks and current public CLI contract tests.

`make check` is the local pre-archive gate. It cleans generated artifacts, runs compile checks, runs contract tests, builds the configured package, checks package sanity, and removes package output again. It intentionally does not run integration tests yet.

`make smoke` runs smoke tests only.

`make unit` runs smoke and unit tests.

`make integration` runs automated repo-local integration tests, including package generation and packaged forge behavior. Integration is intentionally separate from `make check`.

Focused integration targets are available when diagnosing failures:

```bash
make integration-package
make integration-packaged-cli
make integration-packaged-forge
make integration-scripts
```

All integration targets set a deterministic test environment by default:

```text
SHELL=/bin/bash
PYTHONPATH=<repo source package paths>
SUF_INTEGRATION_TIMEOUT=30
```

Override the runner or timeout when needed:

```bash
make integration PYTEST="uv run --extra dev python -m pytest"
make integration-packaged-forge INTEGRATION_TIMEOUT=60
```

`make test` runs the full pytest suite.

E2E scenarios are developer diagnostics. Use `make e2e-config` once, run `make package`, then use `make e2e-smoke`, `make e2e-stick`, `make e2e-vault`, `make e2e-mounted-media`, or `make e2e-full`. E2E runs packaged tools from `dist/suf/bin` or `SUF_E2E_TOOL_DIR`; it does not build the package for you.

## VM or SSH package-index issues

If dependency downloads fail through an unreachable mirror, run:

```bash
UV_HTTP_TIMEOUT=600 UV_HTTP_RETRIES=10 \
uv sync --extra dev --extra lint --extra build --index-url https://pypi.org/simple
```

Inspect inherited package-index settings with:

```bash
env | grep -E 'UV_|PIP_|HTTP|HTTPS|NO_PROXY'
pip config list 2>/dev/null || true
cat ~/.config/uv/uv.toml 2>/dev/null || true
cat uv.toml 2>/dev/null || true
```


## Local gates

Use the fast gate while editing:

```bash
make quick
```

Use the pre-archive gate before packaging a handoff archive:

```bash
make check
```

`make check` runs:

```text
make clean
make compile-check
make contract
make package
make package-sanity
make clean-package
```

`make package` calls `tools/package.py` through `uv run --extra build`. `make package-sanity` checks the existing `dist/suf` package. Use `make bootstrap` when dependencies need to be installed or refreshed.

Integration tests stay explicit for now:

```bash
make integration
```

Package/forge integration coverage is split into smaller focused files under `tests/integration/`: package layout, packaged CLI behavior, packaged forge generation, and operator script behavior.

Run the focused targets when narrowing a failure:

```bash
make integration-package
make integration-packaged-cli
make integration-packaged-forge
make integration-scripts
```

`make integration` and the focused integration targets use short pytest tracebacks by default. Pass `PYTEST_SHORT=""` for full tracebacks.


## Current public CLI contract

The active public command families are:

```text
stick
vault
wipe
forge
```

Retired command families must not be reintroduced in docs, tests, scripts, or package behavior:

```text
manager
builder
eraser
```

Use `docs/25 - public CLI contract.md` for the quick command-family map before adding new contract tests or examples.

## Cleanup

```bash
make clean-package
make clean-test-artifacts
make clean
```

`make clean-package` removes generated package output and package build workspaces:

```text
build/
dist/
```

`make clean-test-artifacts` removes local test/tool caches:

```text
.pytest_cache/
.ruff_cache/
__pycache__/
```

`make clean` runs both cleanup targets.

## Package builds

```bash
make package
```

`make package` uses `[package].tools` from `suf.toml` to choose packaged CLI entrypoints. The default package includes `stick`, `vault`, `wipe`, and `forge`. `lab` is source-tree development tooling and is not packaged.

The package output path remains `dist/suf`. Runtime docs are copied only for packaged tools. `[package]` is source-tree package-build configuration only. It is not copied into packaged `config/forge.toml`.

The runtime under `dist/suf/lib/` follows `[package].lib_layout` from `suf.toml`:

- `tree` copies Python package source trees for inspection.
- `executable` builds one PyInstaller executable per selected package tool, for example `dist/suf/lib/stick` and `dist/suf/lib/forge`.

Package builds clean generated `build/` and `dist/` before running.

The package/forge integration test removes generated `build/` and `dist/` paths before and after itself.

## Runtime package docs

Package output contains runtime docs only:

```text
dist/suf/docs/<tool>.md
```

Tool docs are copied only for selected tools.

## Packaged forge config

When `forge` is selected, package output contains:

```text
dist/suf/config/forge.toml
```

Packaged `forge` uses this config to validate, inspect, and regenerate scripts only. It reuses the runtime already present under `dist/suf/lib/`. Full package rebuilding remains a repository task handled by `make package`.
