"""Tests for simple_contacts.config."""

from simple_contacts.config import CONFIG_DIR, DATA_DIR, SETTINGS_FILE, ensure_directories


def test_ensure_directories_creates_missing(tmp_path, monkeypatch):
    data_target = tmp_path / "new_data"
    config_target = tmp_path / "new_config"
    monkeypatch.setattr("simple_contacts.config.DATA_DIR", data_target)
    monkeypatch.setattr("simple_contacts.config.CONFIG_DIR", config_target)
    ensure_directories()
    assert data_target.exists()
    assert config_target.exists()


def test_settings_file_in_config_dir():
    assert SETTINGS_FILE.parent == CONFIG_DIR


def test_paths_are_pathlib():
    from pathlib import Path
    assert isinstance(DATA_DIR, Path)
    assert isinstance(CONFIG_DIR, Path)
    assert isinstance(SETTINGS_FILE, Path)
