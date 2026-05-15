from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "suf.toml"
VERSION_FILE = ROOT / "packages/usb_shared/src/usb_shared/version.py"


def _project_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("VERSION = "):
            return line.split("=", 1)[1].strip().strip("\"")
    raise SystemExit(f"Could not read project version from: {VERSION_FILE}")


PACKAGE_TOOLS = ["stick", "vault", "wipe", "forge"]

TOOL_MODULES = {
    "stick": "stick.cli",
    "vault": "vault.cli",
    "wipe": "wipe.cli",
    "forge": "forge.cli",
}
PACKAGE_PATHS = {
    "src": ROOT / "src",
    "usb_shared": ROOT / "packages/usb_shared/src",
    "usb_linux": ROOT / "packages/usb_linux/src",
    "usb_stick": ROOT / "packages/usb_stick/src",
    "usb_vault": ROOT / "packages/usb_vault/src",
    "usb_wipe": ROOT / "packages/usb_wipe/src",
    "usb_forge": ROOT / "packages/usb_forge/src",
}
TOOL_PACKAGES = {
    "stick": ["usb_stick"],
    "vault": ["usb_vault"],
    "wipe": ["usb_wipe"],
    "forge": ["usb_forge"],
}

# Tree-layout packages are source bundles, not installed wheels.  They must carry
# the Python runtime libraries used by the CLIs, otherwise dist/suf/bin/<tool>
# only works on developer machines whose system python already has those libs.
RUNTIME_IMPORTS = [
    "annotated_doc",
    "click",
    "markdown_it",
    "mdurl",
    "pygments",
    "rich",
    "shellingham",
    "typer",
    "typing_extensions",
]

RUNTIME_DOCS = {
    "stick": ROOT / "docs/runtime/stick.md",
    "vault": ROOT / "docs/runtime/vault.md",
    "wipe": ROOT / "docs/runtime/wipe.md",
    "forge": ROOT / "docs/runtime/forge.md",
}


def _env_package_tools() -> list[str] | None:
    raw = os.environ.get("SUF_PACKAGE_TOOLS")
    if raw is None:
        return None
    tools = [item.strip() for item in raw.split(",") if item.strip()]
    if not tools:
        raise SystemExit("SUF_PACKAGE_TOOLS must name at least one package tool.")
    return tools


def _load_package_config() -> dict:
    # Packaging keeps stable output defaults and uses the configured package
    # table for packaged CLI tools and library layout. Test and review tooling may
    # override these values through explicit SUF_PACKAGE_* environment variables
    # so integration tests do not depend on an operator's local package choices.
    with CONFIG_PATH.open("rb") as fh:
        raw = tomllib.load(fh)
    artifacts = raw.get("artifacts", {})
    package = raw.get("package", {})
    lib_layout = os.environ.get("SUF_PACKAGE_LIB_LAYOUT") or package.get("lib_layout", "tree")
    if lib_layout not in {"tree", "executable"}:
        raise SystemExit("package.lib_layout must be 'tree' or 'executable'.")
    return {
        "tools": _env_package_tools() or list(package.get("tools", PACKAGE_TOOLS)),
        "output_dir": "dist/suf",
        "lib_layout": lib_layout,
        "include_manifest": bool(artifacts.get("include_manifest", True)),
    }


def _needed_source_cli_names(tools: list[str]) -> list[str]:
    requested = set(tools)
    return [name for name in PACKAGE_TOOLS if name in requested]


def _needed_package_keys(tools: list[str]) -> list[str]:
    keys = ["usb_shared", "usb_linux"]
    for tool in tools:
        for package in TOOL_PACKAGES.get(tool, []):
            if package not in keys:
                keys.append(package)
    return keys


def _copy_tree(src: Path, dst: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".ruff_cache", "*.egg-info")
    shutil.copytree(src, dst, ignore=ignore)


def _copy_runtime_import(import_name: str, vendor_dir: Path) -> None:
    spec = importlib.util.find_spec(import_name)
    if spec is None or spec.origin is None:
        raise SystemExit(
            f"Package tree layout requires importable runtime dependency: {import_name}. "
            "Run `uv sync --extra dev --extra lint --extra build` first."
        )
    if spec.origin == "built-in":
        return
    origin = Path(spec.origin)
    if origin.name == "__init__.py":
        src = origin.parent
        dst = vendor_dir / src.name
        if dst.exists():
            return
        _copy_tree(src, dst)
        return
    dst = vendor_dir / origin.name
    if not dst.exists():
        shutil.copy2(origin, dst)


