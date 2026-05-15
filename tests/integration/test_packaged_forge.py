from __future__ import annotations

from tests.integration.package_support import PACKAGE


def test_packaged_forge_generation_works(generated_scripts: None) -> None:
    assert (PACKAGE / "generated-scripts" / "green-stick-mount").exists()
