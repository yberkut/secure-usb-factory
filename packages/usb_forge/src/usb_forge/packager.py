from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from usb_shared.config.schema import AtomicScriptConfig, ScenarioStepConfig, ScenarioScriptConfig, SufConfig

from .planner import build_plan

ROOT_PACKAGE_MAP: dict[str, Path] = {
    "src": Path("src"),
    "usb_shared": Path("packages/usb_shared/src"),
    "usb_linux": Path("packages/usb_linux/src"),
    "usb_stick": Path("packages/usb_stick/src"),
    "usb_vault": Path("packages/usb_vault/src"),
    "usb_wipe": Path("packages/usb_wipe/src"),
    "usb_forge": Path("packages/usb_forge/src"),
}

MODULE_BY_TOOL = {
    "stick": "stick.cli",
    "vault": "vault.cli",
    "wipe": "wipe.cli",
    "forge": "forge.cli",
}

DEBUG_TOOL_BY_PACKAGE: dict[str, tuple[str, str]] = {
    "usb_stick": ("stick", "stick.cli"),
    "usb_vault": ("vault", "vault.cli"),
    "usb_wipe": ("wipe", "wipe.cli"),
    "usb_forge": ("forge", "forge.cli"),
}

@dataclass(frozen=True)
class RuntimeSpec:
    layout: str
    pythonpath_parts: list[str]
    executable_path: str = "lib/runtime"

    def py_path(self) -> str:
        return ":".join(f"$ROOT_DIR/{part}" for part in self.pythonpath_parts)


@dataclass(frozen=True)
class SkippedScript:
    name: str
    missing_tools: list[str]

    def render_notice(self) -> str:
        tools = ", ".join(self.missing_tools)
        return f"Skipped script: {self.name} (missing packaged tool: {tools})"


def _render_tool_exec(tool: str, runtime: RuntimeSpec) -> str:
    if runtime.layout == "executable":
        return f'"$ROOT_DIR/{runtime.executable_path}" {tool}'
    if runtime.layout == "package":
        return f'"$ROOT_DIR/{runtime.executable_path}/{tool}"'
    return f"python3 -m {MODULE_BY_TOOL[tool]}"


def _shell_quote(arg: str) -> str:
    return "'" + arg.replace("'", "'\"'\"'") + "'"


def _command_tokens(command: str) -> tuple[str, ...]:
    return tuple(part for part in command.split() if part)


def _has_option(args: list[str], option: str) -> bool:
    return any(arg == option or arg.startswith(f"{option}=") for arg in args)


def _wrap_mount_path(stick_id: str) -> str:
    return f"/media/{stick_id}-stick"


def _vault_command_needs_media_mount(command_tokens: tuple[str, ...] | list[str]) -> bool:
    return tuple(command_tokens[:1]) in {("create",), ("mount",)}


def _translated_tool_and_args(config: SufConfig, script: AtomicScriptConfig) -> tuple[str, list[str]]:
    tokens = _command_tokens(script.command)
    stick = config.sticks.get(script.stick_id) if script.stick_id else None
    vault = stick.vaults.get(script.vault) if stick is not None and script.vault else None

    def mount_path() -> str:
        return _wrap_mount_path(script.stick_id) if script.stick_id else "/media/unknown-stick"

    if script.tool == "stick":
        args = [*tokens]
        if script.stick_id is not None:
            args += ["--id", script.stick_id]
        if stick is not None and tokens[:1] in {("create",), ("mount",)}:
            args += ["--path", stick.device_path]
        args += script.fixed_args
        return "stick", args

    if script.tool == "vault":
        args = [*tokens]
        if script.stick_id is not None:
            args += ["--media-id", script.stick_id]
            if _vault_command_needs_media_mount(tokens):
                args += ["--mount", mount_path()]
        if script.vault is not None:
            args += ["--vault", script.vault]
        if tokens[:1] == ("create",) and vault is not None:
            if not _has_option(script.fixed_args, "--size"):
                args += ["--size", vault.size]
            if not _has_option(script.fixed_args, "--purpose"):
                args += ["--purpose", vault.purpose]
        args += script.fixed_args
        return "vault", args

    if script.tool == "wipe":
        args = [*tokens]
        if tokens[:1] == ("stick",):
            if stick is not None:
                args += ["--path", stick.device_path]
        elif tokens[:1] == ("vault",):
            if script.stick_id is not None:
                args += ["--media-id", script.stick_id, "--mount", mount_path()]
            if script.vault is not None:
                args += ["--vault", script.vault]
        args += script.fixed_args
        return "wipe", args

    if script.tool == "forge":
        return script.tool, [*tokens, *script.fixed_args]

    raise ValueError(f"Unsupported script tool: {script.tool}")




