"""Tests for digest rendering helpers."""

from __future__ import annotations

from digest.builder import build_digest_entries, render_digest_messages
from normalize.schema import normalize_raw_item


def test_build_digest_entries_prefers_chinese_digest_fields() -> None:
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
        }
    )

    entry = build_digest_entries([item])[0]

    assert entry.source == "OpenAI 官方新闻"
    assert "北京时间" not in entry.time
    assert "发布" in entry.summary_zh
    assert entry.summary_en == ""
    assert "NVDA" in entry.impacted_assets


def test_render_digest_messages_uses_chinese_labels_and_blank_lines_between_entries() -> None:
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
        }
    )

    entries = build_digest_entries([item, item])
    message = render_digest_messages(entries, title="重要新闻摘要（2条）", use_markdown=False)[0]

    assert "来源：" in message
    assert "时间：" in message
    assert "摘要：" in message
    assert "原文：" in message
    assert "\n\n2. " in message
    assert "EN:" not in message
    assert "Source:" not in message
