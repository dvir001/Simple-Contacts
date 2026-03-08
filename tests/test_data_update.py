"""Tests for simple_contacts.data_update."""

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tests.conftest import SAMPLE_EMPLOYEES


class TestLoadDataUpdateStatus:
    def test_returns_idle_when_no_file(self):
        from simple_contacts.data_update import load_data_update_status

        status = load_data_update_status()
        assert status["state"] == "idle"

    def test_reads_persisted_status(self, tmp_path, monkeypatch):
        from simple_contacts.data_update import load_data_update_status

        status_file = os.path.join(str(tmp_path / "data"), "data_update_status.json")
        os.makedirs(os.path.dirname(status_file), exist_ok=True)
        with open(status_file, "w") as fh:
            json.dump({"state": "idle", "success": True, "finishedAt": "2026-01-01T00:00:00+00:00"}, fh)

        status = load_data_update_status()
        assert status.get("success") is True

    def test_resets_stale_running_before_startup_complete(self, tmp_path, monkeypatch):
        from simple_contacts import data_update
        from simple_contacts.data_update import load_data_update_status

        status_file = os.path.join(str(tmp_path / "data"), "data_update_status.json")
        with open(status_file, "w") as fh:
            json.dump({"state": "running", "startedAt": "2026-01-01T00:00:00+00:00"}, fh)

        # _APP_STARTUP_COMPLETE is False by default from conftest
        status = load_data_update_status()
        assert status["state"] == "idle"
        assert "interrupted" in status.get("error", "").lower()

    def test_resets_stale_running_after_2_hours(self, tmp_path, monkeypatch):
        from simple_contacts import data_update
        from simple_contacts.data_update import load_data_update_status

        monkeypatch.setattr("simple_contacts.data_update._APP_STARTUP_COMPLETE", True)

        old_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        status_file = os.path.join(str(tmp_path / "data"), "data_update_status.json")
        with open(status_file, "w") as fh:
            json.dump({"state": "running", "startedAt": old_time}, fh)

        status = load_data_update_status()
        assert status["state"] == "idle"
        assert "stuck" in status.get("error", "").lower()


class TestMarkRunningAndFinished:
    def test_mark_running(self):
        from simple_contacts.data_update import mark_data_update_running

        status = mark_data_update_running(source="test")
        assert status["state"] == "running"
        assert status["source"] == "test"
        assert "startedAt" in status

    def test_mark_finished_success(self):
        from simple_contacts.data_update import mark_data_update_finished

        status = mark_data_update_finished(success=True, source="test")
        assert status["state"] == "idle"
        assert status["success"] is True
        assert status.get("lastSuccessAt") is not None

    def test_mark_finished_failure(self):
        from simple_contacts.data_update import mark_data_update_finished

        status = mark_data_update_finished(success=False, error="boom", source="test")
        assert status["state"] == "idle"
        assert status["success"] is False
        assert status["error"] == "boom"


class TestMarkStartupComplete:
    def test_sets_flag(self, monkeypatch):
        from simple_contacts import data_update
        from simple_contacts.data_update import mark_startup_complete

        monkeypatch.setattr("simple_contacts.data_update._APP_STARTUP_COMPLETE", False)
        mark_startup_complete()
        assert data_update._APP_STARTUP_COMPLETE is True


class TestUpdateEmployeeData:
    @patch("simple_contacts.data_update.fetch_all_employees", return_value=SAMPLE_EMPLOYEES)
    @patch("simple_contacts.data_update.azure_credentials_configured", return_value=True)
    def test_success(self, mock_creds, mock_fetch, tmp_path, monkeypatch):
        from simple_contacts.data_update import load_data_update_status, update_employee_data

        monkeypatch.setattr("simple_contacts.data_update._APP_STARTUP_COMPLETE", True)
        update_employee_data(source="test")

        status = load_data_update_status()
        assert status["success"] is True

        # Verify employees were written to disk
        import simple_contacts.config as cfg
        emp_path = cfg.EMPLOYEE_LIST_FILE
        assert emp_path.exists()
        employees = json.loads(emp_path.read_text(encoding="utf-8"))
        assert len(employees) == 2

    @patch("simple_contacts.data_update.azure_credentials_configured", return_value=False)
    def test_no_credentials(self, mock_creds, monkeypatch):
        from simple_contacts.data_update import load_data_update_status, update_employee_data

        monkeypatch.setattr("simple_contacts.data_update._APP_STARTUP_COMPLETE", True)
        update_employee_data(source="test")

        status = load_data_update_status()
        assert status["success"] is False
        assert "not configured" in status.get("error", "").lower()

    @patch("simple_contacts.data_update.fetch_all_employees", return_value=[])
    @patch("simple_contacts.data_update.azure_credentials_configured", return_value=True)
    def test_empty_result(self, mock_creds, mock_fetch, monkeypatch):
        from simple_contacts.data_update import load_data_update_status, update_employee_data

        monkeypatch.setattr("simple_contacts.data_update._APP_STARTUP_COMPLETE", True)
        update_employee_data(source="test")

        status = load_data_update_status()
        assert status["success"] is False
        assert "no employees" in status.get("error", "").lower()

    @patch("simple_contacts.data_update.fetch_all_employees", side_effect=RuntimeError("API timeout"))
    @patch("simple_contacts.data_update.azure_credentials_configured", return_value=True)
    def test_exception(self, mock_creds, mock_fetch, monkeypatch):
        from simple_contacts.data_update import load_data_update_status, update_employee_data

        monkeypatch.setattr("simple_contacts.data_update._APP_STARTUP_COMPLETE", True)
        update_employee_data(source="test")

        status = load_data_update_status()
        assert status["success"] is False
        assert "API timeout" in status.get("error", "")

    @patch("simple_contacts.data_update.azure_credentials_configured", return_value=True)
    def test_skips_when_already_running(self, mock_creds, monkeypatch):
        from simple_contacts.data_update import (
            load_data_update_status,
            mark_data_update_running,
            update_employee_data,
        )

        monkeypatch.setattr("simple_contacts.data_update._APP_STARTUP_COMPLETE", True)
        mark_data_update_running(source="other")

        # Should be a no-op since state is already running
        update_employee_data(source="test")

        status = load_data_update_status()
        assert status["state"] == "running"
        assert status["source"] == "other"