def _help_color_shell() -> str:
    return """_suf_color_enabled() {
  if [[ "${NO_COLOR:-}" != "" ]]; then
    return 1
  fi
  if [[ "${CLICOLOR_FORCE:-0}" != "0" ]]; then
    return 0
  fi
  [[ -t 1 ]]
}

_suf_text() {
  local code="$1"
  shift
  if _suf_color_enabled; then
    printf '\033[%sm%s\033[0m' "$code" "$*"
  else
    printf '%s' "$*"
  fi
}

_suf_help_line() {
  printf '%s\n' "$*"
}

_suf_help_label() {
  _suf_text '1;36' "$1"
}

_suf_help_heading() {
  _suf_text '1;37' "$1"
}

_suf_help_warning() {
  _suf_text '1;33' "$1"
}

_suf_help_command() {
  _suf_text '2' "$1"
}
"""


def _plain_command(tool: str, args: list[str]) -> str:
    return " ".join([tool, *args])


def _is_destructive_script(script: AtomicScriptConfig) -> bool:
    return script.tool == "wipe"


def _is_destructive_step(step: ScenarioStepConfig) -> bool:
    return step.kind == "cli" and step.tool == "wipe"


def _is_destructive_scenario(script: ScenarioScriptConfig) -> bool:
    return any(_is_destructive_step(step) for step in script.steps)


def _atomic_help_lines(config: SufConfig, script: AtomicScriptConfig, entry: str, args: list[str]) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = [
        ("heading", script.name),
        ("text", ""),
        ("label", "Purpose:"),
        ("text", f"  {script.help}"),
        ("text", ""),
    ]
    if _is_destructive_script(script):
        lines.extend([
            ("warning", "WARNING:"),
            ("warning", "  This script performs a destructive wipe operation."),
            ("text", ""),
        ])
    target_lines: list[str] = []
    if script.stick_id is not None:
        target_lines.append(f"Media ID: {script.stick_id}")
        stick = config.sticks.get(script.stick_id)
        command_tokens = _command_tokens(script.command)
        if stick is not None and script.tool in {"stick", "wipe"} and command_tokens[:1] == ("stick",):
            target_lines.append(f"Device:   {stick.device_path}")
        if script.tool != "vault" or _vault_command_needs_media_mount(command_tokens):
            target_lines.append(f"Mount:    {_wrap_mount_path(script.stick_id)}")
    if script.vault is not None:
        target_lines.append(f"Vault:    {script.vault}")
    if script.fixed_args:
        target_lines.append(f"Fixed:    {' '.join(script.fixed_args)}")
    if target_lines:
        lines.append(("label", "Bound target:"))
        lines.extend(("text", f"  {line}") for line in target_lines)
        lines.append(("text", ""))
    lines.extend([
        ("label", "Runs:"),
        ("command", f"  {_plain_command(entry, args)}"),
        ("text", ""),
        ("label", "Usage:"),
        ("command", f"  {script.name} [extra args...]"),
        ("command", f"  {script.name} --help"),
    ])
    return lines




