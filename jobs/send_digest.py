"""Build and deliver scheduled digests to WeCom."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from config.settings import get_settings, setup_logging
from digest.builder import build_digest_entries, render_digest_messages, select_digest_items
from jobs.schedule_utils import is_scheduled_run_due
from notify.wecom import WeComNotifier
from storage.db import Database

LOGGER = setup_logging("jobs.send_digest")


def send_digest(force: bool = False, scheduled: bool = False) -> dict[str, object]:
    """Send a digest of pending, unsent items."""
    settings = get_settings()
    started_at = datetime.now(UTC)
    db = Database()
    status = "success"
    error_message: str | None = None

    if scheduled and not force and not is_scheduled_run_due():
        ended_at = datetime.now(UTC)
        stats = {"skipped": True, "reason": "outside_schedule"}
        db.log_run("send_digest", started_at, ended_at, "skipped", stats)
        return stats

    try:
        candidate_limit = max(settings.max_digest_items * 4, settings.max_digest_items + 20)
        candidate_items = db.fetch_pending_digest_items(
            limit=candidate_limit,
            min_score=settings.digest_min_score,
        )
        items = select_digest_items(candidate_items, limit=settings.max_digest_items)
        if not items:
            stats = {"sent_messages": 0, "sent_items": 0, "skipped": True, "reason": "no_pending_items"}
            return stats

        notifier = WeComNotifier()
        if not notifier.webhook_url:
            raise ValueError("WECOM_WEBHOOK_URL is not configured.")

        use_markdown = notifier.message_format != "text"
        entries = build_digest_entries(items)
        title = f"\u91cd\u8981\u65b0\u95fb\u6458\u8981\uff08{len(entries)}\u6761\uff09"
        messages = render_digest_messages(entries, title=title, use_markdown=use_markdown)
        notifier.send_messages(messages)

        for item in items:
            db.mark_sent(item.id, "digest")

        stats = {"sent_messages": len(messages), "sent_items": len(items), "skipped": False}
        return stats
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Digest send failed.")
        status = "failed"
        error_message = str(exc)
        raise
    finally:
        ended_at = datetime.now(UTC)
        stats_to_log = locals().get("stats", {"scheduled": scheduled, "forced": force})
        db.log_run("send_digest", started_at, ended_at, status, stats_to_log, error_message)


def main() -> None:
    """CLI entry point for sending digests."""
    parser = argparse.ArgumentParser(description="Send a digest for unsent news items.")
    parser.add_argument("--force", action="store_true", help="Run even if outside the scheduled window.")
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Enable schedule gating before sending.",
    )
    args = parser.parse_args()
    stats = send_digest(force=args.force, scheduled=args.scheduled)
    LOGGER.info("Digest finished with stats: %s", stats)


if __name__ == "__main__":
    main()
