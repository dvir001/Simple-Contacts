"""Flask application for SimpleContacts."""

from __future__ import annotations

import atexit
import json
import logging
import os
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

from .auth import login_required, require_auth, sanitize_next_path, build_auth_code_flow, acquire_token
from .config import (
    DATA_DIR,
    EMPLOYEE_LIST_FILE,
    MAX_CUSTOM_CONTACTS,
    SSO_AUTHORITY,
    SSO_REDIRECT_PATH,
    STATIC_DIR,
    TEMPLATE_DIR,
    ensure_directories,
    sso_configured,
)
from .data_update import (
    load_data_update_status,
    mark_startup_complete,
    update_employee_data,
)
from .exports import build_microsip_directory_items, build_yealink_phonebook_xml
from .msgraph import azure_credentials_configured, fetch_all_employees
from .scheduler import (
    configure_scheduler,
    is_scheduler_running,
    restart_scheduler,
    start_scheduler,
    stop_scheduler,
)
from .settings import DEFAULT_SETTINGS, load_settings, save_settings

logger = logging.getLogger(__name__)

ensure_directories()

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    template_folder=str(TEMPLATE_DIR),
)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_employees():
    """Load employee list from disk, returning a list of dicts."""
    if not EMPLOYEE_LIST_FILE.exists():
        return []
    try:
        with EMPLOYEE_LIST_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("Failed to load employee list: %s", exc)
        return []