def _translated_scenario_cli_args(config: SufConfig | None, step: ScenarioStepConfig) -> list[str]:
    tokens = list(step.command)
    if config is None or step.tool is None:
        return [*tokens, *step.args, *step.fixed_args]

    stick = config.sticks.get(step.stick_id) if step.stick_id else None
    vault = stick.vaults.get(step.vault) if stick is not None and step.vault else None

    def mount_path() -> str:
        return _wrap_mount_path(step.stick_id) if step.stick_id else "/media/unknown-stick"

    if step.tool == "stick":
        args = [*tokens]
        if step.stick_id is not None:
            args += ["--id", step.stick_id]
        if stick is not None and tuple(tokens[:1]) in {("create",), ("mount",)}:
            args += ["--path", stick.device_path]
        return [*args, *step.args, *step.fixed_args]

    if step.tool == "vault":
        args = [*tokens]
        if step.stick_id is not None:
            args += ["--media-id", step.stick_id]
            if _vault_command_needs_media_mount(tokens):
                args += ["--mount", mount_path()]
        if step.vault is not None:
            args += ["--vault", step.vault]
        if tuple(tokens[:1]) == ("create",) and vault is not None:
            args += ["--size", vault.size, "--purpose", vault.purpose]
        return [*args, *step.args, *step.fixed_args]

    if step.tool == "wipe":
        args = [*tokens]
        if tuple(tokens[:1]) == ("stick",) and stick is not None:
            args += ["--path", stick.device_path]
        elif tuple(tokens[:1]) == ("vault",):
            if step.stick_id is not None:
                args += ["--media-id", step.stick_id, "--mount", mount_path()]
            if step.vault is not None:
                args += ["--vault", step.vault]
        return [*args, *step.args, *step.fixed_args]

    return [*tokens, *step.args, *step.fixed_args]


def _scenario_help_lines(config: SufConfig | None, script: ScenarioScriptConfig, runtime: RuntimeSpec) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = [
        ("heading", script.name),
        ("text", ""),
        ("label", "Purpose:"),
        ("text", f"  {script.help}"),
        ("text", ""),
    ]
    if _is_destructive_scenario(script):
        lines.extend([
            ("warning", "WARNING:"),
            ("warning", "  This scenario contains destructive wipe operations."),
            ("text", ""),
        ])
    lines.extend([
        ("label", "Scenario:"),
        ("text", f"  Steps: {len(script.steps)}"),
        ("text", f"  Stop on error: {'YES' if script.stop_on_error else 'NO'}"),
        ("text", ""),
        ("label", "Equivalent commands:"),
    ])
    for index, step in enumerate(script.steps, start=1):
        lines.append(("command", f"  {index}. {_render_scenario_step(config, step, runtime)}"))
    lines.extend([
        ("text", ""),
        ("label", "Usage:"),
        ("command", f"  {script.name}"),
        ("command", f"  {script.name} --manual"),
        ("command", f"  {script.name} --help"),
    ])
    return lines


def _render_help_function(function_name: str, lines: list[tuple[str, str]]) -> str:
    rendered = [_help_color_shell(), f"{function_name}() {{"]
    for kind, text in lines:
        quoted = _shell_quote(text)
        if kind == "heading":
            rendered.append(f"  _suf_help_heading {quoted}; printf '\\n'")
        elif kind == "label":
            rendered.append(f"  _suf_help_label {quoted}; printf '\\n'")
        elif kind == "warning":
            rendered.append(f"  _suf_help_warning {quoted}; printf '\\n'")
        elif kind == "command":
            rendered.append(f"  _suf_help_command {quoted}; printf '\\n'")
        else:
            rendered.append(f"  _suf_help_line {quoted}")
    rendered.append("}")
    return "\n".join(rendered)

def _runtime_from_pythonpath(pythonpath_parts: list[str]) -> RuntimeSpec:
    return RuntimeSpec(layout="tree", pythonpath_parts=pythonpath_parts)


