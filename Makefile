UV ?= uv
PYTHON ?= python
PYTEST ?= $(UV) run --extra dev $(PYTHON) tools/pytest_runner.py
PYTEST_SHORT ?= -q --tb=short
INTEGRATION_TIMEOUT ?= 30
REPO_PYTHONPATH := src:packages/usb_shared/src:packages/usb_linux/src:packages/usb_stick/src:packages/usb_vault/src:packages/usb_wipe/src:packages/usb_forge/src
TEST_ENV := SHELL=/bin/bash PYTHONPATH=$(REPO_PYTHONPATH) SUF_INTEGRATION_TIMEOUT=$(INTEGRATION_TIMEOUT) PYTHONDONTWRITEBYTECODE=1

.PHONY: bootstrap test test-quiet smoke unit contract integration integration-package integration-packaged-cli integration-packaged-forge integration-scripts e2e e2e-config e2e-smoke e2e-stick e2e-vault e2e-vault-full-tiny e2e-mounted-media e2e-full e2e-all e2e-fresh-stick e2e-vault-lifecycle e2e-smoke-manual e2e-stick-manual e2e-vault-manual e2e-mounted-media-manual e2e-full-manual package package-review compile-check package-sanity quick check fmt lint clean clean-package clean-test-artifacts

bootstrap:
	bash ./tools/bootstrap.sh

test:
	$(PYTEST)

test-quiet:
	$(PYTEST) -q

smoke:
	$(PYTEST) tests/smoke

contract:
	$(PYTEST) tests/contract

unit:
	$(PYTEST) tests/unit tests/smoke

integration:
	$(TEST_ENV) $(PYTEST) tests/integration $(PYTEST_SHORT)

integration-package:
	$(TEST_ENV) $(PYTEST) tests/integration/test_package_layout.py $(PYTEST_SHORT)

integration-packaged-cli:
	$(TEST_ENV) $(PYTEST) tests/integration/test_packaged_cli.py $(PYTEST_SHORT)

integration-packaged-forge:
	$(TEST_ENV) $(PYTEST) tests/integration/test_packaged_forge.py $(PYTEST_SHORT)

integration-scripts:
	$(TEST_ENV) $(PYTEST) tests/integration/test_generated_scripts.py $(PYTEST_SHORT)

e2e:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py --help

e2e-config:
	cp -n tests/e2e/e2e.env.example tests/e2e/e2e.env
	@echo "Created tests/e2e/e2e.env if it did not already exist."
	@echo "Edit it with disposable target values before running E2E scenarios."

e2e-smoke:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-smoke

e2e-stick:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-stick

e2e-vault:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-vault

e2e-vault-full-tiny:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-vault-full-tiny

e2e-mounted-media:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-mounted-media

e2e-full:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-full

e2e-all:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-all

# Backward-compatible aliases.
e2e-fresh-stick: e2e-stick

e2e-vault-lifecycle: e2e-vault

e2e-smoke-manual:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-smoke --manual

e2e-stick-manual:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-stick --manual

e2e-vault-manual:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-vault --manual

e2e-mounted-media-manual:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-mounted-media --manual

e2e-full-manual:
	$(UV) run --extra dev $(PYTHON) tools/e2e_runner.py e2e-full --manual

compile-check:
	$(UV) run $(PYTHON) tools/compile_check.py

package:
	$(UV) run --extra build $(PYTHON) tools/package.py

package-sanity:
	$(UV) run --extra build $(PYTHON) tools/package_sanity.py

package-review:
	$(UV) run --extra build $(PYTHON) tools/package_review.py

quick: compile-check contract

check:
	$(MAKE) clean
	$(MAKE) compile-check
	$(MAKE) contract
	$(MAKE) package
	$(MAKE) package-sanity
	$(MAKE) clean-package

fmt:
	$(UV) run --extra lint ruff format .
	$(UV) run --extra lint black .

lint:
	$(UV) run --extra lint ruff check .

clean: clean-package clean-test-artifacts

clean-package:
	rm -rf build dist

clean-test-artifacts:
	rm -rf .pytest_cache .ruff_cache *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
