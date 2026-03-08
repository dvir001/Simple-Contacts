"""Tests for simple_contacts.config."""

from simple_contacts.config import DATA_DIR, SETTINGS_FILE, ensure_directories


def test_ensure_directories_creates_missing(tmp_path, monkeypatch):
    target = tmp_path / "new_data"
    monkeypatch.setattr("simple_contacts.config.DATA_DIR", target)
    ensure_directories()
    assert target.exists()


def test_paths_are_pathlib():
    from pathlib import Path
    assert isinstance(DATA_DIR, Path)
    assert isinstance(SETTINGS_FILE, Path)