def _save_employees(employees: list) -> bool:
    """Persist employee list to disk."""
    EMPLOYEE_LIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with EMPLOYEE_LIST_FILE.open("w", encoding="utf-8") as fh:
            json.dump(employees, fh, indent=2)
        return True
    except Exception as exc:
        logger.error("Failed to save employee list: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Authentication routes
# ---------------------------------------------------------------------------

def _build_redirect_uri() -> str:
    """Build the OAuth redirect URI, respecting X-Forwarded-Proto."""
    uri = request.url_root.rstrip("/") + SSO_REDIRECT_PATH
    forwarded_proto = request.headers.get("X-Forwarded-Proto")
    if forwarded_proto:
        uri = uri.replace("http://", f"{forwarded_proto}://", 1)
    return uri


@app.route("/login")
def login_page():
    """Render the login page.

    When SSO is configured the page shows a *Sign in with Microsoft* button.
    The password form is only displayed as a fallback when SSO is **not**
    configured.
    """
    return render_template(
        "login.html",
        sso_enabled=sso_configured(),
    )


@app.route("/login/sso")
def login_sso():
    """Initiate Azure AD SSO by redirecting to the Microsoft login page."""
    if not sso_configured():
        return redirect(url_for("login_page"))

    try:
        flow = build_auth_code_flow(redirect_uri=_build_redirect_uri())
    except Exception:
        logger.exception("Failed to initiate Azure AD auth code flow")
        return render_template("login.html", sso_enabled=True, error="Failed to start SSO login.")

    session["auth_flow"] = flow
    auth_uri = flow.get("auth_uri")
    if not auth_uri:
        logger.error("MSAL auth flow did not return an auth_uri")
        return render_template("login.html", sso_enabled=True, error="SSO configuration error.")

    return redirect(auth_uri)


@app.route(SSO_REDIRECT_PATH)
def auth_callback():
    """Handle the OAuth2 redirect callback from Azure AD."""
    flow = session.pop("auth_flow", None)
    if not flow:
        logger.warning("Auth callback received without a pending auth flow")
        return redirect(url_for("login_page"))

    try:
        result = acquire_token(flow, request.args)
    except Exception:
        logger.exception("Error acquiring token from Azure AD")
        return render_template("login.html", sso_enabled=True, error="Authentication failed.")

    if "error" in result:
        error_desc = result.get("error_description", result.get("error", "Unknown error"))
        logger.error("Azure AD authentication error: %s", error_desc)
        safe_error = str(error_desc)[:200].replace("<", "&lt;").replace(">", "&gt;")
        return render_template("login.html", sso_enabled=True, error=f"Authentication failed: {safe_error}")

    # Successful SSO – populate session
    claims = result.get("id_token_claims", {})
    session["authenticated"] = True
    session["auth_method"] = "sso"
    session["user_name"] = claims.get("name", claims.get("preferred_username", "User"))
    session["user_email"] = claims.get("preferred_username", "")

    next_path = sanitize_next_path(session.pop("login_next", None))
    return redirect(next_path or url_for("configure"))


@app.route("/login/password", methods=["POST"])
def login_password():
    """Password-based login (fallback when SSO is not configured)."""
    if sso_configured():
        # Password form is disabled when SSO is active
        return redirect(url_for("login_page"))

    password = request.form.get("password", "")
    expected = os.environ.get("APP_PASSWORD", "admin")
    if password == expected:
        session["authenticated"] = True
        session["auth_method"] = "password"
        return redirect(url_for("configure"))
    return render_template("login.html", sso_enabled=False, error="Invalid password"), 401


@app.route("/logout")
def logout():
    """Clear session and redirect.

    When SSO was used, also sign out of the Azure AD session.
    """
    auth_method = session.get("auth_method")
    session.clear()

    if auth_method == "sso" and SSO_AUTHORITY:
        post_logout = request.url_root.rstrip("/")
        forwarded_proto = request.headers.get("X-Forwarded-Proto")
        if forwarded_proto:
            proto = forwarded_proto.split(",")[0].strip().lower()
            if proto in ("http", "https"):
                post_logout = post_logout.replace("http://", f"{proto}://", 1)
        from urllib.parse import quote
        azure_logout = (
            f"{SSO_AUTHORITY}/oauth2/v2.0/logout"
            f"?post_logout_redirect_uri={quote(post_logout, safe='')}"
        )
        return redirect(azure_logout)

    return redirect(url_for("login_page"))


# ---------------------------------------------------------------------------
# UI routes
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def index():
    """Redirect root to configure page."""
    return redirect(url_for("configure"))


@app.route("/configure")
@login_required
def configure():
    """Render the configure page."""
    return render_template("configure.html")


# ---------------------------------------------------------------------------
# Settings API
# ---------------------------------------------------------------------------

@app.route("/api/settings", methods=["GET"])
@require_auth
def get_settings():
    """Return current application settings + sync status."""
    settings = load_settings()
    settings["dataUpdateStatus"] = load_data_update_status()
    settings["maxCustomContacts"] = MAX_CUSTOM_CONTACTS
    return jsonify(settings)


@app.route("/api/settings", methods=["POST"])
@require_auth
def post_settings():
    """Update application settings."""
    try:
        payload = request.get_json(force=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Expected JSON object"}), 400

        current = load_settings()
        for key in DEFAULT_SETTINGS:
            if key in payload:
                current[key] = payload[key]

        # Enforce custom contacts limit
        raw = current.get("customDirectoryContacts", "")
        lines = [l.strip() for l in raw.split("\n") if l.strip() and not l.strip().startswith("#")]
        if len(lines) > MAX_CUSTOM_CONTACTS:
            return jsonify({"error": f"Custom contacts limit is {MAX_CUSTOM_CONTACTS}"}), 400

        if save_settings(current):
            # Restart scheduler if sync-related settings changed
            if "updateTime" in payload or "autoUpdateEnabled" in payload:
                threading.Thread(target=restart_scheduler, daemon=True).start()
            return jsonify({"status": "ok", "settings": current})
        return jsonify({"error": "Failed to save settings"}), 500
    except Exception as exc:
        logger.error("Error in POST /api/settings: %s", exc)
        return jsonify({"error": "Internal server error while updating settings"}), 500


# ---------------------------------------------------------------------------
# Config export / import
# ---------------------------------------------------------------------------

@app.route("/api/settings/export", methods=["GET"])
@require_auth
def export_settings():
    """Download current settings as a JSON file (no employee data)."""
    settings = load_settings()
    payload = json.dumps(settings, indent=2)
    return Response(
        payload,
        mimetype="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="simple-contacts-config.json"',
        },
    )


@app.route("/api/settings/import", methods=["POST"])
@require_auth
def import_settings():
    """Import settings from an uploaded JSON file."""
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "No file uploaded"}), 400

    try:
        raw = uploaded.read()
        incoming = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Config import: invalid JSON – %s", exc)
        return jsonify({"error": "Invalid JSON file"}), 400

    if not isinstance(incoming, dict):
        return jsonify({"error": "Expected a JSON object"}), 400

    # Only accept known setting keys
    current = load_settings()
    for key in DEFAULT_SETTINGS:
        if key in incoming:
            current[key] = incoming[key]

    # Enforce custom contacts limit
    raw_contacts = current.get("customDirectoryContacts", "")
    lines = [l.strip() for l in raw_contacts.split("\n") if l.strip() and not l.strip().startswith("#")]
    if len(lines) > MAX_CUSTOM_CONTACTS:
        return jsonify({"error": f"Custom contacts limit is {MAX_CUSTOM_CONTACTS}"}), 400

    if save_settings(current):
        # Restart scheduler if sync-related settings changed
        if "updateTime" in incoming or "autoUpdateEnabled" in incoming:
            threading.Thread(target=restart_scheduler, daemon=True).start()
        return jsonify({"status": "ok", "settings": current})
    return jsonify({"error": "Failed to save imported settings"}), 500


@app.route("/api/settings/reset", methods=["POST"])
@require_auth
def reset_settings():
    """Reset all settings back to defaults."""
    if save_settings(DEFAULT_SETTINGS):
        threading.Thread(target=restart_scheduler, daemon=True).start()
        logger.info("Settings reset to defaults")
        return jsonify({"status": "ok", "settings": DEFAULT_SETTINGS.copy()})
    return jsonify({"error": "Failed to reset settings"}), 500