def _copy_runtime_metadata(import_name: str, vendor_dir: Path) -> None:
    spec = importlib.util.find_spec(import_name)
    if spec is None or spec.origin is None or spec.origin == "built-in":
        return
    origin = Path(spec.origin)
    search_dir = origin.parent.parent if origin.name == "__init__.py" else origin.parent
    normalized = import_name.replace("_", "-").lower()
    for metadata in search_dir.iterdir():
        if not metadata.name.endswith((".dist-info", ".egg-info")):
            continue
        meta_name = metadata.name.split("-", 1)[0].replace("_", "-").lower()
        if meta_name != normalized:
            continue
        dst = vendor_dir / metadata.name
        if dst.exists():
            continue
        if metadata.is_dir():
            _copy_tree(metadata, dst)
        else:
            shutil.copy2(metadata, dst)


def _copy_runtime_dependencies(output: Path) -> None:
    vendor_dir = output / "lib" / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    for import_name in RUNTIME_IMPORTS:
        _copy_runtime_import(import_name, vendor_dir)
        _copy_runtime_metadata(import_name, vendor_dir)


def _write_tree_package(output: Path, tools: list[str]) -> None:
    lib_dir = output / "lib"
    bin_dir = output / "bin"
    lib_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    src_dir = lib_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    for name in _needed_source_cli_names(tools):
        _copy_tree(ROOT / "src" / name, src_dir / name)
    package_keys = _needed_package_keys(tools)
    for key in package_keys:
        _copy_tree(PACKAGE_PATHS[key], lib_dir / key)
    _copy_runtime_dependencies(output)
    pythonpath_keys = ["vendor", "src", *package_keys]
    pythonpath = ":".join(f'$ROOT_DIR/lib/{key}' for key in pythonpath_keys)
    for tool in tools:
        module = TOOL_MODULES[tool]
        script = bin_dir / tool
        script.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"\n'
            f'export PYTHONPATH="{pythonpath}"\n'
            'export SUF_FORGE_CONFIG="${SUF_FORGE_CONFIG:-$ROOT_DIR/config/forge.toml}"\n'
            'export USB_FACTORY_PACKAGE_ROOT="${USB_FACTORY_PACKAGE_ROOT:-$ROOT_DIR}"\n'
            'export PYTHONDONTWRITEBYTECODE=1\n'
            'export SHELL="${SHELL:-/bin/bash}"\n'
            'if [[ "${1:-}" =~ ^--(show|install)-completion$ && "${2:-}" =~ ^(bash|zsh|fish|powershell|pwsh)$ ]]; then\n'
            '  export _TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION=1\n'
            'fi\n'
            + f'exec python3 -m {module} "$@"\n',
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | 0o111)


