"""Generic public site ingestion using configurable HTML selectors."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from config.settings import get_settings
from normalize.schema import utc_now


def fetch_site_items(
    sources_config: dict[str, Any],
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Fetch enabled public HTML pages using selector-based adapters."""
    pages = [
        page
        for page in sources_config.get("sites", {}).get("pages", [])
        if page.get("enabled", False)
    ]
    if not pages:
        return []

    timeout = get_settings().request_timeout_seconds
    own_client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    items: list[dict[str, Any]] = []

    try:
        for page in pages:
            response = own_client.get(page["url"])
            response.raise_for_status()
            items.extend(parse_site_page(response.text, page))
    finally:
        if client is None:
            own_client.close()

    return items


def parse_site_page(html: str, page_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse one site page based on configured selectors."""
    adapter = page_config.get("adapter", "generic_article_cards")
    if adapter != "generic_article_cards":
        raise ValueError(f"Unsupported site adapter: {adapter}")
    return _parse_card_list(html, page_config, source_type="site")


def _parse_card_list(html: str, page_config: dict[str, Any], source_type: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    selectors = page_config.get("selectors", {})
    item_selector = selectors.get("item", "article")
    base_url = page_config.get("base_url", page_config.get("url", ""))
    cards = soup.select(item_selector)
    items: list[dict[str, Any]] = []

    for card in cards:
        if not isinstance(card, Tag):
            continue
        title = _extract_text(card, selectors.get("title"))
        url = _extract_url(card, selectors.get("url"), base_url)
        if not title or not url:
            continue
        items.append(
            {
                "source": page_config["name"],
                "source_type": source_type,
                "title": title,
                "body": _extract_text(card, selectors.get("summary")),
                "url": url,
                "author": page_config["name"],
                "published_at": _extract_text(card, selectors.get("time")),
                "fetched_at": utc_now(),
                "tags": list(page_config.get("tags", []))
                + (["official"] if page_config.get("official") else []),
            }
        )

    return items


def _extract_text(card: Tag, selector: str | None) -> str:
    if not selector:
        return ""
    node = card.select_one(selector)
    return "" if node is None else node.get_text(" ", strip=True)


def _extract_url(card: Tag, selector: str | None, base_url: str) -> str:
    if not selector:
        return ""
    node = card.select_one(selector)
    if node is None:
        return ""
    href = node.get("href", "")
    return urljoin(base_url, href)
