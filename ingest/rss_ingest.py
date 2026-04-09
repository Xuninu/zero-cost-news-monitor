"""RSS ingestion for configurable feed sources."""

from __future__ import annotations

from typing import Any

import feedparser
import httpx

from config.settings import get_settings
from normalize.schema import utc_now


def fetch_rss_items(
    sources_config: dict[str, Any],
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Fetch all enabled RSS feeds from the config file."""
    feeds = [
        feed
        for feed in sources_config.get("rss", {}).get("feeds", [])
        if feed.get("enabled", False)
    ]
    if not feeds:
        return []

    timeout = get_settings().request_timeout_seconds
    own_client = client or httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (news-monitor/0.1)"},
    )
    items: list[dict[str, Any]] = []

    try:
        for feed in feeds:
            response = own_client.get(feed["url"])
            response.raise_for_status()
            parsed = feedparser.parse(response.text)
            max_entries = int(feed.get("max_entries", 20))
            for entry in parsed.entries[:max_entries]:
                items.append(
                    {
                        "source": feed["name"],
                        "source_type": "rss",
                        "title": entry.get("title", ""),
                        "body": entry.get("summary", "") or entry.get("description", ""),
                        "url": entry.get("link", ""),
                        "author": entry.get("author", feed["name"]),
                        "published_at": entry.get("published", "") or entry.get("updated", ""),
                        "fetched_at": utc_now(),
                        "tags": list(feed.get("tags", [])) + (["official"] if feed.get("official") else []),
                    }
                )
    finally:
        if client is None:
            own_client.close()

    return items
