from pathlib import Path

from usb_stick.service import StickService
from usb_vault.service import VaultService
from usb_wipe.service import WipeService


def test_stick_create_status(monkeypatch) -> None:
    monkeypatch.setattr("usb_stick.service.which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr("usb_stick.service.device_exists", lambda path: True)
    result = StickService().create_status("blue", "/dev/disk/by-id/test")
    assert result.ok
    assert any("blue-stick" in line for line in result.lines)


def test_vault_status(monkeypatch) -> None:
    monkeypatch.setattr("usb_vault.service.which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr("usb_vault.service.is_mounted", lambda path: Path(path) == Path("/media/blue-stick"))
    monkeypatch.setattr("usb_vault.service.path_exists", lambda path: True)
    monkeypatch.setattr("usb_vault.service.mapper_exists", lambda name: False)
    result = VaultService().status("blue", "/media/blue-stick", "personal")
    assert result.ok
    assert any("blue-personal-vault" in line for line in result.lines)


def test_wipe_stick_status(monkeypatch) -> None:
    monkeypatch.setattr("usb_wipe.service.device_exists", lambda path: True)
    monkeypatch.setattr("usb_wipe.service.device_identity", lambda path, **kwargs: None)
    result = WipeService().stick("/dev/disk/by-id/test", status=True)
    assert result.ok
    assert any("Wipe stick status:" in line for line in result.lines)
