"""Digest rendering helpers for WeCom delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo
from typing import Iterable

from config.settings import get_settings, load_yaml_config
from normalize.schema import NewsItem, clean_text

SOURCE_NAME_ZH = {
    "OpenAI": "\u004f\u0070\u0065\u006e\u0041\u0049\u5b98\u65b9",
    "Anthropic": "\u0041\u006e\u0074\u0068\u0072\u006f\u0070\u0069\u0063\u5b98\u65b9",
    "Google DeepMind": "\u0047\u006f\u006f\u0067\u006c\u0065\u0020\u0044\u0065\u0065\u0070\u004d\u0069\u006e\u0064\u5b98\u65b9",
    "NVIDIA Developer": "\u82f1\u4f1f\u8fbe\u5f00\u53d1\u8005\u9891\u9053",
    "Bloomberg Technology": "\u5f6d\u535a\u79d1\u6280",
    "OpenAI News": "\u004f\u0070\u0065\u006e\u0041\u0049\u5b98\u65b9\u65b0\u95fb",
    "Google AI Blog": "\u8c37\u6b4c\u0020\u0041\u0049\u535a\u5ba2",
    "Microsoft AI Blog": "\u5fae\u8f6f\u0020\u0041\u0049\u535a\u5ba2",
    "TechCrunch AI": "\u0054\u0065\u0063\u0068\u0043\u0072\u0075\u006e\u0063\u0068\u0020\u0041\u0049",
    "Ars Technica Technology Lab": "\u0041\u0072\u0073\u6280\u672f\u680f\u76ee",
    "BBC World": "\u0042\u0042\u0043\u4e16\u754c",
    "BBC Business": "\u0042\u0042\u0043\u5546\u4e1a",
    "Al Jazeera Global": "\u534a\u5c9b\u7535\u89c6\u53f0",
    "EIA Energy": "\u7f8e\u56fd\u80fd\u6e90\u4fe1\u606f\u7f72",
    "Google News Middle East Oil Shipping": "\u8c37\u6b4c\u65b0\u95fb\u4e2d\u4e1c\u6cb9\u8fd0",
    "Google News Trump Markets": "\u8c37\u6b4c\u65b0\u95fb\u7279\u6717\u666e\u5e02\u573a",
    "Google News SpaceX IPO": "\u8c37\u6b4c\u65b0\u95fb\u0053\u0070\u0061\u0063\u0065\u0058\u0020\u0049\u0050\u004f",
    "Eastmoney Market Commentary": "\u4e1c\u65b9\u8d22\u5bcc\u5e02\u573a\u8bc4\u8bba",
    "Eastmoney Company News": "\u4e1c\u65b9\u8d22\u5bcc\u516c\u53f8\u65b0\u95fb",
}

TAG_NAME_ZH = {
    "international-ai": "\u56fd\u9645AI",
    "global-technology": "\u5168\u7403\u79d1\u6280",
    "a-shares": "A\u80a1",
    "china-markets": "\u4e2d\u56fd\u5e02\u573a",
    "official": "\u5b98\u65b9\u52a8\u6001",
    "frontier-models": "\u524d\u6cbf\u6a21\u578b",
    "model-release": "\u6a21\u578b\u53d1\u5e03",
    "semiconductors": "\u534a\u5bfc\u4f53",
    "ai-infrastructure": "AI\u7b97\u529b",
    "ai-chip": "AI\u82af\u7247",
    "ai-application": "AI\u5e94\u7528",
    "company-news": "\u516c\u53f8\u65b0\u95fb",
    "market-commentary": "\u5e02\u573a\u8bc4\u8bba",
    "earnings": "\u4e1a\u7ee9",
    "policy": "\u653f\u7b56",
    "regulation": "\u76d1\u7ba1",
    "markets": "\u5e02\u573a",
    "consumer-tech": "\u6d88\u8d39\u79d1\u6280",
    "geopolitics": "\u5730\u7f18\u653f\u6cbb",
    "global-markets": "\u5168\u7403\u5e02\u573a",
    "market-moving": "\u5e02\u573a\u50ac\u5316",
    "energy": "\u80fd\u6e90",
    "oil": "\u539f\u6cb9",
    "shipping": "\u822a\u8fd0",
    "commodities": "\u5927\u5b97\u5546\u54c1",
    "us-politics": "\u7f8e\u56fd\u653f\u6cbb",
    "macro": "\u5b8f\u89c2",
    "gold": "\u9ec4\u91d1",
    "safe-haven": "\u907f\u9669",
    "defense": "\u519b\u5de5",
    "space-economy": "\u592a\u7a7a\u7ecf\u6d4e",
    "ipo": "\u0049\u0050\u004f",
    "aerospace": "\u822a\u5929\u822a\u7a7a",
    "consumer-hotspot": "\u70ed\u70b9\u6d88\u8d39",
    "tourism-consumption": "\u6587\u65c5\u6d88\u8d39",
    "entertainment": "\u5a31\u4e50",
    "sports-hotspot": "\u8d5b\u4e8b\u70ed\u70b9",
}

IMPACT_TAG_PRIORITY = [
    "geopolitics",
    "oil",
    "shipping",
    "energy",
    "defense",
    "gold",
    "space-economy",
    "ipo",
    "macro",
    "global-markets",
    "market-moving",
    "ai-infrastructure",
    "ai-chip",
    "semiconductors",
    "international-ai",
    "global-technology",
    "a-shares",
    "china-markets",
    "ai-application",
    "consumer-hotspot",
    "tourism-consumption",
    "entertainment",
    "sports-hotspot",
]

GENERIC_IMPACT_TAGS = {
    "a-shares",
    "china-markets",
    "global-markets",
    "market-moving",
    "official",
    "company-news",
    "market-commentary",
    "earnings",
    "policy",
    "regulation",
    "markets",
}

TECH_AI_TAGS = {
    "international-ai",
    "global-technology",
    "frontier-models",
    "model-release",
    "semiconductors",
    "ai-infrastructure",
    "ai-chip",
    "ai-application",
    "consumer-tech",
    "space-economy",
    "aerospace",
}

MARKET_HOTSPOT_TAGS = {
    "geopolitics",
    "global-markets",
    "market-moving",
    "energy",
    "oil",
    "shipping",
    "commodities",
    "us-politics",
    "macro",
    "gold",
    "safe-haven",
    "defense",
    "consumer-hotspot",
    "tourism-consumption",
    "entertainment",
    "sports-hotspot",
}

A_SHARE_TAGS = {
    "a-shares",
    "china-markets",
}

EVENT_PATTERNS = (
    (
        "\u5730\u7f18\u51b2\u7a81\u4e0e\u6cb9\u8fd0\u6270\u52a8",
        (
            "middle east",
            "iran",
            "israel",
            "red sea",
            "hormuz",
            "crude",
            "oil",
            "tanker",
            "shipping",
            "\u4e2d\u4e1c",
            "\u4f0a\u6717",
            "\u4ee5\u8272\u5217",
            "\u7ea2\u6d77",
            "\u970d\u5c14\u6728\u5179",
            "\u539f\u6cb9",
            "\u6cb9\u8f6e",
            "\u822a\u8fd0",
            "\u6d77\u8fd0",
        ),
    ),
    (
        "\u7279\u6717\u666e\u4e0e\u5b8f\u89c2\u5e02\u573a\u50ac\u5316",
        (
            "trump",
            "tariff",
            "powell",
            "fed",
            "federal reserve",
            "white house",
            "\u7279\u6717\u666e",
            "\u5173\u7a0e",
            "\u9c8d\u5a01\u5c14",
            "\u7f8e\u8054\u50a8",
            "\u767d\u5bab",
        ),
    ),
    (
        "\u4e1a\u7ee9\u4e0e\u7ecf\u8425\u66f4\u65b0",
        (
            "earnings",
            "revenue",
            "guidance",
            "profit",
            "forecast",
            "\u4e1a\u7ee9",
            "\u8d22\u62a5",
            "\u5229\u6da6",
            "\u8425\u6536",
            "\u5feb\u62a5",
            "\u5e74\u62a5",
            "\u5b63\u62a5",
        ),
    ),
    (
        "\u76d1\u7ba1\u4e0e\u653f\u7b56\u53d8\u5316",
        (
            "regulation",
            "regulator",
            "approval",
            "antitrust",
            "sanction",
            "export control",
            "ban",
            "\u76d1\u7ba1",
            "\u653f\u7b56",
            "\u5ba1\u6279",
            "\u5236\u88c1",
            "\u7981\u4ee4",
            "\u5173\u7a0e",
        ),
    ),
    (
        "\u6a21\u578b\u4e0e\u4ea7\u54c1\u66f4\u65b0",
        (
            "gpt",
            "claude",
            "gemini",
            "llama",
            "deepseek",
            "model",
            "release",
            "launch",
            "agent",
            "reasoning",
            "\u6a21\u578b",
            "\u53d1\u5e03",
            "\u4e0a\u7ebf",
            "\u667a\u80fd\u4f53",
            "\u63a8\u7406",
        ),
    ),
    (
        "\u7b97\u529b\u4e0e\u57fa\u7840\u8bbe\u65bd\u8fdb\u5c55",
        (
            "gpu",
            "accelerator",
            "hbm",
            "blackwell",
            "cuda",
            "datacenter",
            "data center",
            "inference",
            "training cluster",
            "server",
            "cloud",
            "\u7b97\u529b",
            "\u6570\u636e\u4e2d\u5fc3",
            "\u670d\u52a1\u5668",
            "\u4e91",
        ),
    ),
    (
        "\u673a\u5668\u4eba\u4e0e\u667a\u80fd\u9a7e\u9a76\u8fdb\u5c55",
        (
            "robot",
            "robotics",
            "robotaxi",
            "autonomous",
            "\u81ea\u52a8\u9a7e\u9a76",
            "\u673a\u5668\u4eba",
        ),
    ),
    (
        "\u592a\u7a7a\u7ecf\u6d4e\u4e0e\u0049\u0050\u004f\u50ac\u5316",
        (
            "spacex",
            "starlink",
            "rocket",
            "satellite",
            "launch vehicle",
            "orbital",
            "\u592a\u7a7a",
            "\u822a\u5929",
            "\u536b\u661f",
            "\u53d1\u5c04",
        ),
    ),
    (
        "\u70ed\u70b9\u4e8b\u4ef6\u4e0e\u677f\u5757\u50ac\u5316",
        (
            "championship",
            "champion",
            "concert",
            "box office",
            "tourism surge",
            "sold out",
            "esports",
            "\u593a\u51a0",
            "\u51a0\u519b",
            "\u6f14\u5531\u4f1a",
            "\u7968\u623f",
            "\u6587\u65c5",
            "\u65c5\u6e38\u70ed",
            "\u8d5b\u4e8b",
            "\u70ed\u95e8\u0049\u0050",
        ),
    ),
    (
        "A\u80a1\u5e02\u573a\u52a8\u6001",
        (
            "a-share",
            "a shares",
            "\u6caa\u6df1",
            "\u4e0a\u4ea4\u6240",
            "\u6df1\u4ea4\u6240",
            "\u521b\u4e1a\u677f",
            "\u79d1\u521b\u677f",
            "\u9f99\u864e\u699c",
            "\u673a\u6784\u8c03\u7814",
            "\u6da8\u505c",
            "\u8dcc\u505c",
        ),
    ),
)

POSITIVE_TERMS = (
    "approval",
    "approved",
    "partnership",
    "expand",
    "expansion",
    "growth",
    "beat",
    "record",
    "surge",
    "rally",
    "launch",
    "release",
    "increase",
    "recovery",
    "order",
    "\u83b7\u6279",
    "\u5408\u4f5c",
    "\u6269\u4ea7",
    "\u589e\u957f",
    "\u63d0\u5347",
    "\u7a81\u7834",
    "\u56de\u8d2d",
    "\u4e2d\u6807",
    "\u6da8\u4ef7",
    "\u5927\u5355",
    "\u5feb\u62a5",
    "\u4fee\u590d",
)

NEGATIVE_TERMS = (
    "ban",
    "probe",
    "layoff",
    "delay",
    "warning",
    "drop",
    "decline",
    "cut",
    "sanction",
    "lawsuit",
    "recall",
    "fraud",
    "attack",
    "tariff",
    "threat",
    "weak",
    "\u7981\u4ee4",
    "\u88c1\u5458",
    "\u5ef6\u8fdf",
    "\u4e0b\u6ed1",
    "\u9884\u4e8f",
    "\u4e8f\u635f",
    "\u5236\u88c1",
    "\u5173\u7a0e",
    "\u5a01\u80c1",
    "\u88ab\u8c03\u67e5",
    "\u5904\u7f5a",
    "\u9047\u88ad",
)

NEUTRAL_TERMS = (
    "no impact",
    "neutral",
    "unchanged",
    "\u6682\u65e0\u5f71\u54cd",
    "\u5f71\u54cd\u6709\u9650",
    "\u4e2d\u6027",
    "\u6301\u5e73",
)


@lru_cache(maxsize=1)
def _ticker_entries() -> list[dict[str, object]]:
    config = load_yaml_config("tickers.yaml")
    return list(config.get("tickers", []))


@dataclass(slots=True)
class DigestEntry:
    """Rendered entry ready for downstream formatting."""

    item_id: str
    title: str
    source: str
    time: str
    priority_label: str
    impact_label: str
    impact_scope: str
    impact_assessment: str
    trigger_text: str
    impacted_assets: str
    candidate_symbols: str
    summary_zh: str
    score: float
    link: str


def select_digest_items(items: Iterable[NewsItem], limit: int) -> list[NewsItem]:
    """Select digest items with balanced coverage across key market themes."""
    ranked_items = sorted(items, key=_digest_item_sort_key, reverse=True)
    if limit <= 0 or not ranked_items:
        return []

    selected: list[NewsItem] = []
    selected_ids: set[str] = set()

    bucket_plan = (
        ("tech_ai", _bucket_target_count("tech_ai", ranked_items, limit)),
        ("market_hotspot", _bucket_target_count("market_hotspot", ranked_items, limit)),
        ("a_shares", _bucket_target_count("a_shares", ranked_items, limit)),
    )

    for bucket_name, target_count in bucket_plan:
        for item in ranked_items:
            if len(selected) >= limit or target_count <= 0:
                break
            if item.id in selected_ids or not _item_matches_bucket(item, bucket_name):
                continue
            selected.append(item)
            selected_ids.add(item.id)
            target_count -= 1

    for item in ranked_items:
        if len(selected) >= limit:
            break
        if item.id in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(item.id)

    return sorted(selected, key=_digest_item_sort_key, reverse=True)


def build_digest_entries(items: Iterable[NewsItem]) -> list[DigestEntry]:
    """Convert scored items into digest entries."""
    settings = get_settings()
    display_tz = ZoneInfo(settings.pipeline_schedule_timezone)
    entries: list[DigestEntry] = []
    for item in items:
        reference = (item.published_at or item.fetched_at).astimezone(display_tz)
        impact_targets = _impact_targets_zh(item)
        entries.append(
            DigestEntry(
                item_id=item.id,
                title=_title_zh(item),
                source=_source_name_zh(item.source),
                time=reference.strftime("%m-%d %H:%M"),
                priority_label=_priority_label(item.score),
                impact_label=_impact_label_zh(item),
                impact_scope="\u884c\u4e1a" if impact_targets else "\u4e3b\u9898",
                impact_assessment=_impact_assessment_zh(item, impact_targets),
                trigger_text=_trigger_text_zh(item),
                impacted_assets="\u3001".join(impact_targets) if impact_targets else "\u76f8\u5173\u4e3b\u9898",
                candidate_symbols=_candidate_symbols_text(item),
                summary_zh=_summary_zh(item),
                score=item.score,
                link=item.url,
            )
        )
    return entries


def build_urgent_message(item: NewsItem, use_markdown: bool = True) -> str:
    """Render a single urgent alert message."""
    entry = build_digest_entries([item])[0]
    lines = [
        f"\u91cd\u8981\u65b0\u95fb\u63d0\u9192 {entry.time}",
        "------------------------------",
        f"[{entry.priority_label}\u00b7{entry.impact_label}\u00b7{entry.impact_scope}]",
        entry.title,
        f"\u5019\u9009\u6807\u7684\uff1a{entry.candidate_symbols}",
        f"\u5f71\u54cd\u5224\u65ad\uff1a{entry.impact_assessment}",
        f"\u89e6\u53d1\u56e0\u7d20\uff1a{entry.trigger_text}",
        f"\u7efc\u5408\u5206\uff1a{entry.score:.0f}",
        f"\u6765\u6e90\uff1a{entry.source}",
        f"\u539f\u6587\uff1a{entry.link}",
    ]
    return "\n".join(lines)


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
    header = _digest_header(entries)
    current = header

    for index, entry in enumerate(entries, start=1):
        block = _render_entry(entry, index)
        candidate = f"{current}\n\n{block}".strip()
        if len(candidate) > max_chars and current != header:
            chunks.append(current)
            current = f"{header}\n\n{block}"
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


def _digest_header(entries: list[DigestEntry]) -> str:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.pipeline_schedule_timezone))
    theme = _digest_theme(entries)
    return (
        f"\u5e02\u573a\u63d0\u9192 {now.strftime('%m-%d %H:%M')}\n"
        f"{theme} {len(entries)} \u6761\n"
        "------------------------------"
    )


def _render_entry(entry: DigestEntry, index: int) -> str:
    return (
        f"{index}. [{entry.priority_label}\u00b7{entry.impact_label}\u00b7{entry.impact_scope}]\n"
        f"{entry.title}\n"
        f"\u5019\u9009\u6807\u7684\uff1a{entry.candidate_symbols}\n"
        f"\u5f71\u54cd\u5224\u65ad\uff1a{entry.impact_assessment}\n"
        f"\u89e6\u53d1\u56e0\u7d20\uff1a{entry.trigger_text}\n"
        f"\u7efc\u5408\u5206\uff1a{entry.score:.0f}\n"
        f"\u6765\u6e90\uff1a{entry.source}\n"
        f"\u539f\u6587\uff1a{entry.link}"
    )


def _priority_label(score: float) -> str:
    if score >= 84:
        return "\u9ad8\u4f18\u5148"
    if score >= 65:
        return "\u91cd\u70b9"
    return "\u8ddf\u8e2a"


def _impact_label_zh(item: NewsItem) -> str:
    text_blob = f"{item.title}\n{item.body}".lower()
    positive_hits = sum(1 for term in POSITIVE_TERMS if term in text_blob)
    negative_hits = sum(1 for term in NEGATIVE_TERMS if term in text_blob)
    neutral_hits = sum(1 for term in NEUTRAL_TERMS if term in text_blob)

    if neutral_hits and positive_hits == negative_hits:
        return "\u4e2d\u6027"
    if positive_hits > negative_hits:
        return "\u5229\u597d"
    if negative_hits > positive_hits:
        return "\u5229\u7a7a"
    return "\u4e2d\u6027"


def _impact_assessment_zh(item: NewsItem, impact_targets: list[str]) -> str:
    target_text = "\u3001".join(impact_targets) if impact_targets else "\u76f8\u5173\u4e3b\u9898"
    impact_label = _impact_label_zh(item)
    if impact_label == "\u5229\u597d":
        return f"\u5bf9{target_text}\u76f8\u5173\u80a1\u7968\u504f\u5229\u597d"
    if impact_label == "\u5229\u7a7a":
        return f"\u5bf9{target_text}\u76f8\u5173\u80a1\u7968\u504f\u5229\u7a7a"
    return f"\u5bf9{target_text}\u76f8\u5173\u80a1\u7968\u5f71\u54cd\u504f\u4e2d\u6027"


def _trigger_text_zh(item: NewsItem) -> str:
    labels: list[str] = []
    event_text = _event_label_zh(item)
    if event_text:
        labels.append(event_text)
    for label in _topic_labels_zh(item, limit=3):
        if label not in labels:
            labels.append(label)
    return "\u3001".join(labels[:3]) if labels else "\u5f85\u8865\u5145"


def _summary_zh(item: NewsItem) -> str:
    return f"{_source_name_zh(item.source)}{_trigger_text_zh(item)}"


def _title_zh(item: NewsItem) -> str:
    title = clean_text(item.title)
    if _contains_cjk(title):
        return title[:58] + "..." if len(title) > 58 else title

    event_text = _event_label_zh(item)
    impact_targets = _impact_targets_zh(item)
    if impact_targets and event_text:
        return f"{impact_targets[0]}{event_text}"
    if event_text:
        return event_text
    if impact_targets:
        return f"{impact_targets[0]}\u91cd\u8981\u52a8\u6001"
    return "\u91cd\u8981\u65b0\u95fb\u52a8\u6001"


def _source_name_zh(source: str) -> str:
    normalized = clean_text(source)
    return SOURCE_NAME_ZH.get(normalized, normalized or "\u8d44\u8baf\u6765\u6e90")


def _topic_labels_zh(item: NewsItem, limit: int = 3) -> list[str]:
    labels: list[str] = []
    for tag in item.tags:
        tag_name = TAG_NAME_ZH.get(clean_text(tag))
        if tag_name and tag_name not in labels:
            labels.append(tag_name)
        if len(labels) >= limit:
            break
    return labels


def _impact_targets_zh(item: NewsItem) -> list[str]:
    labels: list[str] = []
    tag_set = {clean_text(tag).lower() for tag in item.tags}
    for tag in IMPACT_TAG_PRIORITY:
        if tag in tag_set:
            label = TAG_NAME_ZH.get(tag)
            if label and label not in labels:
                labels.append(label)
    for ticker in _ticker_entries():
        ticker_tags = {clean_text(str(tag)).lower() for tag in ticker.get("tags", [])}
        if not ticker_tags.intersection(tag_set):
            continue
        for tag in ticker_tags:
            label = TAG_NAME_ZH.get(tag)
            if label and label not in labels:
                labels.append(label)
    return labels[:3]


def _candidate_symbols_text(item: NewsItem, limit: int = 4) -> str:
    symbols: list[str] = []
    tag_set = {clean_text(tag).lower() for tag in item.tags}
    specific_tags = {tag for tag in tag_set if tag not in GENERIC_IMPACT_TAGS}
    ticker_by_symbol = {
        clean_text(str(ticker.get("symbol", ""))): ticker
        for ticker in _ticker_entries()
        if clean_text(str(ticker.get("symbol", "")))
    }

    for symbol in item.symbols:
        cleaned = clean_text(symbol)
        if cleaned and cleaned not in symbols:
            ticker_meta = ticker_by_symbol.get(cleaned)
            if ticker_meta:
                ticker_tags = {clean_text(str(tag)).lower() for tag in ticker_meta.get("tags", [])}
                if specific_tags and not ticker_tags.intersection(specific_tags):
                    continue
                if ticker_tags and not ticker_tags.intersection(tag_set):
                    continue
            symbols.append(cleaned)

    ranked_tickers: list[tuple[int, int, str]] = []
    for ticker in _ticker_entries():
        symbol = clean_text(str(ticker.get("symbol", "")))
        if not symbol or symbol in symbols:
            continue
        ticker_tags = {clean_text(str(tag)).lower() for tag in ticker.get("tags", [])}
        relevant_tags = ticker_tags.intersection(specific_tags or tag_set)
        if not relevant_tags:
            continue
        overlap_score = 0
        for tag in relevant_tags:
            try:
                overlap_score += len(IMPACT_TAG_PRIORITY) - IMPACT_TAG_PRIORITY.index(tag)
            except ValueError:
                overlap_score += 1
        ranked_tickers.append((-overlap_score, len(symbols), symbol))

    for _, _, symbol in sorted(ranked_tickers):
        if symbol not in symbols:
            symbols.append(symbol)
        if len(symbols) >= limit:
            break

    return " \u00b7 ".join(symbols[:limit]) if symbols else "\u5f85\u8865\u5145"


def _event_label_zh(item: NewsItem) -> str:
    text_blob = f"{item.title}\n{item.body}".lower()
    for label, terms in EVENT_PATTERNS:
        if any(term in text_blob for term in terms):
            return label
    return ""


def _digest_theme(entries: list[DigestEntry]) -> str:
    merged = " ".join(entry.impacted_assets for entry in entries)
    has_a_shares = "A\u80a1" in merged or "\u4e2d\u56fd\u5e02\u573a" in merged
    has_tech = any(token in merged for token in ("\u56fd\u9645AI", "\u5168\u7403\u79d1\u6280", "\u534a\u5bfc\u4f53", "AI\u7b97\u529b"))
    has_macro = any(
        token in merged
        for token in (
            "\u5730\u7f18\u653f\u6cbb",
            "\u539f\u6cb9",
            "\u822a\u8fd0",
            "\u80fd\u6e90",
            "\u9ec4\u91d1",
            "\u7f8e\u56fd\u653f\u6cbb",
            "\u5b8f\u89c2",
            "\u5168\u7403\u5e02\u573a",
            "\u519b\u5de5",
        )
    )
    has_space = any(token in merged for token in ("\u592a\u7a7a\u7ecf\u6d4e", "\u822a\u5929\u822a\u7a7a", "IPO"))
    has_consumer = any(token in merged for token in ("\u70ed\u70b9\u6d88\u8d39", "\u6587\u65c5\u6d88\u8d39", "\u5a31\u4e50", "\u8d5b\u4e8b\u70ed\u70b9"))
    if has_macro and has_tech and has_a_shares:
        return "\u5b8f\u89c2 / \u79d1\u6280 / A\u80a1"
    if has_macro and has_tech:
        return "\u5b8f\u89c2 / \u79d1\u6280"
    if has_macro and has_a_shares:
        return "\u5b8f\u89c2 / A\u80a1"
    if has_space and has_tech:
        return "\u592a\u7a7a / \u79d1\u6280"
    if has_consumer and has_a_shares:
        return "\u6d88\u8d39 / A\u80a1"
    if has_a_shares and has_tech:
        return "\u79d1\u6280 / A\u80a1"
    if has_macro:
        return "\u5b8f\u89c2"
    if has_space:
        return "\u592a\u7a7a"
    if has_consumer:
        return "\u6d88\u8d39"
    if has_a_shares:
        return "A\u80a1"
    if has_tech:
        return "\u79d1\u6280"
    return "\u5e02\u573a"


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _bucket_target_count(bucket_name: str, items: list[NewsItem], limit: int) -> int:
    available = sum(1 for item in items if _item_matches_bucket(item, bucket_name))
    if available <= 0:
        return 0

    if bucket_name == "tech_ai":
        target = 3 if limit >= 9 else 2 if limit >= 4 else 1
    elif bucket_name == "market_hotspot":
        target = 3 if limit >= 10 else 2 if limit >= 5 else 1
    elif bucket_name == "a_shares":
        target = 1 if limit >= 8 else 0
    else:
        target = 0
    return min(target, available, limit)


def _item_matches_bucket(item: NewsItem, bucket_name: str) -> bool:
    tag_set = {clean_text(tag).lower() for tag in item.tags}
    if bucket_name == "tech_ai":
        return bool(tag_set.intersection(TECH_AI_TAGS))
    if bucket_name == "market_hotspot":
        return bool(tag_set.intersection(MARKET_HOTSPOT_TAGS))
    if bucket_name == "a_shares":
        return bool(tag_set.intersection(A_SHARE_TAGS))
    return False


def _digest_item_sort_key(item: NewsItem) -> tuple[int, float, datetime]:
    reference = item.published_at or item.fetched_at
    return (1 if item.is_urgent else 0, item.score, reference)
