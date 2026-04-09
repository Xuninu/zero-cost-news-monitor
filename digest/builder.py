"""Digest rendering helpers for WeCom delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import Iterable

from normalize.schema import NewsItem, clean_text


@dataclass(slots=True)
class DigestEntry:
    """Rendered entry ready for downstream formatting."""

    item_id: str
    title: str
    source: str
    time: str
    summary_zh: str
    summary_en: str
    impacted_assets: str
    score: float
    link: str


def build_digest_entries(items: Iterable[NewsItem]) -> list[DigestEntry]:
    """Convert scored items into digest entries."""
    entries: list[DigestEntry] = []
    for item in items:
        reference = (item.published_at or item.fetched_at).astimezone(UTC)
        assets = ", ".join(item.symbols[:3] + item.tags[:3]) or "n/a"
        entries.append(
            DigestEntry(
                item_id=item.id,
                title=item.title,
                source=item.source,
                time=reference.strftime("%Y-%m-%d %H:%M UTC"),
                summary_zh=_summary_zh(item),
                summary_en=_summary_en(item),
                impacted_assets=assets,
                score=item.score,
                link=item.url,
            )
        )
    return entries


def build_urgent_message(item: NewsItem, use_markdown: bool = True) -> str:
    """Render a single urgent alert message."""
    entry = build_digest_entries([item])[0]
    if use_markdown:
        return (
            "## Urgent News Alert\n"
            f"- **Title**: {entry.title}\n"
            f"- **Source**: {entry.source}\n"
            f"- **Time**: {entry.time}\n"
            f"- **CN**: {entry.summary_zh}\n"
            f"- **EN**: {entry.summary_en}\n"
            f"- **Assets**: {entry.impacted_assets}\n"
            f"- **Score**: {entry.score}\n"
            f"- **Link**: {entry.link}"
        )
    return (
        "URGENT NEWS ALERT\n"
        f"Title: {entry.title}\n"
        f"Source: {entry.source}\n"
        f"Time: {entry.time}\n"
        f"CN: {entry.summary_zh}\n"
        f"EN: {entry.summary_en}\n"
        f"Assets: {entry.impacted_assets}\n"
        f"Score: {entry.score}\n"
        f"Link: {entry.link}"
    )


def render_digest_messages(
    entries: list[DigestEntry],
    title: str,
    use_markdown: bool = True,
    max_chars: int = 3200,
) -> list[str]:
    """Chunk digest entries into message-sized payloads."""
    if not entries:
        return []

    chunks: list[str] = []
    current = _digest_header(title, use_markdown)

    for index, entry in enumerate(entries, start=1):
        block = _render_entry(entry, index, use_markdown)
        candidate = f"{current}\n\n{block}".strip()
        if len(candidate) > max_chars and current != _digest_header(title, use_markdown):
            chunks.append(current)
            current = f"{_digest_header(title, use_markdown)}\n\n{block}"
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


def _digest_header(title: str, use_markdown: bool) -> str:
    return f"## {title}" if use_markdown else title


def _render_entry(entry: DigestEntry, index: int, use_markdown: bool) -> str:
    if use_markdown:
        return (
            f"### {index}. {entry.title}\n"
            f"- Source: {entry.source}\n"
            f"- Time: {entry.time}\n"
            f"- CN: {entry.summary_zh}\n"
            f"- EN: {entry.summary_en}\n"
            f"- Assets: {entry.impacted_assets}\n"
            f"- Score: {entry.score}\n"
            f"- Link: {entry.link}"
        )
    return (
        f"{index}. {entry.title}\n"
        f"Source: {entry.source}\n"
        f"Time: {entry.time}\n"
        f"CN: {entry.summary_zh}\n"
        f"EN: {entry.summary_en}\n"
        f"Assets: {entry.impacted_assets}\n"
        f"Score: {entry.score}\n"
        f"Link: {entry.link}"
    )


def _summary_zh(item: NewsItem) -> str:
    lead = _lead_phrase(item)
    assets = _asset_phrase(item)
    return f"{lead}\uff1b\u5f71\u54cd\u9762\u805a\u7126 {assets}\u3002"


def _summary_en(item: NewsItem) -> str:
    lead = _lead_phrase(item, english=True)
    assets = _asset_phrase(item)
    return f"{lead}; watch {assets}."


def _lead_phrase(item: NewsItem, english: bool = False) -> str:
    title = clean_text(item.title)
    title = title[:110] + "..." if len(title) > 110 else title
    if english:
        return f"{item.source} reported: {title}"
    return f"{item.source} \u62a5\u9053\uff1a{title}"


def _asset_phrase(item: NewsItem) -> str:
    assets = item.symbols[:3] + item.tags[:3]
    return ", ".join(assets) if assets else "\u76f8\u5173\u4e3b\u9898\u8d44\u4ea7"
