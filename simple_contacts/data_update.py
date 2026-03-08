"""Data update status tracking and sync logic for SimpleContacts."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import simple_contacts.config as app_config
from simple_contacts.msgraph import azure_credentials_configured, fetch_all_employees
from simple_contacts.settings import load_settings

logger = logging.getLogger(__name__)

DATA_DIR = str(app_config.DATA_DIR)
EMPLOYEE_LIST_FILE = str(app_config.EMPLOYEE_LIST_FILE)
DATA_UPDATE_STATUS_FILE = os.path.join(DATA_DIR, "data_update_status.json")

_DATA_UPDATE_STATUS_LOCK = threading.Lock()
_CURRENT_DATA_UPDATE_STATUS: Dict[str, Any] = {"state": "idle"}
_APP_STARTUP_COMPLETE = False


# ------------------------------------------------------------------
# Status persistence helpers
# ------------------------------------------------------------------

def _write_data_update_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    global _CURRENT_DATA_UPDATE_STATUS
    with _DATA_UPDATE_STATUS_LOCK:
        _CURRENT_DATA_UPDATE_STATUS = payload
        try:
            os.makedirs(os.path.dirname(DATA_UPDATE_STATUS_FILE), exist_ok=True)
            with open(DATA_UPDATE_STATUS_FILE, "w") as fh:
                json.dump(payload, fh, indent=2)
        except Exception as exc:
            logger.warning("Failed to write data update status: %s", exc)
    return payload


def load_data_update_status() -> Dict[str, Any]:
    """Load data update status from disk, resetting stale running states."""
    global _CURRENT_DATA_UPDATE_STATUS, _APP_STARTUP_COMPLETE
    stale_override = None

    with _DATA_UPDATE_STATUS_LOCK:
        if os.path.exists(DATA_UPDATE_STATUS_FILE):
            try:
                with open(DATA_UPDATE_STATUS_FILE, "r") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    _CURRENT_DATA_UPDATE_STATUS = data
            except Exception as exc:
                logger.warning("Failed to load data update status: %s", exc)

        state = (_CURRENT_DATA_UPDATE_STATUS or {}).get("state")
        if state == "running":
            if not _APP_STARTUP_COMPLETE:
                # First load after restart — previous run is stale
                stale_override = {
                    "state": "idle",
                    "success": False,
                    "finishedAt": datetime.now(timezone.utc).isoformat(),
                    "error": "Previous sync was interrupted by application restart.",
                }
            else:
                started_text = (_CURRENT_DATA_UPDATE_STATUS or {}).get("startedAt")
                try:
                    started_dt = datetime.fromisoformat(started_text) if started_text else None
                    if started_dt and started_dt.tzinfo is None:
                        started_dt = started_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    started_dt = None

                if started_dt:
                    elapsed = datetime.now(timezone.utc) - started_dt.astimezone(timezone.utc)
                    if elapsed > timedelta(hours=2):
                        stale_override = {
                            "state": "idle",
                            "success": False,
                            "finishedAt": datetime.now(timezone.utc).isoformat(),
                            "error": "Previous sync appeared stuck; automatically reset.",
                        }
                else:
                    stale_override = {
                        "state": "idle",
                        "success": False,
                        "finishedAt": datetime.now(timezone.utc).isoformat(),
                        "error": "Previous sync status was invalid; automatically reset.",
                    }

        if stale_override:
            last_success = (_CURRENT_DATA_UPDATE_STATUS or {}).get("lastSuccessAt")
            if last_success:
                stale_override["lastSuccessAt"] = last_success
            _CURRENT_DATA_UPDATE_STATUS = stale_override

        current_snapshot = dict(_CURRENT_DATA_UPDATE_STATUS)

    if stale_override:
        _write_data_update_status(stale_override)

    return current_snapshot


def mark_data_update_running(source: str = "unknown") -> Dict[str, Any]:
    """Mark data update as running."""
    previous_status = load_data_update_status()
    status: Dict[str, Any] = {
        "state": "running",
        "source": source,
        "startedAt": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(previous_status, dict) and previous_status.get("lastSuccessAt"):
        status["lastSuccessAt"] = previous_status["lastSuccessAt"]
    return _write_data_update_status(status)


def mark_data_update_finished(
    success: bool = True,
    error: Optional[str] = None,
    source: str = "unknown",
) -> Dict[str, Any]:
    """Mark data update as finished."""
    status: Dict[str, Any] = {
        "state": "idle",
        "success": bool(success),
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    if error:
        status["error"] = str(error)
    if success:
        status["lastSuccessAt"] = status["finishedAt"]
    else:
        previous_status = load_data_update_status()
        last_success = previous_status.get("lastSuccessAt") if isinstance(previous_status, dict) else None
        if last_success:
            status["lastSuccessAt"] = last_success
    return _write_data_update_status(status)


def mark_startup_complete() -> None:
    """Mark that app startup is complete (for stale status detection)."""
    global _APP_STARTUP_COMPLETE
    _APP_STARTUP_COMPLETE = True


# ------------------------------------------------------------------
# Main sync function (the scheduler callback)
# ------------------------------------------------------------------

def update_employee_data(source: str = "manual") -> None:
    """Fetch employees from Azure AD and persist to disk.

    This is the function passed to :func:`configure_scheduler` as the
    callback.  It can also be called directly (e.g. from the manual
    trigger endpoint).
    """
    current_status = load_data_update_status()
    if current_status.get("state") == "running":
        logger.warning("Sync already in progress; skipping (source=%s)", source)
        return

    if not azure_credentials_configured():
        logger.warning("Azure AD credentials not configured; cannot sync (source=%s)", source)
        mark_data_update_finished(success=False, error="Azure AD credentials are not configured.", source=source)
        return

    mark_data_update_running(source)
    logger.info("Starting employee data sync (source=%s)...", source)

    try:
        employees = fetch_all_employees()
        if not employees:
            raise RuntimeError("No employees returned from Graph API")

        # Persist
        emp_path = app_config.EMPLOYEE_LIST_FILE
        emp_path.parent.mkdir(parents=True, exist_ok=True)
        with emp_path.open("w", encoding="utf-8") as fh:
            json.dump(employees, fh, indent=2)

        logger.info("Synced %d employees from Azure AD (source=%s)", len(employees), source)
        mark_data_update_finished(success=True, source=source)

    except Exception as exc:
        logger.exception("Employee data sync failed (source=%s): %s", source, exc)
        mark_data_update_finished(success=False, error=str(exc), source=source)


__all__ = [
    "load_data_update_status",
    "mark_data_update_finished",
    "mark_data_update_running",
    "mark_startup_complete",
    "update_employee_data",
]