def _render_atomic_script(
    config: SufConfig,
    script: AtomicScriptConfig,
    pythonpath_parts: list[str] | None = None,
    runtime: RuntimeSpec | None = None,
) -> str:
    runtime = runtime or _runtime_from_pythonpath(pythonpath_parts or [])
    entry, args = _translated_tool_and_args(config, script)
    quoted_args = " ".join(_shell_quote(arg) for arg in args)
    tool_exec = _render_tool_exec(entry, runtime)
    py_export = "" if runtime.layout in {"executable", "package"} else f'export PYTHONPATH="{runtime.py_path()}"\n'
    help_function = _render_help_function("_suf_script_help", _atomic_help_lines(config, script, entry, args))
    return f"""#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
{py_export}{help_function}

if [[ ${{1:-}} == "--show-completion" || ${{1:-}} == "--install-completion" ]]; then
  exec {tool_exec} "$@"
fi

if [[ ${{1:-}} == "--help" || ${{1:-}} == "-h" ]]; then
  _suf_script_help
  exit 0
fi

exec {tool_exec} {quoted_args} "$@"
"""


def _render_scenario_step(config: SufConfig | None, step: ScenarioStepConfig, runtime: RuntimeSpec | None = None) -> str:
    runtime = runtime or RuntimeSpec(layout="tree", pythonpath_parts=[])
    if step.kind == "cli":
        tool = step.tool or ""
        cli_args = _translated_scenario_cli_args(config, step)
        args = " ".join(_shell_quote(arg) for arg in cli_args)
        return f"{_render_tool_exec(tool, runtime)} {args}".strip()
    if step.kind == "entrypoint":
        args = ", ".join(repr(arg) for arg in step.args)
        return (
            "python3 - <<'PY_STEP'\n"
            f"from {step.module} import {step.callable} as _scenario_entrypoint\n"
            f"raise SystemExit(_scenario_entrypoint({args}))\n"
            "PY_STEP"
        )
    if step.kind == "python":
        args = " ".join(_shell_quote(arg) for arg in step.args)
        return f"python3 {_shell_quote(step.path or '')} {args}"
    raise ValueError(f"Unsupported scenario step kind: {step.kind}")


def _render_scenario_manual(config: SufConfig | None, script: ScenarioScriptConfig, runtime: RuntimeSpec | None = None) -> str:
    commands = [
        f"echo 'Scenario manual procedure: {script.name}'",
        "echo 'Equivalent commands:'",
    ]
    for index, step in enumerate(script.steps, start=1):
        rendered = _render_scenario_step(config, step, runtime).replace("'", "'\"'\"'")
        commands.append(f"echo '{index}. {rendered}'")
    commands.append("exit 0")
    return "\n".join(commands)


def _render_scenario_script(
    script: ScenarioScriptConfig,
    pythonpath_parts: list[str] | None = None,
    config: SufConfig | None = None,
    runtime: RuntimeSpec | None = None,
) -> str:
    runtime = runtime or _runtime_from_pythonpath(pythonpath_parts or [])
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail" if script.stop_on_error else "set -uo pipefail",
        "",
        'ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"',
        "export PYTHONDONTWRITEBYTECODE=1",
    ]
    if runtime.layout not in {"executable", "package"}:
        lines.append(f'export PYTHONPATH="{runtime.py_path()}"')
    lines.extend(
        [
            _render_help_function("_suf_script_help", _scenario_help_lines(config, script, runtime)),
            "",
            'if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then',
            "  _suf_script_help",
            "  exit 0",
            "fi",
            "",
            'if [[ ${1:-} == "--manual" || ${1:-} == "-M" ]]; then',
            _render_scenario_manual(config, script, runtime),
            "fi",
            "",
        ]
    )
    for index, step in enumerate(script.steps, start=1):
        rendered = _render_scenario_step(config, step, runtime)
        title = step.tool or step.module or step.path
        lines.append(f"echo '[{index}/{len(script.steps)}] {step.kind}: {title}'")
        if script.stop_on_error:
            lines.append(rendered)
        else:
            lines.append(f"{rendered} || true")
        lines.append("")
    return "\n".join(lines)


def _ignored_source_path(path: Path) -> bool:
    return (
        "__pycache__" in path.parts
        or ".ruff_cache" in path.parts
        or "secure_usb_factory.egg-info" in path.parts
        or path.name.endswith(".pyc")
    )


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)

    def ignore(_dir: str, names: list[str]) -> set[str]:
        ignored = {"__pycache__", ".ruff_cache", "secure_usb_factory.egg-info"}
        return {name for name in names if name in ignored or name.endswith(".pyc")}

    shutil.copytree(src, dest, ignore=ignore)


