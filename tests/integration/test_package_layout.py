from __future__ import annotations

import tomllib

from tests.integration.package_support import PACKAGE, ROOT


def test_tree_package_layout_does_not_create_build_workspace(packaged_tree: None) -> None:
    assert PACKAGE.exists()
    assert not (ROOT / "build").exists()


def test_packaged_tools_docs_and_config_exist(packaged_tree: None) -> None:
    for tool in ["stick", "vault", "wipe", "forge"]:
        assert (PACKAGE / "bin" / tool).exists()
    assert not (PACKAGE / "bin" / "lab").exists()

    assert (PACKAGE / "config" / "forge.toml").exists()


def test_packaged_forge_config_preserves_structured_scenario_fields(packaged_tree: None) -> None:
    config_path = PACKAGE / "config" / "forge.toml"
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    steps = data["forge"]["scripts"]["green-vault-personal-open-session"]["steps"]

    assert steps[0]["stick_id"] == "green"
    assert steps[1]["stick_id"] == "green"
    assert steps[1]["vault"] == "personal"
    assert "args" not in steps[0]
    assert "args" not in steps[1]
    assert "package" not in data


def test_packaged_forge_config_preserves_new_destructive_scenarios(packaged_tree: None) -> None:
    config_path = PACKAGE / "config" / "forge.toml"
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    scripts = data["forge"]["scripts"]

    panic = scripts["green-panic-destroy-all-fast"]
    assert panic["type"] == "scenario"
    assert panic["steps"][0]["tool"] == "wipe"
    assert panic["steps"][0]["command"] == ["vault"]
    assert panic["steps"][0]["vault"] == "personal"
    assert panic["steps"][0]["fixed_args"] == ["--fast", "--panic", "-V"]
    assert panic["steps"][1]["tool"] == "wipe"
    assert panic["steps"][1]["command"] == ["vault"]
    assert panic["steps"][1]["vault"] == "work"
    assert panic["steps"][1]["fixed_args"] == ["--fast", "--panic", "-V"]
    assert panic["steps"][2]["tool"] == "wipe"
    assert panic["steps"][2]["command"] == ["stick"]
    assert panic["steps"][2]["fixed_args"] == ["--fast", "--panic", "-V"]

    recreate = scripts["green-stick-recreate-with-confirmation"]
    assert recreate["type"] == "scenario"
    assert recreate["steps"][0]["tool"] == "wipe"
    assert recreate["steps"][0]["fixed_args"] == ["--fast", "-V"]
    assert recreate["steps"][1]["tool"] == "stick"
    assert recreate["steps"][1]["command"] == ["create"]
    assert recreate["steps"][1]["fixed_args"] == ["-V"]


def test_packaged_e2e_scenarios_are_not_packaged(packaged_tree: None) -> None:
    assert not (PACKAGE / "tests" / "e2e").exists()
