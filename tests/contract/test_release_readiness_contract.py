from __future__ import annotations

from pathlib import Path
import tomllib

from typer.testing import CliRunner

from forge.cli import app as forge_app
from usb_forge.validator import validate_generation_inputs
from usb_shared.config.schema import (
    ArtifactsConfig,
    AtomicScriptConfig,
    ForgeConfig,
    StickConfig,
    SufConfig,
)
from usb_shared.errors import ValidationError

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_DOCS = [ROOT / "README.md", *(ROOT / "docs").glob("*.md"), *((ROOT / "docs" / "runtime").glob("*.md")), *((ROOT / "docs" / "scenarios").glob("*.md"))]


def test_active_docs_use_scripts_not_wrapper_vocabulary() -> None:
    offenders: list[str] = []
    for path in ACTIVE_DOCS:
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("wrapper", "wrappers", "generated-wrappers"):
            if forbidden in text:
                offenders.append(f"{path.relative_to(ROOT)}: {forbidden}")
    assert offenders == []


def test_fast_help_and_forge_help_use_script_language() -> None:
    from usb_shared.entrypoint import _help_text

    fast_help = _help_text("forge")
    assert "Generate scripts and the artifact tree" in fast_help
    assert "wrapper" not in fast_help.lower()

    result = CliRunner().invoke(forge_app, ["--help"])
    assert result.exit_code == 0
    assert "script and artifact composition" in result.stdout.lower()
    assert "[bold yellow]" not in result.stdout


def test_public_script_validation_errors_do_not_say_wrapper() -> None:
    cfg = SufConfig(
        sticks={"blue": StickConfig(device_path="/dev/blue", purpose="test")},
        artifacts=ArtifactsConfig(),
        forge=ForgeConfig(
            {
                "bad": AtomicScriptConfig(
                    name="bad",
                    type="atomic",
                    tool="stick",
                    command="mount",
                    help="bad",
                    stick_id="missing",
                )
            }
        ),
    )

    try:
        validate_generation_inputs(cfg)
    except ValidationError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected validation failure")

    assert "script" in message.lower()
    assert "wrapper" not in message.lower()


def test_gitignore_excludes_generated_release_metadata() -> None:
    gitignore = ROOT / ".gitignore"
    assert gitignore.exists(), ".gitignore must be committed in the release tree"

    text = gitignore.read_text(encoding="utf-8")
    for pattern in ("*.egg-info/", ".pytest_cache/", ".ruff_cache/", "build/", "dist/"):
        assert pattern in text


def test_project_script_tables_explicitly_set_disabled_false() -> None:
    with (ROOT / "suf.toml").open("rb") as fh:
        raw = tomllib.load(fh)

    scripts = raw.get("forge", {}).get("scripts", {})
    assert scripts
    missing_or_enabled = [
        name
        for name, script in scripts.items()
        if "disabled" not in script or script["disabled"] is not False
    ]
    assert missing_or_enabled == []


def test_no_public_suf_dispatcher_source_tree() -> None:
    assert not (ROOT / "src" / "suf").exists()

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "suf =" not in pyproject
