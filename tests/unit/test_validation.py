from __future__ import annotations

import pytest

from usb_shared.errors import ValidationError
from usb_shared.naming import derive_stick_names, derive_vault_names
from usb_shared.validation import validate_stick_id, validate_vault_basename, validate_script_name


@pytest.mark.parametrize("value", ["blue", "vault01", "travel-stick", "a", "a1-b2"])
def test_valid_identifiers(value: str) -> None:
    assert validate_stick_id(value) == value
    assert validate_vault_basename(value) == value
    assert validate_script_name(value) == value


@pytest.mark.parametrize(
    "value",
    ["", ".", "..", "../x", "x/y", "bad id", "Bad", "bad_id", "-bad", "bad-", "x.y"],
)
def test_invalid_identifiers(value: str) -> None:
    with pytest.raises(ValidationError):
        validate_stick_id(value)
    with pytest.raises(ValidationError):
        validate_vault_basename(value)


def test_naming_rejects_path_traversal() -> None:
    with pytest.raises(ValidationError):
        derive_stick_names("../blue")
    with pytest.raises(ValidationError):
        derive_vault_names("blue", "../personal")
