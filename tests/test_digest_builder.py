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


def test_build_digest_entries_suggests_macro_and_energy_candidates() -> None:
    item = normalize_raw_item(
        {
            "source": "BBC World",
            "source_type": "rss",
            "title": "Hormuz shipping risk pushes crude oil higher",
            "body": "Iran tensions raise tanker and shipping concerns across energy markets.",
            "url": "https://example.com/hormuz-risk",
            "published_at": "2026-04-10T04:00:00Z",
            "tags": ["geopolitics", "oil", "shipping", "energy", "market-moving"],
            "score": 88,
        }
    )

    entry = build_digest_entries([item])[0]

    assert entry.impact_label in {"利好", "利空", "中性"}
    assert "相关股票" in entry.impact_assessment
    assert any(symbol in entry.candidate_symbols for symbol in ["XOM", "CVX", "601857.SH", "ZIM"])
    assert any(tag in entry.trigger_text for tag in ["地缘", "油运", "宏观", "中东"])


def test_a_share_geopolitics_candidates_prefer_energy_shipping_over_generic_ai() -> None:
    item = normalize_raw_item(
        {
            "source": "Eastmoney Company News",
            "source_type": "eastmoney",
            "title": "霍尔木兹海峡紧张局势升级 航运与原油价格波动",
            "body": "中东局势扰动提升原油与海运板块关注度。",
            "url": "https://example.com/hormuz-a-share",
            "published_at": "2026-04-10T04:00:00Z",
            "tags": ["a-shares", "company-news", "geopolitics", "oil", "shipping", "energy"],
            "score": 78,
        }
    )

    entry = build_digest_entries([item])[0]

    assert any(symbol in entry.candidate_symbols for symbol in ["XOM", "CVX", "600028.SH", "601857.SH"])
    assert "688256.SH" not in entry.candidate_symbols
