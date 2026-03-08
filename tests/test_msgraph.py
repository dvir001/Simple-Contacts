"""Tests for simple_contacts.msgraph."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from simple_contacts.msgraph import (
    azure_credentials_configured,
    fetch_all_employees,
    get_access_token,
)


class TestAzureCredentialsConfigured:
    def test_all_set(self, monkeypatch):
        monkeypatch.setenv("AZURE_TENANT_ID", "t")
        monkeypatch.setenv("AZURE_CLIENT_ID", "c")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "s")
        assert azure_credentials_configured() is True

    def test_missing_one(self, monkeypatch):
        monkeypatch.setenv("AZURE_TENANT_ID", "t")
        monkeypatch.setenv("AZURE_CLIENT_ID", "c")
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        assert azure_credentials_configured() is False

    def test_all_missing(self, monkeypatch):
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        assert azure_credentials_configured() is False


class TestGetAccessToken:
    def test_missing_credentials(self, monkeypatch):
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        assert get_access_token() is None

    @patch("simple_contacts.msgraph.requests.post")
    def test_successful_token(self, mock_post, monkeypatch):
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")
        monkeypatch.setenv("AZURE_CLIENT_ID", "client-123")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "secret-123")

        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "my-token"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        token = get_access_token()
        assert token == "my-token"
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "tenant-123" in call_url

    @patch("simple_contacts.msgraph.requests.post")
    def test_network_error(self, mock_post, monkeypatch):
        monkeypatch.setenv("AZURE_TENANT_ID", "t")
        monkeypatch.setenv("AZURE_CLIENT_ID", "c")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "s")

        import requests
        mock_post.side_effect = requests.RequestException("timeout")
        assert get_access_token() is None


class TestFetchAllEmployees:
    @patch("simple_contacts.msgraph.get_access_token")
    def test_no_token(self, mock_token):
        mock_token.return_value = None
        result = fetch_all_employees()
        assert result == []

    @patch("simple_contacts.msgraph.requests.get")
    @patch("simple_contacts.msgraph.get_access_token")
    def test_single_page(self, mock_token, mock_get):
        mock_token.return_value = "tok"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "u1",
                    "displayName": "Alice Smith",
                    "jobTitle": "Engineer",
                    "department": "Eng",
                    "mail": "alice@ex.com",
                    "userPrincipalName": "alice@ex.com",
                    "mobilePhone": "555-1234",
                    "businessPhones": ["555-0001"],
                    "officeLocation": "Building A",
                    "city": "Seattle",
                    "state": "WA",
                    "country": "US",
                    "accountEnabled": True,
                    "userType": "Member",
                },
                {
                    "id": "u2",
                    "displayName": "Guest User",
                    "accountEnabled": True,
                    "userType": "Guest",
                },
                {
                    "id": "u3",
                    "displayName": "Disabled User",
                    "accountEnabled": False,
                    "userType": "Member",
                },
                {
                    "id": "u4",
                    "displayName": "",
                    "accountEnabled": True,
                    "userType": "Member",
                },
            ]
        }
        mock_get.return_value = mock_response

        result = fetch_all_employees(token="tok")

        # Only Alice should come through (guest, disabled, and no-name are skipped)
        assert len(result) == 1
        assert result[0]["name"] == "Alice Smith"
        assert result[0]["email"] == "alice@ex.com"
        assert result[0]["businessPhone"] == "555-0001"
        assert result[0]["city"] == "Seattle"

    @patch("simple_contacts.msgraph.requests.get")
    @patch("simple_contacts.msgraph.get_access_token")
    def test_pagination(self, mock_token, mock_get):
        mock_token.return_value = "tok"

        page1_resp = MagicMock()
        page1_resp.raise_for_status = MagicMock()
        page1_resp.json.return_value = {
            "value": [
                {"id": "u1", "displayName": "Alice", "accountEnabled": True, "userType": "Member"},
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?$skiptoken=abc",
        }

        page2_resp = MagicMock()
        page2_resp.raise_for_status = MagicMock()
        page2_resp.json.return_value = {
            "value": [
                {"id": "u2", "displayName": "Bob", "accountEnabled": True, "userType": "Member"},
            ],
        }

        mock_get.side_effect = [page1_resp, page2_resp]

        result = fetch_all_employees(token="tok")
        assert len(result) == 2
        assert mock_get.call_count == 2

    @patch("simple_contacts.msgraph.requests.get")
    @patch("simple_contacts.msgraph.get_access_token")
    def test_network_error_returns_partial(self, mock_token, mock_get):
        mock_token.return_value = "tok"

        import requests as req
        mock_get.side_effect = req.RequestException("fail")

        result = fetch_all_employees(token="tok")
        assert result == []

    @patch("simple_contacts.msgraph.requests.get")
    @patch("simple_contacts.msgraph.get_access_token")
    def test_full_address_composition(self, mock_token, mock_get):
        mock_token.return_value = "tok"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "u1",
                    "displayName": "Alice",
                    "accountEnabled": True,
                    "userType": "Member",
                    "streetAddress": "123 Main St",
                    "city": "Seattle",
                    "state": "WA",
                    "postalCode": "98101",
                    "country": "US",
                },
            ]
        }
        mock_get.return_value = mock_response

        result = fetch_all_employees(token="tok")
        assert result[0]["fullAddress"] == "123 Main St, Seattle, WA, 98101, US"
