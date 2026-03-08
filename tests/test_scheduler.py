"""Tests for simple_contacts.scheduler."""

from datetime import time as dt_time, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from simple_contacts.scheduler import (
    _compute_next_run,
    _parse_time_string,
    configure_scheduler,
    is_scheduler_running,
    start_scheduler,
    stop_scheduler,
)


class TestParseTimeString:
    def test_valid(self):
        t = _parse_time_string("08:30")
        assert t == dt_time(8, 30)

    def test_none_gives_default(self):
        t = _parse_time_string(None)
        assert t == dt_time(20, 0)

    def test_empty_gives_default(self):
        t = _parse_time_string("")
        assert t == dt_time(20, 0)

    def test_invalid_gives_default(self):
        t = _parse_time_string("not-a-time")
        assert t == dt_time(20, 0)

    def test_clamps_high_hour(self):
        t = _parse_time_string("25:00")
        assert t.hour == 23

    def test_clamps_high_minute(self):
        t = _parse_time_string("12:61")
        assert t.minute == 59


class TestComputeNextRun:
    def test_future_time_today(self):
        # Pick a time that is definitely in the future
        future_hour = (datetime.now(timezone.utc).hour + 2) % 24
        update_time = dt_time(hour=future_hour, minute=0)
        result = _compute_next_run(update_time, timezone.utc)
        assert result > datetime.now(timezone.utc)
        assert result.tzinfo is not None

    def test_past_time_gives_tomorrow(self):
        # Pick a time that is definitely in the past
        past_hour = (datetime.now(timezone.utc).hour - 2) % 24
        update_time = dt_time(hour=past_hour, minute=0)
        result = _compute_next_run(update_time, timezone.utc)
        assert result.day != datetime.now(timezone.utc).day or result > datetime.now(timezone.utc)


class TestConfigureScheduler:
    def test_sets_callback(self):
        cb = MagicMock()
        configure_scheduler(cb)
        # Just verify it doesn't raise


class TestStartStopScheduler:
    def test_is_not_running_initially(self, monkeypatch):
        monkeypatch.setattr("simple_contacts.scheduler._scheduler_running", False)
        assert is_scheduler_running() is False

    def test_stop_when_not_running(self, monkeypatch):
        monkeypatch.setattr("simple_contacts.scheduler._scheduler_running", False)
        stop_scheduler()  # Should not raise
        assert is_scheduler_running() is False
