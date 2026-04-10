"""Build and deliver scheduled digests to WeCom."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from config.settings import get_settings, setup_logging
from digest.builder import build_digest_entries, render_digest_messages, select_digest_items
from digest.filtering import DEFAULT_DELIVERY_MAX_AGE_HOURS, is_item_within_age, merge_digest_items
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
        candidate_limit = max(settings.max_digest_items * 20, settings.max_digest_items + 50)
        recent_items = db.fetch_recent_items(
            hours=max(6, int(DEFAULT_DELIVERY_MAX_AGE_HOURS) + 1),
            limit=candidate_limit,
        )
        candidate_items = [
            item
            for item in recent_items
            if item.score >= settings.digest_min_score
            and not db.has_been_sent(item.id)
            and is_item_within_age(item, max_age_hours=DEFAULT_DELIVERY_MAX_AGE_HOURS)
        ]
        merged_candidates = merge_digest_items(
            candidate_items,
            similarity_threshold=settings.title_similarity_threshold,
        )
        selected_items = select_digest_items(
            [cluster.item for cluster in merged_candidates],
            limit=settings.max_digest_items,
        )
        if not selected_items:
            stats = {
                "sent_messages": 0,
                "sent_topics": 0,
                "sent_items": 0,
                "skipped": True,
                "reason": "no_fresh_items",
            }
            return stats

        notifier = WeComNotifier()
        if not notifier.webhook_url:
            raise ValueError("WECOM_WEBHOOK_URL is not configured.")

        cluster_by_id = {cluster.item.id: cluster for cluster in merged_candidates}
        selected_clusters = [cluster_by_id[item.id] for item in selected_items if item.id in cluster_by_id]
        use_markdown = notifier.message_format != "text"
        entries = build_digest_entries([cluster.item for cluster in selected_clusters])
        title = f"重要新闻摘要（{len(entries)}条）"
        messages = render_digest_messages(entries, title=title, use_markdown=use_markdown)
        notifier.send_messages(messages)

        for cluster in selected_clusters:
            for item_id in cluster.item_ids:
                db.mark_sent(item_id, "digest")

        stats = {
            "sent_messages": len(messages),
            "sent_topics": len(selected_clusters),
            "sent_items": sum(len(cluster.item_ids) for cluster in selected_clusters),
            "skipped": False,
        }
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