# ---------------------------------------------------------------------------
# Employee data API
# ---------------------------------------------------------------------------

@app.route("/api/employees", methods=["GET"])
@require_auth
def get_employees():
    """Return current employee list."""
    return jsonify(_load_employees())


@app.route("/api/employees", methods=["DELETE"])
@require_auth
def clear_employees():
    """Remove all employee data."""
    try:
        if EMPLOYEE_LIST_FILE.exists():
            EMPLOYEE_LIST_FILE.unlink()
        return jsonify({"status": "ok"})
    except Exception as exc:
        logger.error("Error clearing employees: %s", exc)
        return jsonify({"error": "Internal server error while clearing employees"}), 500


# ---------------------------------------------------------------------------
# Azure AD sync
# ---------------------------------------------------------------------------

@app.route("/api/azure/status", methods=["GET"])
@require_auth
def azure_status():
    """Return whether Azure AD credentials are configured."""
    return jsonify({"configured": azure_credentials_configured()})


@app.route("/api/azure/sync", methods=["POST"])
@require_auth
def azure_sync():
    """Fetch employees from Microsoft Graph and persist them."""
    if not azure_credentials_configured():
        return jsonify({"error": "Azure AD credentials are not configured"}), 400

    try:
        employees = fetch_all_employees()
        if not employees:
            return jsonify({"error": "No employees returned from Graph API"}), 502

        if _save_employees(employees):
            return jsonify({"status": "ok", "count": len(employees)})
        return jsonify({"error": "Failed to save employee data"}), 500
    except Exception as exc:
        logger.error("Azure sync error: %s", exc)
        return jsonify({"error": "Azure sync failed due to an internal error"}), 500


# ---------------------------------------------------------------------------
# Manual update trigger
# ---------------------------------------------------------------------------

@app.route("/api/update-now", methods=["POST"])
@require_auth
def trigger_update():
    """Kick off a manual data sync in a background thread."""
    current_status = load_data_update_status()
    if current_status.get("state") == "running":
        return jsonify({"error": "Update already in progress"}), 409

    worker = threading.Thread(
        target=update_employee_data,
        kwargs={"source": "manual"},
        daemon=True,
    )
    worker.start()
    return jsonify({"message": "Update started"}), 200


# ---------------------------------------------------------------------------
# Directory feed routes (public – consumed by phones)
# ---------------------------------------------------------------------------

@app.route("/directory/<filename>.json")
def microsip_directory(filename: str):
    """Serve MicroSIP-compatible JSON directory."""
    settings = load_settings()
    if not settings.get("directoryJsonEnabled"):
        return jsonify({"error": "JSON directory feed is disabled"}), 404

    expected_name = settings.get("directoryJsonFilename", "contacts")
    if filename != expected_name:
        return jsonify({"error": "Not found"}), 404

    employees = _load_employees()
    items = build_microsip_directory_items(employees, settings=settings)
    return jsonify(items)


@app.route("/directory/<filename>.xml")
def yealink_directory(filename: str):
    """Serve Yealink-compatible XML phonebook."""
    settings = load_settings()

    expected_name = (settings.get("directoryXmlFilename") or "contacts").strip() or "contacts"
    if filename != expected_name:
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?>\n<Error>Not found</Error>',
            status=404,
            mimetype="application/xml",
        )

    if not settings.get("directoryXmlEnabled"):
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?>\n<Error>Directory feed is disabled</Error>',
            status=403,
            mimetype="application/xml",
        )

    employees = _load_employees()
    directory_title = settings.get("directoryTitle", "Organization Directory")
    xml_content = build_yealink_phonebook_xml(
        employees, settings=settings, title=directory_title,
    )

    response = Response(xml_content, status=200, mimetype="application/xml")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = f'inline; filename="{expected_name}.xml"'
    return response


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    """Return basic health status."""
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Development server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    debug_env = os.environ.get("FLASK_DEBUG", "").lower()
    debug = debug_env in ("1", "true", "t", "yes")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=debug)


# ---------------------------------------------------------------------------
# Scheduler wiring
# ---------------------------------------------------------------------------

configure_scheduler(update_employee_data)
mark_startup_complete()

if hasattr(app, "before_serving"):
    @app.before_serving
    def _start_scheduler_when_ready():
        start_scheduler()

    @app.after_serving
    def _stop_scheduler_on_shutdown():
        stop_scheduler()
elif hasattr(app, "before_request"):
    _scheduler_started = False

    @app.before_request
    def _ensure_scheduler_started():
        global _scheduler_started
        if not _scheduler_started:
            _scheduler_started = True
            start_scheduler()

atexit.register(stop_scheduler)
