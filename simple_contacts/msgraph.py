"""Microsoft Graph helpers for SimpleContacts."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

GRAPH_API_ENDPOINT = os.environ.get(
    "GRAPH_API_ENDPOINT", "https://graph.microsoft.com/v1.0"
)


def _graph_credentials() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    return (
        os.environ.get("AZURE_TENANT_ID"),
        os.environ.get("AZURE_CLIENT_ID"),
        os.environ.get("AZURE_CLIENT_SECRET"),
    )


def _resolve_credentials(
    tenant_id: Optional[str],
    client_id: Optional[str],
    client_secret: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if tenant_id and client_id and client_secret:
        return tenant_id, client_id, client_secret
    env_tenant, env_client, env_secret = _graph_credentials()
    return tenant_id or env_tenant, client_id or env_client, client_secret or env_secret


def get_access_token(
    *,
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> Optional[str]:
    """Exchange client credentials for a Microsoft Graph access token."""
    tenant_id, client_id, client_secret = _resolve_credentials(
        tenant_id, client_id, client_secret
    )
    if not all([tenant_id, client_id, client_secret]):
        logger.error(
            "AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET must be configured"
        )
        return None

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }

    try:
        response = requests.post(token_url, data=token_data, timeout=10)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.RequestException as exc:
        logger.error("Error getting access token: %s", exc)
        return None


def azure_credentials_configured() -> bool:
    """Return True when all three Azure env vars are present."""
    t, c, s = _graph_credentials()
    return bool(t and c and s)


def fetch_all_employees(
    *,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch user records from Microsoft Graph and return a flat list.

    The returned shape matches what the directory exports expect:
    name, email, phone, businessPhone, title, department, city, state,
    officeLocation, fullAddress, userPrincipalName, etc.
    """
    token = token or get_access_token()
    if not token:
        logger.error("Failed to get access token")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    select_fields = (
        "id,displayName,jobTitle,department,mail,userPrincipalName,"
        "mobilePhone,businessPhones,officeLocation,city,state,country,"
        "streetAddress,postalCode,accountEnabled,userType"
    )
    users_url = f"{GRAPH_API_ENDPOINT}/users?$select={select_fields}"

    employees: List[Dict[str, Any]] = []

    while users_url:
        try:
            response = requests.get(users_url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()

            if "value" not in data:
                break

            for user in data["value"]:
                # Skip disabled or guest accounts
                if not user.get("accountEnabled", True):
                    continue
                user_type = (user.get("userType") or "").lower()
                if user_type == "guest":
                    continue

                display_name = (user.get("displayName") or "").strip()
                if not display_name:
                    continue

                business_phones = user.get("businessPhones") or []
                business_phone = (
                    next((p for p in business_phones if p), "")
                    if isinstance(business_phones, list)
                    else str(business_phones)
                )

                primary_email = (
                    user.get("mail") or user.get("userPrincipalName") or ""
                )

                # Build full address
                address_parts: List[str] = []
                for field in ("streetAddress", "city", "state", "postalCode", "country"):
                    val = (user.get(field) or "").strip()
                    if val:
                        address_parts.append(val)

                employees.append(
                    {
                        "id": user.get("id"),
                        "name": display_name,
                        "title": user.get("jobTitle") or "",
                        "department": user.get("department") or "",
                        "email": primary_email.strip(),
                        "userPrincipalName": user.get("userPrincipalName") or "",
                        "phone": user.get("mobilePhone") or "",
                        "businessPhone": business_phone,
                        "officeLocation": user.get("officeLocation") or "",
                        "city": user.get("city") or "",
                        "state": user.get("state") or "",
                        "country": user.get("country") or "",
                        "fullAddress": ", ".join(address_parts),
                    }
                )

            users_url = data.get("@odata.nextLink")

        except requests.RequestException as exc:
            logger.error("Error fetching employees from Graph API: %s", exc)
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 401:
                logger.error("Authentication failed. Check your Azure credentials.")
            elif status_code == 403:
                logger.error(
                    "Permission denied. Ensure User.Read.All permission is granted."
                )
            break

    logger.info("Fetched %s employees from Microsoft Graph", len(employees))
    return employees


__all__ = [
    "azure_credentials_configured",
    "get_access_token",
    "fetch_all_employees",
]
