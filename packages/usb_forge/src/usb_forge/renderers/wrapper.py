from __future__ import annotations


def render_script_stub(name: str) -> str:
    return f"#!/usr/bin/env bash\n# script: {name}\necho 'Not implemented yet.'\n"
