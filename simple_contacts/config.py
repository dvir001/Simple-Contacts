"""Configuration and path helpers for SimpleContacts."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"

SETTINGS_FILE = DATA_DIR / "app_settings.json"
EMPLOYEE_LIST_FILE = DATA_DIR / "employee_list.json"
DATA_UPDATE_STATUS_FILE = DATA_DIR / "data_update_status.json"

MAX_CUSTOM_CONTACTS = int(os.environ.get("MAX_CUSTOM_CONTACTS", "200"))

# ---------------------------------------------------------------------------
# Azure AD SSO (separate app registration from the Graph/data-sync app)
# ---------------------------------------------------------------------------
SSO_CLIENT_ID = os.environ.get("SSO_CLIENT_ID", "")
SSO_TENANT_ID = os.environ.get("SSO_TENANT_ID", "")
SSO_CLIENT_SECRET = os.environ.get("SSO_CLIENT_SECRET", "")
SSO_REDIRECT_PATH = os.environ.get("SSO_REDIRECT_PATH", "/auth/callback")
SSO_AUTHORITY = (
    f"https://login.microsoftonline.com/{SSO_TENANT_ID}" if SSO_TENANT_ID else ""
)
SSO_SCOPES = ["User.Read"]


def sso_configured() -> bool:
    """Return True when all required SSO environment variables are set."""
    return bool(SSO_CLIENT_ID and SSO_TENANT_ID and SSO_CLIENT_SECRET)


def ensure_directories() -> None:
    """Ensure that the application's data and static directories exist."""
    for target in (DATA_DIR, STATIC_DIR):
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            logger.warning("Failed to create directory %s: %s", target, error)


__all__ = [
    "BASE_DIR",
    "DATA_DIR",
    "STATIC_DIR",
    "TEMPLATE_DIR",
    "SETTINGS_FILE",
    "EMPLOYEE_LIST_FILE",
    "DATA_UPDATE_STATUS_FILE",
    "MAX_CUSTOM_CONTACTS",
    "SSO_CLIENT_ID",
    "SSO_TENANT_ID",
    "SSO_CLIENT_SECRET",
    "SSO_REDIRECT_PATH",
    "SSO_AUTHORITY",
    "SSO_SCOPES",
    "sso_configured",
    "ensure_directories",
]
