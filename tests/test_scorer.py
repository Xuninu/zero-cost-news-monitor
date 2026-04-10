"""Tests for the rule-based scorer."""

from __future__ import annotations

from normalize.schema import normalize_raw_item
from score.scorer import RuleBasedScorer


def test_rule_based_scorer_boosts_keywords_tickers_and_official_sources() -> None:
    scorer = RuleBasedScorer(
        keyword_config={
            "scoring": {
                "urgent_threshold": 40,
                "official_source_boost": 10,
                "duplicate_penalty_per_match": 5,
                "max_duplicate_penalty": 15,
                "default_source_weight": 1,
                "source_weights": {"rss": 2},
                "source_name_weights": {"OpenAI": 5},
                "recency_boosts": [{"max_hours": 24, "boost": 8}],
                "keyword_groups": [
                    {
                        "label": "AI launch",
                        "weight": 12,
                        "tags": ["international-ai"],
                        "terms": ["model release", "gpt-5"],
                    }
                ],
                "urgency_keywords": [
                    {"label": "Breaking", "boost": 10, "terms": ["breaking"]},
                ],
            }
        },
        ticker_config={
            "tickers": [
                {"symbol": "NVDA", "weight": 6, "aliases": ["nvidia"], "tags": ["semiconductors"]},
            ]
        },
    )
    item = normalize_raw_item(
        {
            "source": "OpenAI",
            "source_type": "rss",
            "title": "Breaking: GPT-5 model release boosts NVIDIA demand",
            "body": "A new model release could increase Nvidia GPU demand.",
            "url": "https://example.com/openai-gpt5",
            "published_at": "2026-04-09T12:00:00Z",
            "tags": ["official"],
        }
    )

    result = scorer.score_item(item)

    assert result.total_score >= 40
    assert result.is_urgent is True
    assert "NVDA" in result.matched_symbols
    assert "international-ai" in result.matched_tags


def test_rule_based_scorer_handles_geopolitics_and_oil_shipping_signals() -> None:
    scorer = RuleBasedScorer(
        keyword_config={
            "scoring": {
                "urgent_threshold": 60,
                "official_source_boost": 0,
                "duplicate_penalty_per_match": 0,
                "max_duplicate_penalty": 0,
                "default_source_weight": 2,
                "source_weights": {"rss": 4},
                "source_name_weights": {"BBC World": 6},
                "recency_boosts": [{"max_hours": 24, "boost": 8}],
                "keyword_groups": [
                    {
                        "label": "Geopolitics oil shipping shock",
                        "weight": 24,
                        "tags": ["geopolitics", "oil", "shipping"],
                        "terms": ["iran", "hormuz", "oil", "shipping"],
                    }
                ],
                "urgency_keywords": [
                    {"label": "Geopolitical shock", "boost": 20, "terms": ["attack", "missile"]},
                ],
            }
        },
        ticker_config={
            "tickers": [
                {"symbol": "XOM", "weight": 8, "aliases": ["oil"], "tags": ["energy"]},
                {"symbol": "ZIM", "weight": 8, "aliases": ["shipping"], "tags": ["shipping"]},
            ]
        },
    )
    item = normalize_raw_item(
        {
            "source": "BBC World",
            "source_type": "rss",
            "title": "Iran threat around Hormuz sparks attack fears for oil shipping",
            "body": "A missile attack risk could push oil and shipping shares higher.",
            "url": "https://example.com/hormuz-oil-shipping",
            "published_at": "2026-04-10T01:00:00Z",
        }
    )

    result = scorer.score_item(item)

    assert result.total_score >= 60
    assert result.is_urgent is True
    assert "XOM" in result.matched_symbols
    assert "ZIM" in result.matched_symbols
    assert "geopolitics" in result.matched_tags
