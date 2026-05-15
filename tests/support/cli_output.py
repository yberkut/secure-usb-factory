from __future__ import annotations

import re

ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
WHITESPACE_RE = re.compile(r"\s+")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def normalized_cli_output(text: str) -> str:
    """Return CLI output with ANSI styling removed and whitespace made stable."""
    return WHITESPACE_RE.sub(" ", strip_ansi(text)).strip()


def assert_cli_contains(output: str, fragment: str) -> None:
    normalized_output = normalized_cli_output(output)
    normalized_fragment = normalized_cli_output(fragment)
    assert normalized_fragment in normalized_output