def _runtime_script(tool_names: list[str]) -> str:
    imports = "\n".join(f"from {tool}.cli import app as {tool}_app" for tool in tool_names)
    mapping = ", ".join(f"{tool!r}: {tool}_app" for tool in tool_names)
    available = ", ".join(tool_names)
    return f"""from __future__ import annotations

import sys

{imports}

APPS = {{{mapping}}}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {{"--help", "-h"}}:
        print("Usage: runtime <tool> [args...]")
        print("Tools: {available}")
        return 0 if len(sys.argv) >= 2 else 2
    tool = sys.argv[1]
    app = APPS.get(tool)
    if app is None:
        print(f"Unknown tool: {{tool}}", file=sys.stderr)
        print("Tools: {available}", file=sys.stderr)
        return 2
    sys.argv = [f"suf {{tool}}", *sys.argv[2:]]
    app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _tools_for_plan(plan) -> list[str]:
    tools: list[str] = []
    for key in plan.included_packages:
        item = DEBUG_TOOL_BY_PACKAGE.get(key)
        if item is not None:
            tools.append(item[0])
    return tools


def _write_executable_runtime(repo_root: Path, output: Path, plan) -> Path:
    tools = _tools_for_plan(plan)
    if not tools:
        raise RuntimeError("Executable library layout requires at least one runnable tool package.")

    build_root = output / ".pyinstaller"
    if importlib.util.find_spec("PyInstaller") is None:
        raise RuntimeError(
            "Executable library layout requires PyInstaller. "
            "Install the build extra first: "
            "UV_HTTP_TIMEOUT=600 UV_HTTP_RETRIES=10 "
            "uv sync --extra dev --extra lint --extra build --index-url https://pypi.org/simple"
        )
    script = build_root / "script_runtime.py"
    dist_dir = output / "lib"
    work_dir = build_root / "work"
    spec_dir = build_root / "spec"
    build_root.mkdir(parents=True, exist_ok=True)
    script.write_text(_runtime_script(tools), encoding="utf-8")

    pythonpath = os.pathsep.join(str(repo_root / ROOT_PACKAGE_MAP[key]) for key in plan.included_packages)
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
        "runtime",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        str(script),
    ]
    try:
        subprocess.run(command, cwd=repo_root, env=env, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Executable library layout requires a working Python interpreter and PyInstaller build extra.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("PyInstaller failed while building lib/runtime") from exc
    executable = dist_dir / "runtime"
    if not executable.exists():
        raise RuntimeError("PyInstaller completed but lib/runtime was not created.")
    executable.chmod(executable.stat().st_mode | 0o111)
    shutil.rmtree(build_root, ignore_errors=True)
    return executable


def _packaged_root() -> Path | None:
    explicit = os.environ.get("USB_FACTORY_PACKAGE_ROOT")
    if explicit:
        root = Path(explicit).resolve()
        if (root / "config" / "forge.toml").exists():
            return root

    executable = Path(sys.executable).resolve()

    # Tree layout runs through dist/suf/bin/<tool>.
    candidate = executable.parent.parent
    if executable.parent.name == "bin" and (candidate / "config" / "forge.toml").exists():
        return candidate

    # Executable layout runs through dist/suf/lib/runtime.  The tiny bin/<tool>
    # launchers exec that binary, so sys.executable points at lib/<tool> inside
    # the PyInstaller process.
    candidate = executable.parent.parent
    if executable.parent.name == "lib" and (candidate / "config" / "forge.toml").exists():
        return candidate

    return None


def _packaged_available_tools(package_root: Path) -> set[str]:
    bin_dir = package_root / "bin"
    if not bin_dir.exists():
        return set()
    return {path.name for path in bin_dir.iterdir() if path.is_file() and path.name in MODULE_BY_TOOL}


def _required_tools_for_script(script: AtomicScriptConfig | ScenarioScriptConfig) -> set[str]:
    if isinstance(script, AtomicScriptConfig):
        return {script.tool}
    tools: set[str] = set()
    for step in script.steps:
        if step.kind == "cli" and step.tool is not None:
            tools.add(step.tool)
    return tools


def _script_skip_for_missing_tools(
    script: AtomicScriptConfig | ScenarioScriptConfig,
    available_tools: set[str] | None,
) -> SkippedScript | None:
    if available_tools is None:
        return None
    missing = sorted(_required_tools_for_script(script) - available_tools)
    if not missing:
        return None
    return SkippedScript(name=script.name, missing_tools=missing)


def _write_artifact_archive(output: Path) -> Path:
    archive_path = output.with_suffix(".zip")
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(output.rglob("*")):
            if not file_path.is_file() or _ignored_source_path(file_path):
                continue
            archive.write(file_path, file_path.relative_to(output.parent).as_posix())
    return archive_path


def _repo_root_from_source() -> Path:
    path = Path(__file__).resolve()
    try:
        return path.parents[4]
    except IndexError as exc:
        raise RuntimeError(
            "Could not resolve repository root from source path. "
            "Packaged executable runs must set USB_FACTORY_PACKAGE_ROOT "
            "or live under dist/suf/lib/runtime."
        ) from exc


def stage_artifact(config: SufConfig, reporter=None) -> Path:
    plan = build_plan(config)
    package_root = _packaged_root()
    output_base = package_root if package_root is not None else Path.cwd()
    output = output_base / config.artifacts.output_dir
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    available_tools: set[str] | None = None
    if package_root is not None:
        # Packaged forge regenerates scripts only. It reuses the packaged
        # CLIs in ../bin and does not rebuild or copy Python libraries.
        runtime = RuntimeSpec(layout="package", pythonpath_parts=[], executable_path="../bin")
        available_tools = _packaged_available_tools(package_root)
    else:
        repo_root = _repo_root_from_source()
        lib_dir = output / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)

        if config.package.lib_layout == "executable":
            _write_executable_runtime(repo_root, output, plan)
            runtime = RuntimeSpec(layout="executable", pythonpath_parts=[])
        else:
            for package_key in plan.included_packages:
                src = repo_root / ROOT_PACKAGE_MAP[package_key]
                dest = lib_dir / package_key
                _copy_tree(src, dest)
            runtime = RuntimeSpec(layout="tree", pythonpath_parts=[f"lib/{pkg}" for pkg in plan.included_packages])


    generated: list[str] = []
    skipped: list[SkippedScript] = []
    for script in config.forge.scripts.values():
        if script.disabled:
            continue
        skip = _script_skip_for_missing_tools(script, available_tools)
        if skip is not None:
            skipped.append(skip)
            if reporter is not None:
                reporter(skip.render_notice())
            continue
        if isinstance(script, AtomicScriptConfig):
            content = _render_atomic_script(config, script, runtime=runtime)
        else:
            content = _render_scenario_script(script, config=config, runtime=runtime)
        path = output / script.name
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | 0o111)
        generated.append(script.name)

    if skipped and reporter is not None:
        missing_tools = sorted({tool for item in skipped for tool in item.missing_tools})
        reporter(
            "Not all scripts were generated; missing packaged tools: "
            + ", ".join(missing_tools)
        )

    archive_path = str(output.with_suffix(".zip")) if config.artifacts.archive_format == "zip" else None

    if config.artifacts.include_manifest:
        manifest = {
            "generated_scripts": generated,
            "disabled_scripts": plan.disabled_scripts,
            "skipped_scripts": [
                {"name": item.name, "missing_tools": item.missing_tools}
                for item in skipped
            ],
            "included_packages": plan.included_packages,
            "library_layout": config.package.lib_layout,
            "archive_format": config.artifacts.archive_format,
            "archive_path": archive_path,
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + os.linesep, encoding="utf-8")

    if config.artifacts.archive_format == "zip":
        _write_artifact_archive(output)
    return output
