"""Tests for simple_contacts.settings."""

import json

from simple_contacts.settings import DEFAULT_SETTINGS, load_settings, save_settings


def test_load_settings_defaults(tmp_path, monkeypatch):
    """When no file exists, defaults are returned."""
    monkeypatch.setattr("simple_contacts.settings.SETTINGS_FILE", tmp_path / "missing.json")
    result = load_settings()
    assert result == DEFAULT_SETTINGS


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr("simple_contacts.settings.SETTINGS_FILE", path)

    custom = {"directoryJsonEnabled": True, "directoryJsonFilename": "myfile"}
    save_settings(custom)
    assert path.exists()

    loaded = load_settings()
    assert loaded["directoryJsonEnabled"] is True
    assert loaded["directoryJsonFilename"] == "myfile"
    # Non-overridden defaults preserved
    assert loaded["directoryXmlEnabled"] is False


def test_save_merges_with_defaults(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr("simple_contacts.settings.SETTINGS_FILE", path)

    save_settings({"directoryXmlEnabled": True})
    with path.open() as f:
        raw = json.load(f)
    # All default keys should exist
    for key in DEFAULT_SETTINGS:
        assert key in raw


def test_load_settings_handles_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "bad.json"
    path.write_text("NOT JSON", encoding="utf-8")
    monkeypatch.setattr("simple_contacts.settings.SETTINGS_FILE", path)
    result = load_settings()
    assert result == DEFAULT_SETTINGS