def _tool_runtime_script(tool: str) -> str:
    module = TOOL_MODULES[tool]
    return f"""from __future__ import annotations

from {module} import app


def main() -> int:
    app(prog_name={tool!r})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _write_tool_executable(output: Path, tool: str, package_keys: list[str]) -> Path:
    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit(
            "Executable lib_layout requires PyInstaller. "
            "Install the build extra first: "
            "UV_HTTP_TIMEOUT=600 UV_HTTP_RETRIES=10 "
            "uv sync --extra dev --extra lint --extra build --index-url https://pypi.org/simple"
        )
    build_root = output / ".pyinstaller" / tool
    script = build_root / f"{tool}_runtime.py"
    dist_dir = output / "lib"
    work_dir = build_root / "work"
    spec_dir = build_root / "spec"
    build_root.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)
    script.write_text(_tool_runtime_script(tool), encoding="utf-8")

    pythonpath = os.pathsep.join(str(PACKAGE_PATHS[key]) for key in package_keys)
    env = dict(os.environ)
    env["PYTHONPATH"] = pythonpath + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        tool,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        str(script),
    ]
    try:
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    except FileNotFoundError as exc:
        raise SystemExit("Executable lib_layout requires a working Python interpreter and PyInstaller.") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"PyInstaller failed while building dist/suf/lib/{tool}.") from exc
    executable = dist_dir / tool
    if not executable.exists():
        raise SystemExit(f"PyInstaller completed but dist/suf/lib/{tool} was not created.")
    executable.chmod(executable.stat().st_mode | 0o111)
    return executable


def _write_executable_runtime(output: Path, tools: list[str]) -> None:
    package_keys = _needed_package_keys(tools)
    for tool in tools:
        _write_tool_executable(output, tool, package_keys)
    shutil.rmtree(output / ".pyinstaller", ignore_errors=True)


def _write_executable_package(output: Path, tools: list[str]) -> None:
    bin_dir = output / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    _write_executable_runtime(output, tools)
    for tool in tools:
        script = bin_dir / tool
        script.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"\n'
            'export SUF_FORGE_CONFIG="${SUF_FORGE_CONFIG:-$ROOT_DIR/config/forge.toml}"\n'
            'export USB_FACTORY_PACKAGE_ROOT="${USB_FACTORY_PACKAGE_ROOT:-$ROOT_DIR}"\n'
            'export PYTHONDONTWRITEBYTECODE=1\n'
            'export SHELL="${SHELL:-/bin/bash}"\n'
            'if [[ "${1:-}" =~ ^--(show|install)-completion$ && "${2:-}" =~ ^(bash|zsh|fish|powershell|pwsh)$ ]]; then\n'
            '  export _TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION=1\n'
            'fi\n'
            + f'exec "$ROOT_DIR/lib/{tool}" "$@"\n',
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | 0o111)


def _copy_runtime_docs(output: Path, tools: list[str]) -> None:
    docs_dir = output / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for tool in tools:

        src = RUNTIME_DOCS.get(tool)
        if src is None:
            raise SystemExit(f"No runtime documentation registered for tool: {tool}")
        if not src.exists():
            raise SystemExit(f"Missing runtime documentation for {tool}: {src}")
        shutil.copy2(src, docs_dir / f"{tool}.md")


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"



def _write_packaged_forge_config(output: Path, tools: list[str]) -> None:
    if "forge" not in tools:
        return
    with CONFIG_PATH.open("rb") as fh:
        raw = tomllib.load(fh)
    config_dir = output / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "[artifacts]",
        'output_dir = "generated-scripts"',
        f"include_manifest = {str(raw.get('artifacts', {}).get('include_manifest', True)).lower()}",
        'archive_format = "none"',
        "",
    ]

    for stick_id, stick in sorted(raw.get("sticks", {}).items()):
        lines.extend([
            f"[sticks.{stick_id}]",
            f"device_path = {_toml_string(stick['device_path'])}",
            f"purpose = {_toml_string(stick.get('purpose', ''))}",
            "",
        ])
        for vault_name, vault in sorted(stick.get("vaults", {}).items()):
            lines.extend([
                f"[sticks.{stick_id}.vaults.{vault_name}]",
                f"size = {_toml_string(vault['size'])}",
                f"purpose = {_toml_string(vault['purpose'])}",
                "",
            ])

    for script_id, script in sorted(raw.get("forge", {}).get("scripts", {}).items()):
        lines.append(f"[forge.scripts.{script_id}]")
        for key in ("type", "tool", "command", "help", "stick_id", "vault"):
            if key in script:
                lines.append(f"{key} = {_toml_string(script[key])}")
        if "stop_on_error" in script:
            lines.append(f"stop_on_error = {str(script['stop_on_error']).lower()}")
        lines.append(f"disabled = {str(script.get('disabled', False)).lower()}")
        if "fixed_args" in script:
            lines.append(f"fixed_args = {_toml_array(list(script['fixed_args']))}")
        if "steps" in script:
            step_items = []
            for step in script["steps"]:
                parts = []
                for key in ("kind", "tool", "module", "callable", "path", "stick_id", "vault"):
                    if key in step:
                        parts.append(f"{key} = {_toml_string(step[key])}")
                for key in ("command", "args", "fixed_args"):
                    if key in step:
                        parts.append(f"{key} = {_toml_array(list(step[key]))}")
                step_items.append("{ " + ", ".join(parts) + " }")
            lines.append("steps = [")
            for item in step_items:
                lines.append(f"  {item},")
            lines.append("]")
        lines.append("")

    (config_dir / "forge.toml").write_text("\n".join(lines), encoding="utf-8")

def _write_manifest(output: Path, cfg: dict) -> None:
    manifest = {
        "version": _project_version(),
        "layout": cfg["lib_layout"],
        "tools": cfg["tools"],
        "runtime_docs": [f"docs/{tool}.md" for tool in cfg["tools"]],
        "forge_config": "config/forge.toml" if "forge" in cfg["tools"] else None,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + os.linesep, encoding="utf-8")


def main() -> int:
    cfg = _load_package_config()
    tools = list(cfg["tools"])
    unknown = sorted(set(tools) - set(PACKAGE_TOOLS))
    if unknown:
        raise SystemExit(f"Unknown package tools: {', '.join(unknown)}")
    if len(tools) != len(set(tools)):
        raise SystemExit("Package tools must not contain duplicates.")

    output = ROOT / cfg["output_dir"]
    # Clean generated build roots before packaging so stale files cannot mix with new output.
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    output.mkdir(parents=True, exist_ok=True)

    if cfg["lib_layout"] == "executable":
        _write_executable_package(output, tools)
    else:
        _write_tree_package(output, tools)
    _copy_runtime_docs(output, tools)
    _write_packaged_forge_config(output, tools)
    if cfg["include_manifest"]:
        _write_manifest(output, cfg)
    print(f"Built package at: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
