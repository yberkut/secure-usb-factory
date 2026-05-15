from __future__ import annotations

import subprocess

from tests.integration.package_support import PACKAGE, ROOT, run
from tests.support.cli_output import assert_cli_contains, normalized_cli_output


def test_packaged_stick_help_works(packaged_tree: None) -> None:
    help_result = run([str(PACKAGE / "bin" / "stick"), "--help"])
    assert_cli_contains(help_result.stdout, "Usage: stick")


def test_packaged_scripts_delegate_completion_to_typer(packaged_tree: None) -> None:
    script = PACKAGE / "bin" / "stick"
    text = script.read_text(encoding="utf-8")
    assert "--show-completion" not in text
    assert "--install-completion" not in text
    help_result = run([str(script), "--help"])
    assert_cli_contains(help_result.stdout, "--show-completion")
    assert_cli_contains(help_result.stdout, "--install-completion")


def test_packaged_tool_versions_work(packaged_tree: None) -> None:
    for tool in ("stick", "vault", "wipe", "forge"):
        result = run([str(PACKAGE / "bin" / tool), "--version"])
        assert result.stdout.strip() == f"{tool} 1.0.0"


def test_packaged_forge_help_renders_rich_markup(packaged_tree: None) -> None:
    result = run([str(PACKAGE / "bin" / "forge"), "--help"])
    assert_cli_contains(result.stdout, "Forge")
    assert "[bold yellow]" not in normalized_cli_output(result.stdout)
    assert "[/bold yellow]" not in normalized_cli_output(result.stdout)



def test_tree_packaged_tools_carry_python_runtime_dependencies(packaged_tree: None) -> None:
    vendor = PACKAGE / "lib" / "vendor"
    for name in ("annotated_doc", "click", "rich", "shellingham", "typer"):
        assert (vendor / name).exists()


def test_tree_packaged_forge_works_without_dev_python_path(packaged_tree: None) -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "SHELL": "/bin/bash",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [str(PACKAGE / "bin" / "forge"), "--version"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        timeout=30,
        check=True,
    )
    assert result.stdout.strip() == "forge 1.0.0"
