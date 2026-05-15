from usb_shared.naming import derive_stick_names, derive_vault_names


def test_stick_names() -> None:
    names = derive_stick_names("blue")
    assert names.stick_name == "blue-stick"
    assert names.stick_mapper == "map-blue-stick"
    assert str(names.stick_mount) == "/media/blue-stick"


def test_vault_names() -> None:
    names = derive_vault_names("blue", "personal")
    assert names.vault_name == "blue-personal-vault"
    assert names.vault_mapper == "map-blue-personal-vault"
    assert str(names.vault_mount) == "/media/blue-personal-vault"
