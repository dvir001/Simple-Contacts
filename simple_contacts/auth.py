"""Authentication helpers for SimpleContacts.

Supports Azure AD SSO (primary) with password-based login as a fallback.
When SSO is configured the password form is auto-disabled.
"""

from __future__ import annotations

import logging
import re
from functools import wraps
from typing import Optional

from flask import jsonify, redirect, request, session, url_for

logger = logging.getLogger(__name__)

# Allowed next-path pattern (relative paths only, no protocol/host)
_SAFE_NEXT_RE = re.compile(r"^/[a-zA-Z0-9_./-]*$")


def sanitize_next_path(raw: Optional[str]) -> str:
    """Return *raw* only if it looks like a safe relative path, else ''."""
    if raw and _SAFE_NEXT_RE.match(raw):
        return raw
    return ""


# ---------------------------------------------------------------------------
# MSAL / Azure AD SSO helpers
# ---------------------------------------------------------------------------

def _build_msal_app(cache=None):
    """Build a confidential MSAL client application."""
    import msal
    from .config import SSO_AUTHORITY, SSO_CLIENT_ID, SSO_CLIENT_SECRET

    return msal.ConfidentialClientApplication(
        SSO_CLIENT_ID,
        authority=SSO_AUTHORITY,
        client_credential=SSO_CLIENT_SECRET or None,
        token_cache=cache,
    )


def build_auth_code_flow(scopes=None, redirect_uri=None):
    """Initiate an authorisation-code flow and return the flow dict."""
    from .config import SSO_SCOPES

    return _build_msal_app().initiate_auth_code_flow(
        scopes or SSO_SCOPES,
        redirect_uri=redirect_uri,
    )


def acquire_token(flow, auth_response):
    """Complete the auth-code flow and return the MSAL result dict."""
    return _build_msal_app().acquire_token_by_auth_code_flow(flow, auth_response)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def require_auth(fn):
    """Decorator that returns 401 JSON when the session is not authenticated."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify({"error": "Authentication required"}), 401
        return fn(*args, **kwargs)

    return wrapper


def login_required(fn):
    """Decorator that redirects to /login for browser requests."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("authenticated"):
            desired = sanitize_next_path(request.path)
            params = {"next": desired} if desired else {}
            return redirect(url_for("login_page", **params))
        return fn(*args, **kwargs)

    return wrapper
