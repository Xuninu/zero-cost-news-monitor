"""Tests for digest rendering helpers."""

from __future__ import annotations

from digest.builder import build_digest_entries, render_digest_messages
from normalize.schema import normalize_raw_item


def test_build_digest_entries_include_impact_and_candidates() -> None:
    item = normalize_raw_item(
        {
            "source": "OpenAI News",
            "source_type": "rss",
            "title": "OpenAI launches new reasoning model for enterprises",
            "body": "The new model improves enterprise agent workflows and cloud deployment.",
            "url": "https://example.com/openai-launch",
            "published_at": "2026-04-10T04:00:00Z",
            "tags": ["international-ai", "official", "frontier-models"],
            "symbols": ["NVDA"],
            "score": 82,
        }
    )

    entry = build_digest_entries([item])[0]

    assert entry.source == "OpenAI\u5b98\u65b9\u65b0\u95fb"
    assert entry.priority_label == "\u91cd\u70b9"
    assert entry.impact_label == "\u5229\u597d"
    assert "\u504f\u5229\u597d" in entry.impact_assessment
    assert entry.candidate_symbols.startswith("NVDA")
    assert "\u6a21\u578b" in entry.trigger_text


def test_render_digest_messages_follow_market_alert_layout() -> None:
    item = normalize_raw_item(
        {
            "source": "OpenAI News",
            "source_type": "rss",
            "title": "OpenAI launches new reasoning model for enterprises",
            "body": "The new model improves enterprise agent workflows and cloud deployment.",
            "url": "https://example.com/openai-launch",
            "published_at": "2026-04-10T04:00:00Z",
            "tags": ["international-ai", "official", "frontier-models"],
            "symbols": ["NVDA"],
            "score": 82,
        }
    )

    entries = build_digest_entries([item, item])
    message = render_digest_messages(entries, title="unused", use_markdown=False)[0]

    assert "\u5e02\u573a\u63d0\u9192" in message
    assert "[\u91cd\u70b9\u00b7\u5229\u597d\u00b7\u884c\u4e1a]" in message
    assert "\u5019\u9009\u6807\u7684\uff1a" in message
    assert "\u5f71\u54cd\u5224\u65ad\uff1a" in message
    assert "\u89e6\u53d1\u56e0\u7d20\uff1a" in message
    assert "\u7efc\u5408\u5206\uff1a" in message
    assert "\n\n2. " in message
    assert "Source:" not in message
    assert "EN:" not in message
