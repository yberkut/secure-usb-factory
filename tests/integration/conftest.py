from __future__ import annotations

import shutil
import sys

import pytest

from tests.integration.package_support import PACKAGE, ROOT, run


@pytest.fixture(scope="session")
def packaged_tree() -> None:
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    run([sys.executable, "tools/package.py"])
    try:
        yield
    finally:
        shutil.rmtree(ROOT / "build", ignore_errors=True)
        shutil.rmtree(ROOT / "dist", ignore_errors=True)


@pytest.fixture(scope="session")
def generated_scripts(packaged_tree: None) -> None:
    forge_result = run(["./forge", "generate", "--verbose"], cwd=PACKAGE / "bin")
    assert "Generation result: OK" in forge_result.stdout
