"""Background scheduler management for SimpleContacts."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, time as dt_time, timezone
from typing import Callable, Optional

import schedule

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

import simple_contacts.config as app_config
from simple_contacts.settings import load_settings

logger = logging.getLogger(__name__)

_scheduler_running = False
_scheduler_lock = threading.Lock()
_scheduler_thread: Optional[threading.Thread] = None
_update_callback: Optional[Callable[..., None]] = None
_lock_file_handle = None

DEFAULT_TIME_STRING = "20:00"
DEFAULT_TIMEZONE = "UTC"
SCHEDULER_LOCK_FILE = os.path.join(str(app_config.DATA_DIR), ".scheduler.lock")


def _resolve_timezone(tz_name: Optional[str]) -> timezone:
    """Resolve a timezone name to a timezone object."""
    if ZoneInfo is None:
        logger.warning("ZoneInfo module unavailable; falling back to UTC")
        return timezone.utc

    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            logger.warning("Invalid timezone '%s'; defaulting to UTC", tz_name)
    return ZoneInfo(DEFAULT_TIMEZONE)


def _parse_time_string(value: Optional[str]) -> dt_time:
    """Parse an ``HH:MM`` string into a :class:`datetime.time`."""
    candidate = (value or DEFAULT_TIME_STRING).strip()
    try:
        hour_str, minute_str = candidate.split(":", 1)
        hour = max(0, min(23, int(hour_str)))
        minute = max(0, min(59, int(minute_str)))
        return dt_time(hour=hour, minute=minute)
    except Exception:
        logger.warning("Invalid update time '%s'; defaulting to %s", value, DEFAULT_TIME_STRING)
        return dt_time(hour=20, minute=0)


def _compute_next_run(update_time: dt_time, tz: timezone) -> datetime:
    """Compute the next occurrence of *update_time* in *tz*, returned as UTC."""
    tz_now = datetime.now(tz)
    candidate = tz_now.replace(
        hour=update_time.hour, minute=update_time.minute, second=0, microsecond=0,
    )
    if candidate <= tz_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def configure_scheduler(update_callback: Callable[..., None]) -> None:
    """Register the callback used to refresh employee data."""
    global _update_callback
    _update_callback = update_callback


def is_scheduler_running() -> bool:
    """Return *True* if the background scheduler loop is active."""
    return _scheduler_running


def _ensure_callback() -> Callable[..., None]:
    if _update_callback is None:
        raise RuntimeError("Scheduler update callback has not been configured")
    return _update_callback


# ------------------------------------------------------------------
# Schedule loop
# ------------------------------------------------------------------

def _schedule_loop() -> None:  # noqa: C901 – intentionally consolidated
    global _scheduler_running

    try:
        update_callback = _ensure_callback()
    except RuntimeError as exc:
        logger.error(str(exc))
        _scheduler_running = False
        return

    schedule.clear()
    settings = load_settings()

    # --- initial update on startup ---
    run_initial = os.environ.get("RUN_INITIAL_UPDATE", "auto").lower()
    if run_initial == "true":
        logger.info("Running initial data sync on startup (RUN_INITIAL_UPDATE=true)...")
        update_callback(source="startup")
    elif run_initial == "auto":
        if not app_config.EMPLOYEE_LIST_FILE.exists():
            logger.info("No cached data found; running initial data sync...")
            update_callback(source="startup-no-cache")
        else:
            logger.info(
                "Cached data exists; skipping initial sync (set RUN_INITIAL_UPDATE=true to force)"
            )
    else:
        logger.info("Initial sync skipped (RUN_INITIAL_UPDATE=%s)", run_initial)

    # --- compute first scheduled run ---
    update_time = _parse_time_string(settings.get("updateTime"))
    tz = timezone.utc
    next_run_utc: Optional[datetime]

    if settings.get("autoUpdateEnabled", True):
        next_run_utc = _compute_next_run(update_time, tz)
        logger.info(
            "Scheduled daily sync for %s UTC; next run at %s",
            update_time.strftime("%H:%M"),
            next_run_utc.strftime("%Y-%m-%d %H:%M UTC"),
        )
    else:
        next_run_utc = None
        logger.info("Automatic sync is disabled; skipping daily schedule")

    # --- polling loop ---
    while _scheduler_running:
        if next_run_utc is not None and datetime.now(timezone.utc) >= next_run_utc:
            logger.info("Executing scheduled sync...")
            try:
                update_callback(source="scheduled")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Scheduled sync callback failed: %s", exc)

            # Re-read settings to pick up any changes
            settings = load_settings()
            update_time = _parse_time_string(settings.get("updateTime"))

            if settings.get("autoUpdateEnabled", True):
                next_run_utc = _compute_next_run(update_time, tz)
                logger.info(
                    "Next scheduled sync at %s UTC",
                    next_run_utc.strftime("%Y-%m-%d %H:%M"),
                )
            else:
                next_run_utc = None
                logger.info("Automatic sync disabled; halting further scheduling")

        time.sleep(30)


# ------------------------------------------------------------------
# Cross-process lock (Linux/Gunicorn multi-worker friendly)
# ------------------------------------------------------------------

def _acquire_scheduler_lock() -> bool:
    """Try to acquire cross-process scheduler lock."""
    global _lock_file_handle
    try:
        import fcntl

        os.makedirs(os.path.dirname(SCHEDULER_LOCK_FILE), exist_ok=True)
        _lock_file_handle = open(SCHEDULER_LOCK_FILE, "w")  # noqa: SIM115
        fcntl.flock(_lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
        return True
    except (ImportError, BlockingIOError, OSError):
        if _lock_file_handle:
            _lock_file_handle.close()
            _lock_file_handle = None
        return False


def _release_scheduler_lock() -> None:
    """Release the cross-process scheduler lock."""
    global _lock_file_handle
    if _lock_file_handle:
        try:
            import fcntl

            fcntl.flock(_lock_file_handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        _lock_file_handle.close()
        _lock_file_handle = None


# ------------------------------------------------------------------
# Start / Stop / Restart
# ------------------------------------------------------------------

def start_scheduler() -> None:
    """Start the background scheduler thread if it is not already running."""
    global _scheduler_running, _scheduler_thread

    with _scheduler_lock:
        if _scheduler_running:
            return

        if not _acquire_scheduler_lock():
            logger.debug("Scheduler lock held by another process; skipping start")
            return

        _scheduler_running = True
        _scheduler_thread = threading.Thread(target=_schedule_loop, daemon=True)
        _scheduler_thread.start()
        logger.info("Scheduler started")


def stop_scheduler() -> None:
    """Stop the background scheduler loop."""
    global _scheduler_running

    with _scheduler_lock:
        if not _scheduler_running:
            return
        _scheduler_running = False
        _release_scheduler_lock()
        logger.info("Scheduler stopped")


def restart_scheduler() -> None:
    """Restart the scheduler, reloading settings and timings."""
    stop_scheduler()
    time.sleep(2)
    schedule.clear()
    start_scheduler()


__all__ = [
    "configure_scheduler",
    "is_scheduler_running",
    "restart_scheduler",
    "start_scheduler",
    "stop_scheduler",
]
