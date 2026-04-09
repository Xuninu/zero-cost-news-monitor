"""URL and title similarity deduplication helpers."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from normalize.schema import NewsItem, clean_text

TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "spm",
    "src",
    "source",
}


@dataclass(slots=True)
class DuplicateCandidate:
    """Existing item details used for title similarity checks."""

    item_id: str
    title: str
    url: str


@dataclass(slots=True)
class DuplicateCheckResult:
    """Result of duplicate evaluation for a candidate item."""

    is_duplicate: bool
    reason: str | None
    matched_item_id: str | None
    strongest_similarity: float
    similar_count: int


def normalize_url(url: str) -> str:
    """Normalize URLs to make direct duplicate checks more reliable."""
    parsed = urlparse(url.strip())
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    normalized = parsed._replace(
        netloc=parsed.netloc.lower(),
        query=urlencode(filtered_query, doseq=True),
        fragment="",
    )
    normalized_url = urlunparse(normalized).rstrip("/")
    return normalized_url


def title_similarity(left: str, right: str) -> float:
    """Return a ratio between 0 and 1 for two titles."""
    left_clean = clean_text(left).lower()
    right_clean = clean_text(right).lower()
    if not left_clean or not right_clean:
        return 0.0
    return SequenceMatcher(a=left_clean, b=right_clean).ratio()


def evaluate_duplicate(
    item: NewsItem,
    existing_url_item_id: str | None,
    recent_candidates: Iterable[DuplicateCandidate],
    similarity_threshold: float,
) -> DuplicateCheckResult:
    """Evaluate whether an item is a duplicate using URL first, then title similarity."""
    if existing_url_item_id:
        return DuplicateCheckResult(
            is_duplicate=True,
            reason="normalized_url",
            matched_item_id=existing_url_item_id,
            strongest_similarity=1.0,
            similar_count=1,
        )

    strongest_similarity = 0.0
    strongest_match_id: str | None = None
    similar_count = 0
    soft_threshold = max(0.75, similarity_threshold - 0.12)

    for candidate in recent_candidates:
        similarity = title_similarity(item.title, candidate.title)
        if similarity > strongest_similarity:
            strongest_similarity = similarity
            strongest_match_id = candidate.item_id
        if similarity >= similarity_threshold:
            return DuplicateCheckResult(
                is_duplicate=True,
                reason="title_similarity",
                matched_item_id=candidate.item_id,
                strongest_similarity=similarity,
                similar_count=similar_count + 1,
            )
        if similarity >= soft_threshold:
            similar_count += 1

    return DuplicateCheckResult(
        is_duplicate=False,
        reason=None,
        matched_item_id=strongest_match_id,
        strongest_similarity=strongest_similarity,
        similar_count=similar_count,
    )
