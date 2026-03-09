"""Shared fixtures for SimpleContacts tests."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_data(tmp_path, monkeypatch):
    """Redirect all data/settings paths to a temporary directory per-test."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    monkeypatch.setattr("simple_contacts.config.DATA_DIR", data_dir)
    monkeypatch.setattr("simple_contacts.config.SETTINGS_FILE", data_dir / "app_settings.json")
    monkeypatch.setattr("simple_contacts.config.EMPLOYEE_LIST_FILE", data_dir / "employee_list.json")
    monkeypatch.setattr("simple_contacts.config.DATA_UPDATE_STATUS_FILE", data_dir / "data_update_status.json")

    # Also patch in settings module which imports at module level
    monkeypatch.setattr("simple_contacts.settings.SETTINGS_FILE", data_dir / "app_settings.json")

    # Patch data_update module-level string paths
    monkeypatch.setattr("simple_contacts.data_update.DATA_DIR", str(data_dir))
    monkeypatch.setattr("simple_contacts.data_update.EMPLOYEE_LIST_FILE", str(data_dir / "employee_list.json"))
    monkeypatch.setattr("simple_contacts.data_update.DATA_UPDATE_STATUS_FILE", str(data_dir / "data_update_status.json"))

    # Reset data_update in-memory state
    monkeypatch.setattr("simple_contacts.data_update._CURRENT_DATA_UPDATE_STATUS", {"state": "idle"})
    monkeypatch.setattr("simple_contacts.data_update._APP_STARTUP_COMPLETE", False)

    yield


@pytest.fixture
def app(monkeypatch):
    """Create a Flask test app."""
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_PASSWORD", "testpass")

    from simple_contacts.app_main import app as flask_app

    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    """Return a test client."""
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Return an authenticated test client."""
    with client.session_transaction() as sess:
        sess["authenticated"] = True
    return client


SAMPLE_EMPLOYEES = [  # test-only fake data, not real PII
    {
        "name": "Test User One",
        "email": "testuser1@test.example",  # noqa: E501  # not real
        "phone": "555-0000",
        "businessPhone": "555-0001",
        "title": "Engineer",
        "department": "Engineering",
        "city": "Testville",
        "state": "TS",
    },
    {
        "name": "Test User Two",
        "email": "testuser2@test.example",  # noqa: E501  # not real
        "phone": "",
        "businessPhone": "555-0002",
        "title": "Manager",
        "department": "Sales",
        "city": "Testville",
        "state": "TS",
    },
]
