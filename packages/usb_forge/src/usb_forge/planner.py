from __future__ import annotations

from dataclasses import dataclass

from usb_shared.config.schema import AtomicScriptConfig, ScenarioScriptConfig, SufConfig


@dataclass(frozen=True)
class AtomicScriptPlan:
    name: str
    tool: str
    command: str
    target: str
    fixed_args: list[str]

    def render(self) -> str:
        args = " ".join(self.fixed_args) if self.fixed_args else "(none)"
        return f"- {self.name}: {self.tool} {self.command} target={self.target} args={args}"


@dataclass(frozen=True)
class ScenarioScriptPlan:
    name: str
    step_count: int
    stop_on_error: bool

    def render(self) -> str:
        stop = "YES" if self.stop_on_error else "NO"
        return f"- {self.name}: {self.step_count} step(s), stop-on-error={stop}"


@dataclass(frozen=True)
class ForgePlan:
    included_packages: list[str]
    atomic_scripts: list[str]
    scenario_scripts: list[str]
    disabled_scripts: list[str]
    referenced_targets: list[str]
    output_dir: str
    lib_layout: str
    artifact_archive_format: str
    atomic_details: list[AtomicScriptPlan]
    scenario_details: list[ScenarioScriptPlan]

    def render_lines(self) -> list[str]:
        lines = [
            "Forge inspection:",
            f"Output artifact: {self.output_dir}",
            f"Library layout: {self.lib_layout}",
            f"Artifact archive: {self.artifact_archive_format}",
            "Atomic scripts:",
        ]
        lines.extend([detail.render() for detail in self.atomic_details] or ["- (none)"])
        lines.append("Scenario scripts:")
        lines.extend([detail.render() for detail in self.scenario_details] or ["- (none)"])
        lines.append("Scripts disabled:")
        lines.extend([f"- {name}" for name in self.disabled_scripts] or ["- (none)"])
        lines.extend([
            f"Packages in lib/: {', '.join(self.included_packages) or '(none)'}",
            f"Referenced targets: {', '.join(self.referenced_targets) or '(none)'}",
            # Compatibility summary lines used by older tests and operator notes.
            f"Atomic scripts: {', '.join(self.atomic_scripts) or '(none)'}",
            f"Scenario scripts: {', '.join(self.scenario_scripts) or '(none)'}",
            f"Scripts generated: {', '.join(self.atomic_scripts + self.scenario_scripts) or '(none)'}",
            f"Scripts disabled: {', '.join(self.disabled_scripts) or '(none)'}",
        ])
        return lines


def _packages_for_tool(tool: str) -> set[str]:
    base = {"src", "usb_shared", "usb_linux"}
    if tool == "stick":
        base.add("usb_stick")
    elif tool == "vault":
        base.add("usb_vault")
    elif tool == "wipe":
        base.add("usb_wipe")
    elif tool == "forge":
        base.add("usb_forge")
    return base


def _determine_included_packages(config: SufConfig) -> list[str]:
    packages = {"src", "usb_shared", "usb_linux"}
    for script in config.forge.scripts.values():
        if script.disabled:
            continue
        if isinstance(script, AtomicScriptConfig):
            packages.update(_packages_for_tool(script.tool))
        elif isinstance(script, ScenarioScriptConfig):
            for step in script.steps:
                if step.kind == "cli" and step.tool:
                    packages.update(_packages_for_tool(step.tool))
    order = ["src", "usb_shared", "usb_linux", "usb_stick", "usb_vault", "usb_wipe", "usb_forge"]
    return [pkg for pkg in order if pkg in packages]


def _target_for_atomic_script(script: AtomicScriptConfig) -> str:
    if script.stick_id and script.vault:
        return f"{script.stick_id}/{script.vault}"
    if script.stick_id:
        return script.stick_id
    return "(none)"


def build_plan(config: SufConfig) -> ForgePlan:
    atomic_scripts: list[str] = []
    scenario_scripts: list[str] = []
    disabled_scripts: list[str] = []
    referenced_targets: list[str] = []
    atomic_details: list[AtomicScriptPlan] = []
    scenario_details: list[ScenarioScriptPlan] = []

    for script in config.forge.scripts.values():
        if script.disabled:
            disabled_scripts.append(script.name)
            continue
        if isinstance(script, AtomicScriptConfig):
            atomic_scripts.append(script.name)
            target = _target_for_atomic_script(script)
            atomic_details.append(
                AtomicScriptPlan(
                    name=script.name,
                    tool=script.tool,
                    command=script.command,
                    target=target,
                    fixed_args=list(script.fixed_args),
                )
            )
            if script.stick_id and script.vault:
                referenced_targets.append(f"{script.stick_id}/{script.vault}")
            elif script.stick_id:
                referenced_targets.append(script.stick_id)
        elif isinstance(script, ScenarioScriptConfig):
            scenario_scripts.append(script.name)
            scenario_details.append(
                ScenarioScriptPlan(
                    name=script.name,
                    step_count=len(script.steps),
                    stop_on_error=script.stop_on_error,
                )
            )

    return ForgePlan(
        included_packages=_determine_included_packages(config),
        atomic_scripts=atomic_scripts,
        scenario_scripts=scenario_scripts,
        disabled_scripts=disabled_scripts,
        referenced_targets=sorted(set(referenced_targets)),
        output_dir=config.artifacts.output_dir,
        lib_layout=config.package.lib_layout,
        artifact_archive_format=config.artifacts.archive_format,
        atomic_details=atomic_details,
        scenario_details=scenario_details,
    )


def inspect_plan(config: SufConfig) -> str:
    return "\n".join(build_plan(config).render_lines())
