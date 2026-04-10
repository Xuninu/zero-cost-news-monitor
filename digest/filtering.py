"""Freshness and delivery-time topic merging helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from dedup.dedup import normalize_url, title_similarity
from digest.builder import SOURCE_NAME_ZH
from normalize.schema import NewsItem, clean_text

DEFAULT_DELIVERY_MAX_AGE_HOURS = 5.0


@dataclass(slots=True)
class MergedDigestItem:
    """A delivery-ready topic that may contain the same story from multiple sources."""

    item: NewsItem
    item_ids: list[str]
    source_names: list[str]


def is_item_within_age(
    item: NewsItem,
    max_age_hours: float = DEFAULT_DELIVERY_MAX_AGE_HOURS,
    now: datetime | None = None,
) -> bool:
    """Return whether an item is recent enough for delivery."""
    reference = item.published_at or item.fetched_at
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=max_age_hours)
    return reference >= cutoff


def merge_digest_items(items: list[NewsItem], similarity_threshold: float) -> list[MergedDigestItem]:
    """Merge repeated stories from different sources into a single delivery topic."""
    clusters: list[MergedDigestItem] = []
    merge_threshold = max(0.82, similarity_threshold - 0.06)

    for item in sorted(items, key=_sort_key, reverse=True):
        match: MergedDigestItem | None = None
        for cluster in clusters:
            if _is_same_story(item, cluster.item, similarity_threshold=merge_threshold):
                match = cluster
                break

        if match is None:
            clusters.append(
                MergedDigestItem(
                    item=_copy_item(item),
                    item_ids=[item.id],
                    source_names=[_source_display_name(item.source)],
                )
            )
            continue

        merged_source_names = _dedupe(match.source_names + [_source_display_name(item.source)])
        representative = _preferred_item(match.item, item)
        merged_item = _copy_item(representative)
        merged_item.tags = _dedupe(match.item.tags + item.tags)
        merged_item.symbols = _dedupe(match.item.symbols + item.symbols)
        merged_item.score_reasons = _dedupe(match.item.score_reasons + item.score_reasons)
        merged_item.body = clean_text(f"{match.item.body} {item.body}")
        merged_item.score = max(match.item.score, item.score)
        merged_item.is_urgent = match.item.is_urgent or item.is_urgent
        merged_item.published_at = _later_datetime(match.item.published_at, item.published_at)
        merged_item.fetched_at = max(match.item.fetched_at, item.fetched_at)
        merged_item.source = _render_source_line(merged_source_names)

        match.item = merged_item
        match.item_ids = _dedupe(match.item_ids + [item.id])
        match.source_names = merged_source_names

    return clusters


def _is_same_story(left: NewsItem, right: NewsItem, similarity_threshold: float) -> bool:
    if normalize_url(left.url) == normalize_url(right.url):
        return True
    if clean_text(left.title).lower() == clean_text(right.title).lower():
        return True
    return title_similarity(left.title, right.title) >= similarity_threshold


def _preferred_item(left: NewsItem, right: NewsItem) -> NewsItem:
    left_key = (
        1 if _contains_cjk(left.title) else 0,
        1 if left.is_urgent else 0,
        left.score,
        left.published_at or left.fetched_at,
    )
    right_key = (
        1 if _contains_cjk(right.title) else 0,
        1 if right.is_urgent else 0,
        right.score,
        right.published_at or right.fetched_at,
    )
    return right if right_key > left_key else left


def _sort_key(item: NewsItem) -> tuple[int, float, datetime]:
    reference = item.published_at or item.fetched_at
    return (1 if item.is_urgent else 0, item.score, reference)


def _copy_item(item: NewsItem) -> NewsItem:
    copied = item.model_copy(deep=True)
    copied.source = _source_display_name(copied.source)
    return copied


def _source_display_name(source: str) -> str:
    normalized = clean_text(source)
    return SOURCE_NAME_ZH.get(normalized, normalized or "资讯来源")


def _render_source_line(source_names: list[str]) -> str:
    if not source_names:
        return "资讯来源"
    primary = source_names[0]
    extras = source_names[1:]
    if not extras:
        return primary
    if len(extras) > 3:
        return f"{primary}；补充来源：{'、'.join(extras[:3])}等{len(extras)}个来源"
    return f"{primary}；补充来源：{'、'.join(extras)}"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(clean_text(value) for value in values if clean_text(value)))


def _later_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    if left and right:
        return left if left >= right else right
    return left or right


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)
