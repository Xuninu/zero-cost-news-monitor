"""Normalized news schema and helper functions."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from dateutil import parser as date_parser
from pydantic import BaseModel, Field, field_validator

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
MULTISPACE_RE = re.compile(r"\s+")


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def clean_text(value: str | None) -> str:
    """Normalize whitespace and trim text."""
    if not value:
        return ""
    return MULTISPACE_RE.sub(" ", value).strip()


def detect_language(*values: str) -> str:
    """Detect whether the text is mostly Chinese or English."""
    joined = " ".join(filter(None, values))
    if not joined:
        return "unknown"
    return "zh" if CJK_RE.search(joined) else "en"


def parse_dt(value: Any) -> datetime | None:
    """Parse a datetime from a string or passthrough an existing datetime."""
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)

    try:
        parsed = date_parser.parse(str(value))
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def make_fingerprint(title: str, body: str) -> str:
    """Build a stable hash for title and body content."""
    payload = f"{clean_text(title).lower()}||{clean_text(body).lower()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_item_id(source: str, url: str, published_at: datetime | None, title: str) -> str:
    """Build a stable identifier for a normalized item."""
    published_token = published_at.isoformat() if published_at else ""
    payload = f"{source}|{url}|{published_token}|{clean_text(title).lower()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class NewsItem(BaseModel):
    """Canonical news item used across the pipeline."""

    id: str
    source: str
    source_type: str
    title: str
    body: str = ""
    url: str
    author: str = ""
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=utc_now)
    language: str = "unknown"
    tags: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    score: float = 0.0
    score_reasons: list[str] = Field(default_factory=list)
    is_urgent: bool = False
    fingerprint: str

    @field_validator("source", "source_type", "title", "body", "url", "author", mode="before")
    @classmethod
    def _clean_scalar(cls, value: Any) -> str:
        return clean_text("" if value is None else str(value))

    @field_validator("tags", "symbols", "score_reasons", mode="before")
    @classmethod
    def _clean_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            values = [value]
        else:
            values = list(value)
        cleaned = [clean_text(str(item)) for item in values if clean_text(str(item))]
        return list(dict.fromkeys(cleaned))

    @field_validator("published_at", "fetched_at", mode="before")
    @classmethod
    def _parse_datetimes(cls, value: Any) -> datetime | None:
        return parse_dt(value)


def normalize_raw_item(raw_item: dict[str, Any]) -> NewsItem:
    """Convert an ingested raw item into the canonical schema."""
    title = clean_text(raw_item.get("title"))
    body = clean_text(raw_item.get("body") or raw_item.get("summary") or raw_item.get("description"))
    url = clean_text(raw_item.get("url"))
    source = clean_text(raw_item.get("source"))
    source_type = clean_text(raw_item.get("source_type"))
    published_at = parse_dt(raw_item.get("published_at"))
    fetched_at = parse_dt(raw_item.get("fetched_at")) or utc_now()
    tags = raw_item.get("tags") or []
    symbols = raw_item.get("symbols") or []
    language = clean_text(raw_item.get("language")) or detect_language(title, body)
    fingerprint = clean_text(raw_item.get("fingerprint")) or make_fingerprint(title, body)
    item_id = clean_text(raw_item.get("id")) or make_item_id(source, url, published_at, title)

    return NewsItem(
        id=item_id,
        source=source,
        source_type=source_type,
        title=title,
        body=body,
        url=url,
        author=raw_item.get("author", ""),
        published_at=published_at,
        fetched_at=fetched_at,
        language=language,
        tags=tags,
        symbols=symbols,
        score=float(raw_item.get("score", 0.0) or 0.0),
        score_reasons=raw_item.get("score_reasons") or [],
        is_urgent=bool(raw_item.get("is_urgent", False)),
        fingerprint=fingerprint,
    )
