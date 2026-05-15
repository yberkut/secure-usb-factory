from __future__ import annotations

import re
from typing import Iterable

import typer
from usb_shared.version import VERSION
from rich.console import Console
from rich.text import Text

from usb_shared.theme import CLI_THEME


def echo_version(name: str) -> None:
    typer.echo(f"{name} {VERSION}")


def echo_label(label: str, value: str) -> None:
    echo_themed_line(f"{label:<13} {value}")


_def_console = Console(stderr=False, width=240)


def _token_pattern(token: str) -> str:
    escaped = re.escape(token)
    if re.fullmatch(r"[A-Z ]+", token):
        return rf"(?<![A-Z]){escaped}(?![A-Z])"
    return escaped


def _style_tokens(value: str) -> Text:
    text = Text(style=CLI_THEME.value_style)
    i = 0
    tokens = sorted(CLI_THEME.token_styles.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(_token_pattern(token) for token in tokens))
    for match in pattern.finditer(value):
        if match.start() > i:
            text.append(value[i:match.start()])
        token = match.group(0)
        style = CLI_THEME.token_styles.get(token, CLI_THEME.value_style)
        text.append(token, style=style)
        i = match.end()
    if i < len(value):
        text.append(value[i:])
    return text


def _render_labeled_line(line: str) -> Text:
    label, rest = line.split(":", 1)
    out = Text()
    out.append(f"{label}:", style=CLI_THEME.label_style)
    out.append(rest[: max(0, len(rest) - len(rest.lstrip()))])
    out.append_text(_style_tokens(rest.lstrip()))
    return out


def _render_prefixed_line(line: str, style: str) -> Text:
    return Text(line, style=style)


def _render_plan_heading(line: str) -> Text:
    label, rest = line.split(":", 1)
    out = Text()
    out.append(f"{label}:", style=CLI_THEME.plan_heading_style)
    out.append(rest[: max(0, len(rest) - len(rest.lstrip()))])
    out.append_text(Text(rest.lstrip(), style=CLI_THEME.plan_heading_style))
    return out


def _render_plan_item(line: str) -> Text:
    match = PLAN_ITEM_RE.match(line) or PLAN_BULLET_RE.match(line)
    if not match:
        return Text(line, style=CLI_THEME.plan_label_style)
    prefix, body = match.groups()
    out = Text()
    out.append(prefix, style=CLI_THEME.plan_prefix_style)
    if ":" in body:
        label, rest = body.split(":", 1)
        out.append(label + ":", style=CLI_THEME.plan_label_style)
        out.append(rest[: max(0, len(rest) - len(rest.lstrip()))], style=CLI_THEME.plan_label_style)
        out.append_text(_style_tokens(rest.lstrip()))
        return out
    out.append(body, style=CLI_THEME.plan_label_style)
    return out


PROMPT_RE = re.compile(r"(^\[[0-9]+/[0-9]+\]\s)|(:\s*$)")
PLAN_ITEM_RE = re.compile(r"^(\d+\.\s+)(.+)$")
PLAN_BULLET_RE = re.compile(r"^(-\s+)(.+)$")


def _render_line(line: str) -> Text:
    if not line:
        return Text("")
    if line.startswith("$ "):
        return _render_prefixed_line(line, CLI_THEME.command_style)
    if line.startswith("Plan:"):
        return _render_plan_heading(line)
    if PLAN_ITEM_RE.match(line) or PLAN_BULLET_RE.match(line):
        return _render_plan_item(line)
    if ":" in line and not line.startswith("["):
        label, rest = line.split(":", 1)
        if label and rest and not label.startswith("/"):
            return _render_labeled_line(line)
    if line.endswith(":") and ":" not in line[:-1]:
        return _render_prefixed_line(line, CLI_THEME.heading_style)
    if PROMPT_RE.search(line):
        return _render_prefixed_line(line, CLI_THEME.prompt_style)
    for prefix in CLI_THEME.error_prefixes:
        if line.startswith(prefix):
            return _render_prefixed_line(line, CLI_THEME.error_style)
    for prefix in CLI_THEME.warning_prefixes:
        if line.startswith(prefix):
            return _render_prefixed_line(line, CLI_THEME.warning_style)
    for prefix in CLI_THEME.success_prefixes:
        if line.startswith(prefix):
            return _render_prefixed_line(line, CLI_THEME.success_style)
    return _style_tokens(line)


def echo_themed_line(line: str) -> None:
    _def_console.print(_render_line(line), soft_wrap=False)


def echo_lines(lines: Iterable[str]) -> None:
    for line in lines:
        echo_themed_line(line)


def echo_plan_lines(lines: Iterable[str]) -> None:
    for line in lines:
        echo_themed_line(line)


def echo_status_lines(lines: Iterable[str]) -> None:
    echo_lines(lines)
