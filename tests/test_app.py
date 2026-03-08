"""Tests for SimpleContacts Flask routes."""

import json
from unittest.mock import patch

from simple_contacts.config import EMPLOYEE_LIST_FILE
from tests.conftest import SAMPLE_EMPLOYEES


class TestHealthRoute:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestAuthRoutes:
    def test_login_page(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_password_login_success(self, client):
        resp = client.post("/login/password", data={"password": "testpass"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_password_login_failure(self, client):
        resp = client.post("/login/password", data={"password": "wrong"})
        assert resp.status_code == 401

    def test_password_login_blocked_when_sso(self, client, monkeypatch):
        """Password POST redirects to login page when SSO is configured."""
        monkeypatch.setattr("simple_contacts.app_main.sso_configured", lambda: True)
        resp = client.post("/login/password", data={"password": "testpass"}, follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_logout(self, auth_client):
        resp = auth_client.get("/logout", follow_redirects=False)
        assert resp.status_code == 302

    def test_unauthenticated_redirect(self, client):
        resp = client.get("/configure", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_sso_login_redirect(self, client, monkeypatch):
        """When SSO is not configured, /login/sso redirects to login page."""
        resp = client.get("/login/sso", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


class TestSettingsAPI:
    def test_get_settings_unauthenticated(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 401

    def test_get_settings(self, auth_client):
        resp = auth_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "directoryJsonEnabled" in data

    def test_post_settings(self, auth_client):
        resp = auth_client.post(
            "/api/settings",
            data=json.dumps({"directoryJsonEnabled": True}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["settings"]["directoryJsonEnabled"] is True


class TestEmployeeAPI:
    def _seed_employees(self):
        """Write sample employees directly to the data file."""
        EMPLOYEE_LIST_FILE.write_text(json.dumps(SAMPLE_EMPLOYEES), encoding="utf-8")

    def test_get_employees(self, auth_client):
        self._seed_employees()
        resp = auth_client.get("/api/employees")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    def test_clear_employees(self, auth_client):
        self._seed_employees()
        resp = auth_client.delete("/api/employees")
        assert resp.status_code == 200

        resp = auth_client.get("/api/employees")
        assert resp.get_json() == []


class TestDirectoryFeeds:
    def _setup_data(self, auth_client):
        auth_client.post(
            "/api/settings",
            data=json.dumps({
                "directoryJsonEnabled": True,
                "directoryJsonFilename": "microsip",
                "directoryXmlEnabled": True,
                "directoryXmlFilename": "yealink",
            }),
            content_type="application/json",
        )
        EMPLOYEE_LIST_FILE.write_text(json.dumps(SAMPLE_EMPLOYEES), encoding="utf-8")

    def test_json_feed(self, auth_client, client):
        self._setup_data(auth_client)
        resp = client.get("/directory/microsip.json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_xml_feed(self, auth_client, client):
        self._setup_data(auth_client)
        resp = client.get("/directory/yealink.xml")
        assert resp.status_code == 200
        assert b"YealinkIPPhoneDirectory" in resp.data

    def test_json_feed_disabled(self, client):
        resp = client.get("/directory/microsip.json")
        assert resp.status_code == 404

    def test_xml_feed_disabled(self, client):
        resp = client.get("/directory/yealink.xml")
        assert resp.status_code == 403

    def test_wrong_filename_404(self, auth_client, client):
        self._setup_data(auth_client)
        resp = client.get("/directory/wrong.json")
        assert resp.status_code == 404


class TestAzureRoutes:
    def test_azure_status_unauthenticated(self, client):
        resp = client.get("/api/azure/status")
        assert resp.status_code == 401

    @patch("simple_contacts.app_main.azure_credentials_configured", return_value=False)
    def test_azure_status_not_configured(self, mock_creds, auth_client):
        resp = auth_client.get("/api/azure/status")
        assert resp.status_code == 200
        assert resp.get_json()["configured"] is False

    @patch("simple_contacts.app_main.azure_credentials_configured", return_value=True)
    def test_azure_status_configured(self, mock_creds, auth_client):
        resp = auth_client.get("/api/azure/status")
        assert resp.status_code == 200
        assert resp.get_json()["configured"] is True

    @patch("simple_contacts.app_main.azure_credentials_configured", return_value=False)
    def test_azure_sync_no_credentials(self, mock_creds, auth_client):
        resp = auth_client.post("/api/azure/sync")
        assert resp.status_code == 400
        assert "not configured" in resp.get_json()["error"]

    @patch("simple_contacts.app_main.fetch_all_employees", return_value=SAMPLE_EMPLOYEES)
    @patch("simple_contacts.app_main.azure_credentials_configured", return_value=True)
    def test_azure_sync_success(self, mock_creds, mock_fetch, auth_client):
        resp = auth_client.post("/api/azure/sync")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["count"] == 2

        # Verify data was persisted
        resp = auth_client.get("/api/employees")
        assert len(resp.get_json()) == 2

    @patch("simple_contacts.app_main.fetch_all_employees", return_value=[])
    @patch("simple_contacts.app_main.azure_credentials_configured", return_value=True)
    def test_azure_sync_empty_result(self, mock_creds, mock_fetch, auth_client):
        resp = auth_client.post("/api/azure/sync")
        assert resp.status_code == 502

    def test_azure_sync_unauthenticated(self, client):
        resp = client.post("/api/azure/sync")
        assert resp.status_code == 401


class TestUpdateNowRoute:
    def test_unauthenticated(self, client):
        resp = client.post("/api/update-now")
        assert resp.status_code == 401

    @patch("simple_contacts.app_main.load_data_update_status", return_value={"state": "idle"})
    @patch("simple_contacts.app_main.update_employee_data")
    def test_trigger_success(self, mock_update, mock_status, auth_client):
        resp = auth_client.post("/api/update-now")
        assert resp.status_code == 200
        assert "started" in resp.get_json()["message"].lower()

    @patch("simple_contacts.app_main.load_data_update_status", return_value={"state": "running"})
    def test_trigger_already_running(self, mock_status, auth_client):
        resp = auth_client.post("/api/update-now")
        assert resp.status_code == 409


class TestSettingsDataUpdateStatus:
    def test_settings_include_data_update_status(self, auth_client):
        resp = auth_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "dataUpdateStatus" in data

    def test_settings_include_auto_update_fields(self, auth_client):
        resp = auth_client.get("/api/settings")
        data = resp.get_json()
        assert "autoUpdateEnabled" in data
        assert "updateTime" in data

    def test_settings_include_max_custom_contacts(self, auth_client):
        resp = auth_client.get("/api/settings")
        data = resp.get_json()
        assert "maxCustomContacts" in data
        assert isinstance(data["maxCustomContacts"], int)
        assert data["maxCustomContacts"] == 200


class TestCustomContactsLimit:
    def test_save_within_limit(self, auth_client, monkeypatch):
        monkeypatch.setattr("simple_contacts.app_main.MAX_CUSTOM_CONTACTS", 5)
        contacts = "\n".join(f"Contact {i}, {1000 + i}" for i in range(5))
        resp = auth_client.post(
            "/api/settings",
            data=json.dumps({"customDirectoryContacts": contacts}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_save_exceeds_limit(self, auth_client, monkeypatch):
        monkeypatch.setattr("simple_contacts.app_main.MAX_CUSTOM_CONTACTS", 3)
        contacts = "\n".join(f"Contact {i}, {1000 + i}" for i in range(5))
        resp = auth_client.post(
            "/api/settings",
            data=json.dumps({"customDirectoryContacts": contacts}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "limit" in resp.get_json()["error"].lower()

    def test_blank_lines_not_counted(self, auth_client, monkeypatch):
        monkeypatch.setattr("simple_contacts.app_main.MAX_CUSTOM_CONTACTS", 2)
        contacts = "Alice, 100\n\n# comment\nBob, 200\n\n"
        resp = auth_client.post(
            "/api/settings",
            data=json.dumps({"customDirectoryContacts": contacts}),
            content_type="application/json",
        )
        assert resp.status_code == 200
