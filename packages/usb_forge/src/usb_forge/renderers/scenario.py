from __future__ import annotations


def render_scenario_stub(name: str) -> str:
    return f"#!/usr/bin/env bash\n# scenario script: {name}\necho 'Scenario not implemented yet.'\n"
