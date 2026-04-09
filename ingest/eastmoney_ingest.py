"""Eastmoney public page ingestion with adapter-based parsers."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from config.settings import get_settings
from normalize.schema import utc_now


def fetch_eastmoney_items(
    sources_config: dict[str, Any],
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Fetch enabled Eastmoney public pages."""
    pages = [
        page
        for page in sources_config.get("eastmoney", {}).get("pages", [])
        if page.get("enabled", False)
    ]
    if not pages:
        return []

    timeout = get_settings().request_timeout_seconds
    own_client = client or httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (news-monitor/0.1)"},
    )
    items: list[dict[str, Any]] = []

    try:
        for page in pages:
            adapter = page.get("adapter", "eastmoney_article_list")
            if adapter == "eastmoney_np_list_api":
                items.extend(_fetch_np_list_api(page, own_client))
                continue

            response = own_client.get(page["url"])
            response.raise_for_status()
            items.extend(parse_eastmoney_page(response.text, page))
    finally:
        if client is None:
            own_client.close()

    return items


def parse_eastmoney_page(html: str, page_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Dispatch to an Eastmoney parser adapter."""
    adapter = page_config.get("adapter", "eastmoney_article_list")
    adapters = {
        "eastmoney_article_list": _parse_article_list,
    }
    if adapter not in adapters:
        raise ValueError(f"Unsupported Eastmoney adapter: {adapter}")
    return adapters[adapter](html, page_config)


def _parse_article_list(html: str, page_config: dict[str, Any]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    selectors = page_config.get("selectors", {})
    item_selector = selectors.get("item", "div.repeatList ul li")
    cards = soup.select(item_selector)
    base_url = page_config.get("base_url", page_config.get("url", ""))
    items: list[dict[str, Any]] = []

    for card in cards:
        if not isinstance(card, Tag):
            continue
        title_node = card.select_one(selectors.get("title", "a"))
        if title_node is None:
            continue
        title = title_node.get_text(" ", strip=True)
        href = title_node.get("href", "")
        if not title or not href:
            continue
        items.append(
            {
                "source": page_config["name"],
                "source_type": "eastmoney",
                "title": title,
                "body": _extract_text(card, selectors.get("summary", "p.info")),
                "url": urljoin(base_url, href),
                "author": "Eastmoney",
                "published_at": _extract_text(card, selectors.get("time", "p.time")),
                "fetched_at": utc_now(),
                "tags": list(page_config.get("tags", [])),
            }
        )

    return items


def _fetch_np_list_api(page_config: dict[str, Any], client: httpx.Client) -> list[dict[str, Any]]:
    """Fetch an Eastmoney list through its public JSON API."""
    api_config = page_config.get("api", {})
    kind = str(api_config.get("kind", "column")).lower()
    page_size = int(api_config.get("page_size", 20))
    order = int(api_config.get("order", 1))
    fields = str(
        api_config.get(
            "fields",
            "code,showTime,title,mediaName,summary,image,url,uniqueUrl,Np_dst",
        )
    )
    endpoint = (
        "https://np-listapi.eastmoney.com/comm/web/getNewsByScColumns"
        if kind == "sc_column"
        else "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
    )
    params = {
        "client": "web",
        "biz": "web_news_sccol" if kind == "sc_column" else "web_news_col",
        "order": order,
        "page_index": 1,
        "page_size": page_size,
        "req_trace": int(utc_now().timestamp()),
        "fields": fields,
        "types": str(api_config.get("types", "1,20")),
    }
    if kind == "sc_column":
        params["scColumns"] = str(api_config["column"])
    else:
        params["column"] = str(api_config["column"])
        params["needInteractData"] = int(api_config.get("need_interact_data", 0))

    response = client.get(endpoint, params=params)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data", {}).get("list", [])
    items: list[dict[str, Any]] = []

    for row in rows:
        code = str(row.get("code", ""))
        target_url = _resolve_eastmoney_url(row, code)
        if not target_url:
            continue
        tags = list(page_config.get("tags", []))
        if page_config.get("official"):
            tags.append("official")
        items.append(
            {
                "source": page_config["name"],
                "source_type": "eastmoney",
                "title": str(row.get("title", "")).strip(),
                "body": str(row.get("summary", "")).strip(),
                "url": target_url,
                "author": str(row.get("mediaName", "Eastmoney")).strip() or "Eastmoney",
                "published_at": str(row.get("showTime", "")).strip(),
                "fetched_at": utc_now(),
                "tags": list(dict.fromkeys(tags)),
            }
        )

    return items


def _resolve_eastmoney_url(row: dict[str, Any], code: str) -> str:
    """Resolve the most useful public URL from Eastmoney API fields."""
    unique_url = str(row.get("uniqueUrl", "")).strip()
    if unique_url:
        return unique_url

    url = str(row.get("url", "")).strip()
    if url:
        return url

    if str(row.get("Np_dst", "")).upper() == "CFH" and code:
        return f"http://caifuhao.eastmoney.com/news/{code}"
    if code:
        return f"https://finance.eastmoney.com/a/{code}.html"
    return ""


def _extract_text(card: Tag, selector: str) -> str:
    node = card.select_one(selector)
    return "" if node is None else node.get_text(" ", strip=True)
