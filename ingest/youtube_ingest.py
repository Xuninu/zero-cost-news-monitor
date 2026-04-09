"""YouTube ingestion via public RSS polling and webhook payload parsing."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import feedparser
import httpx

from config.settings import get_settings
from normalize.schema import utc_now

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def fetch_youtube_channel_entries(
    sources_config: dict[str, Any],
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Fetch the public RSS feed for each enabled YouTube channel."""
    channels = [
        channel
        for channel in sources_config.get("youtube", {}).get("channels", [])
        if channel.get("enabled", False)
    ]
    if not channels or not sources_config.get("youtube", {}).get("polling_enabled", True):
        return []

    timeout = get_settings().request_timeout_seconds
    own_client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    items: list[dict[str, Any]] = []

    try:
        for channel in channels:
            url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['id']}"
            response = own_client.get(url)
            response.raise_for_status()
            feed = feedparser.parse(response.text)
            max_entries = int(channel.get("max_entries", 15))
            for entry in feed.entries[:max_entries]:
                items.append(
                    {
                        "source": channel["name"],
                        "source_type": "youtube",
                        "title": entry.get("title", ""),
                        "body": entry.get("summary", ""),
                        "url": entry.get("link", ""),
                        "author": entry.get("author", channel["name"]),
                        "published_at": entry.get("published", "") or entry.get("updated", ""),
                        "fetched_at": utc_now(),
                        "tags": list(channel.get("tags", [])),
                    }
                )
    finally:
        if client is None:
            own_client.close()

    return items


def parse_youtube_webhook(payload: bytes, sources_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a YouTube PubSubHubbub webhook payload into raw items."""
    root = ET.fromstring(payload)
    channel_lookup = {
        str(channel["id"]): channel
        for channel in sources_config.get("youtube", {}).get("channels", [])
    }
    items: list[dict[str, Any]] = []

    for entry in root.findall("atom:entry", ATOM_NS):
        channel_id = entry.findtext("yt:channelId", default="", namespaces=ATOM_NS)
        channel_config = channel_lookup.get(channel_id, {})
        author_name = entry.findtext("atom:author/atom:name", default="", namespaces=ATOM_NS)
        video_id = entry.findtext("yt:videoId", default="", namespaces=ATOM_NS)
        url = ""
        link = entry.find("atom:link", ATOM_NS)
        if link is not None:
            url = link.attrib.get("href", "")
        if not url and video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"

        items.append(
            {
                "source": channel_config.get("name") or author_name or "YouTube",
                "source_type": "youtube",
                "title": entry.findtext("atom:title", default="", namespaces=ATOM_NS),
                "body": "",
                "url": url,
                "author": author_name,
                "published_at": entry.findtext("atom:published", default="", namespaces=ATOM_NS),
                "fetched_at": utc_now(),
                "tags": list(channel_config.get("tags", [])),
            }
        )

    return items
