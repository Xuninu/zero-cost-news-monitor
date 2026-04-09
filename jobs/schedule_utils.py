"""Shared scheduling helpers for local runs and GitHub Actions gating."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config.settings import get_settings

HALF_HOUR_WINDOW_HOURS = set(range(5, 15))
TWO_HOUR_WINDOW_HOURS = {1, 3, 15, 17, 19, 21, 23}


def is_scheduled_run_due(now: datetime | None = None, timezone_name: str | None = None) -> bool:
    """Return whether the current time matches the configured delivery schedule."""
    settings = get_settings()
    tz = ZoneInfo(timezone_name or settings.pipeline_schedule_timezone)
    current = now.astimezone(tz) if now else datetime.now(tz)
    if current.minute in {0, 30} and current.hour in HALF_HOUR_WINDOW_HOURS:
        return True
    return current.minute == 0 and current.hour in TWO_HOUR_WINDOW_HOURS


def schedule_description() -> str:
    """Human-readable description of the production schedule."""
    return (
        "Every 30 minutes from 05:00 to 14:30 Asia/Shanghai, "
        "then every 2 hours at 15:00, 17:00, 19:00, 21:00, 23:00, 01:00, 03:00."
    )
