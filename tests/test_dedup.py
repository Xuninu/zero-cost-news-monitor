"""Tests for URL normalization and duplicate detection."""

from __future__ import annotations

from dedup.dedup import DuplicateCandidate, evaluate_duplicate, normalize_url
from normalize.schema import normalize_raw_item


def test_normalize_url_strips_tracking_parameters_and_fragment() -> None:
    url = "https://example.com/story?utm_source=test&id=123&fbclid=abc#section"
    assert normalize_url(url) == "https://example.com/story?id=123"


def test_evaluate_duplicate_detects_title_similarity() -> None:
    item = normalize_raw_item(
        {
            "source": "Source A",
            "source_type": "rss",
            "title": "OpenAI launches a new AI model for enterprises",
            "body": "",
            "url": "https://example.com/a",
        }
    )
    candidates = [
        DuplicateCandidate(
            item_id="existing-1",
            title="OpenAI launches new AI model for enterprise users",
            url="https://example.com/b",
        )
    ]

    result = evaluate_duplicate(item, None, candidates, similarity_threshold=0.85)

    assert result.is_duplicate is True
    assert result.reason == "title_similarity"
