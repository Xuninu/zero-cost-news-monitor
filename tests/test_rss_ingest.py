"""Tests for RSS ingestion helpers."""

from __future__ import annotations

from ingest.rss_ingest import _entry_body


def test_entry_body_ignores_google_news_aggregator_summaries() -> None:
    entry = {"summary": "Google News boilerplate", "description": "Fallback text"}
    assert _entry_body("Google News Trump Markets", entry) == ""


def test_entry_body_keeps_regular_feed_summaries() -> None:
    entry = {"summary": "Regular summary", "description": "Fallback text"}
    assert _entry_body("BBC World", entry) == "Regular summary"
