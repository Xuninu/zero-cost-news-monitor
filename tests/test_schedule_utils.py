"""Tests for GitHub Actions schedule gating."""

from __future__ import annotations

from datetime import datetime

from jobs.schedule_utils import is_scheduled_run_due


def test_is_scheduled_run_due_allows_delay_within_half_hour_slot() -> None:
    scheduled_time = datetime.fromisoformat("2026-04-10T10:29:00+08:00")
    assert is_scheduled_run_due(scheduled_time, "Asia/Shanghai") is True


def test_is_scheduled_run_due_rejects_times_outside_delivery_window() -> None:
    outside_window = datetime.fromisoformat("2026-04-10T16:10:00+08:00")
    assert is_scheduled_run_due(outside_window, "Asia/Shanghai") is False
