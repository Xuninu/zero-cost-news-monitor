"""Collect, normalize, score, store, and optionally alert on new items."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from typing import Any

from config.settings import get_settings, load_yaml_config, setup_logging
from dedup.dedup import DuplicateCandidate, evaluate_duplicate
from digest.builder import build_urgent_message
from digest.filtering import DEFAULT_DELIVERY_MAX_AGE_HOURS, is_item_within_age
from ingest.eastmoney_ingest import fetch_eastmoney_items
from ingest.rss_ingest import fetch_rss_items
from ingest.site_ingest import fetch_site_items
from ingest.x_ingest import fetch_x_items
from ingest.youtube_ingest import fetch_youtube_channel_entries
from jobs.schedule_utils import is_scheduled_run_due
from normalize.schema import NewsItem, normalize_raw_item
from notify.wecom import WeComNotifier
from score.scorer import RuleBasedScorer
from storage.db import Database

LOGGER = setup_logging("jobs.run_pipeline")


def collect_raw_items(
    sources_config: dict[str, Any],
    only_sources: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    """Collect raw items from all enabled source families."""
    collectors = {
        "youtube": fetch_youtube_channel_entries,
        "eastmoney": fetch_eastmoney_items,
        "rss": fetch_rss_items,
        "site": fetch_site_items,
        "x": fetch_x_items,
    }

    raw_items: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    errors: list[str] = []

    for source_name, collector in collectors.items():
        if only_sources and source_name not in only_sources:
            continue
        try:
            items = collector(sources_config)
            raw_items.extend(items)
            counts[source_name] = len(items)
        except Exception as exc:  # noqa: BLE001
            message = f"{source_name}: {exc}"
            LOGGER.exception("Collector failed for %s", source_name)
            errors.append(message)
            counts[source_name] = 0

    return raw_items, counts, errors


def process_raw_items(
    raw_items: list[dict[str, Any]],
    db: Database | None = None,
    scorer: RuleBasedScorer | None = None,
    notifier: WeComNotifier | None = None,
    send_urgent: bool = True,
) -> dict[str, Any]:
    """Normalize, deduplicate, score, persist, and optionally alert items."""
    settings = get_settings()
    db = db or Database()
    scorer = scorer or RuleBasedScorer()
    notifier = notifier or WeComNotifier()
    similarity_threshold = settings.title_similarity_threshold
    stats: dict[str, Any] = {
        "input_items": len(raw_items),
        "invalid_items": 0,
        "duplicate_url": 0,
        "duplicate_title": 0,
        "stored_items": 0,
        "urgent_sent": 0,
        "stale_urgent_skipped": 0,
        "errors": [],
    }

    recent_candidates = db.fetch_recent_title_candidates()

    for raw_item in raw_items:
        try:
            item = normalize_raw_item(raw_item)
            if not item.title or not item.url or not item.source or not item.source_type:
                stats["invalid_items"] += 1
                continue

            duplicate = evaluate_duplicate(
                item=item,
                existing_url_item_id=db.find_item_id_by_url(item.url),
                recent_candidates=recent_candidates,
                similarity_threshold=similarity_threshold,
            )
            if duplicate.is_duplicate:
                if duplicate.reason == "normalized_url":
                    stats["duplicate_url"] += 1
                else:
                    stats["duplicate_title"] += 1
                continue

            score_result = scorer.score_item(item, duplicate_count=duplicate.similar_count)
            item = _apply_score_result(item, score_result)
            db.upsert_item(item)
            recent_candidates.insert(0, DuplicateCandidate(item.id, item.title, item.url))
            stats["stored_items"] += 1

            if send_urgent and item.is_urgent and not db.has_been_sent(item.id):
                if not is_item_within_age(item, max_age_hours=DEFAULT_DELIVERY_MAX_AGE_HOURS):
                    stats["stale_urgent_skipped"] += 1
                    continue
                if notifier.webhook_url:
                    use_markdown = notifier.message_format != "text"
                    notifier.send_message(build_urgent_message(item, use_markdown=use_markdown))
                    db.mark_sent(item.id, "urgent")
                    stats["urgent_sent"] += 1
                else:
                    LOGGER.warning("Urgent item detected but WECOM_WEBHOOK_URL is not configured.")
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Failed to process raw item.")
            stats["errors"].append(str(exc))

    return stats


def run_pipeline(
    force: bool = False,
    only_sources: list[str] | None = None,
    scheduled: bool = False,
    bootstrap: bool = False,
) -> dict[str, Any]:
    """Run the end-to-end collection and scoring pipeline."""
    started_at = datetime.now(UTC)
    db = Database()
    status = "success"
    error_message: str | None = None

    if scheduled and not force and not is_scheduled_run_due():
        ended_at = datetime.now(UTC)
        stats = {"skipped": True, "reason": "outside_schedule"}
        db.log_run("run_pipeline", started_at, ended_at, "skipped", stats)
        return stats

    try:
        sources_config = load_yaml_config("sources.yaml")
        source_filter = {name.strip().lower() for name in only_sources or [] if name.strip()}
        raw_items, collector_counts, collector_errors = collect_raw_items(
            sources_config=sources_config,
            only_sources=source_filter or None,
        )
        processing_stats = process_raw_items(raw_items, db=db, send_urgent=not bootstrap)
        bootstrap_marked_sent = 0
        if bootstrap:
            pending_items = db.fetch_pending_digest_items(limit=10_000, min_score=0.0)
            for item in pending_items:
                db.mark_sent(item.id, "bootstrap")
            bootstrap_marked_sent = len(pending_items)
        stats = {
            "scheduled": scheduled,
            "forced": force,
            "bootstrap": bootstrap,
            "collector_counts": collector_counts,
            "collector_errors": collector_errors,
            "bootstrap_marked_sent": bootstrap_marked_sent,
            **processing_stats,
        }
        if collector_errors or processing_stats["errors"]:
            status = "partial_success"
        return stats
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Pipeline run failed.")
        status = "failed"
        error_message = str(exc)
        raise
    finally:
        ended_at = datetime.now(UTC)
        stats_to_log = locals().get("stats", {"scheduled": scheduled, "forced": force})
        db.log_run("run_pipeline", started_at, ended_at, status, stats_to_log, error_message)


def _apply_score_result(item: NewsItem, score_result: Any) -> NewsItem:
    item.score = score_result.total_score
    item.score_reasons = score_result.reasons
    item.is_urgent = score_result.is_urgent
    item.tags = list(dict.fromkeys(item.tags + score_result.matched_tags))
    item.symbols = list(dict.fromkeys(item.symbols + score_result.matched_symbols))
    return item


def main() -> None:
    """CLI entry point for local runs and GitHub Actions."""
    parser = argparse.ArgumentParser(description="Run the zero-cost news pipeline.")
    parser.add_argument("--force", action="store_true", help="Run even if outside the scheduled window.")
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Enable schedule gating before running collectors.",
    )
    parser.add_argument(
        "--sources",
        nargs="*",
        help="Optional source families to run, for example: youtube rss eastmoney.",
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Collect and store items, but suppress urgent pushes and mark them as already sent.",
    )
    args = parser.parse_args()

    stats = run_pipeline(
        force=args.force,
        only_sources=args.sources,
        scheduled=args.scheduled,
        bootstrap=args.bootstrap,
    )
    LOGGER.info("Pipeline finished with stats: %s", stats)


if __name__ == "__main__":
    main()
