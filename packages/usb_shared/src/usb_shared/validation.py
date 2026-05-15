from __future__ import annotations

import re
from pathlib import Path

from .errors import ValidationError

_IDENTIFIER_RE = re.compile(r"^(?:[a-z0-9]|[a-z0-9][a-z0-9-]{0,61}[a-z0-9])$")
_FORBIDDEN_PATHS = {"", ".", ".."}


def _validate_identifier(value: str, label: str) -> str:
    if value in _FORBIDDEN_PATHS or not _IDENTIFIER_RE.fullmatch(value):
        raise ValidationError(
            f"Invalid {label}: {value!r}. Use lowercase letters, digits, and dashes; "
            "start with a letter or digit; max length 63; no slashes, spaces, dots, or '..'."
        )
    return value


def validate_stick_id(stick_id: str) -> str:
    return _validate_identifier(stick_id, "Stick ID")


def validate_media_id(media_id: str) -> str:
    return _validate_identifier(media_id, "media ID")


def validate_vault_basename(vault: str) -> str:
    return _validate_identifier(vault, "vault basename")


def validate_script_name(name: str) -> str:
    # Script names are executable filenames, so keep them path-safe too.
    return _validate_identifier(name, "script name")


def validate_no_path_traversal(value: str, label: str) -> str:
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValidationError(f"Invalid {label}: {value!r}. Path traversal is not allowed.")
    return value
