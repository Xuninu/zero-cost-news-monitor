"""Digest rendering helpers for WeCom delivery."""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo
from typing import Iterable

from config.settings import get_settings
from normalize.schema import NewsItem, clean_text

SOURCE_NAME_ZH = {
    "OpenAI": "OpenAI 官方",
    "Anthropic": "Anthropic 官方",
    "Google DeepMind": "Google DeepMind 官方",
    "NVIDIA Developer": "英伟达开发者频道",
    "Bloomberg Technology": "彭博科技",
    "OpenAI News": "OpenAI 官方新闻",
    "Google AI Blog": "谷歌 AI 博客",
    "Microsoft AI Blog": "微软 AI 博客",
    "TechCrunch AI": "TechCrunch AI",
    "Ars Technica Technology Lab": "Ars 技术栏目",
    "Eastmoney Market Commentary": "东方财富市场评论",
    "Eastmoney Company News": "东方财富公司新闻",
}

TAG_NAME_ZH = {
    "international-ai": "国际AI",
    "global-technology": "全球科技",
    "a-shares": "A股",
    "china-markets": "中国市场",
    "official": "官方动态",
    "frontier-models": "前沿模型",
    "model-release": "模型发布",
    "semiconductors": "半导体",
    "ai-infrastructure": "AI算力",
    "company-news": "公司新闻",
    "market-commentary": "市场评论",
    "earnings": "业绩",
    "policy": "政策",
    "regulation": "监管",
    "markets": "市场",
    "consumer-tech": "消费科技",
}

EVENT_PATTERNS = (
    (
        "业绩与经营更新",
        ("earnings", "revenue", "guidance", "profit", "forecast", "业绩", "财报", "利润", "营收", "快报", "年报", "季报"),
    ),
    (
        "监管与政策变化",
        ("regulation", "regulator", "approval", "antitrust", "sanction", "export control", "ban", "监管", "政策", "审批", "制裁", "禁令"),
    ),
    (
        "模型与产品更新",
        ("gpt", "claude", "gemini", "llama", "deepseek", "model", "release", "launch", "agent", "reasoning", "模型", "发布", "上线", "智能体", "推理"),
    ),
    (
        "算力与基础设施进展",
        ("gpu", "accelerator", "hbm", "blackwell", "cuda", "datacenter", "data center", "inference", "training cluster", "server", "cloud", "算力", "数据中心", "服务器", "云"),
    ),
    (
        "机器人与智能驾驶进展",
        ("robot", "robotics", "robotaxi", "autonomous", "自动驾驶", "机器人"),
    ),
    (
        "A股市场动态",
        ("a-share", "a shares", "沪深", "上交所", "深交所", "创业板", "科创板", "龙虎榜", "机构调研", "涨停", "跌停"),
    ),
)


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
    settings = get_settings()
    display_tz = ZoneInfo(settings.pipeline_schedule_timezone)
    entries: list[DigestEntry] = []
    for item in items:
        reference = (item.published_at or item.fetched_at).astimezone(display_tz)
        source_name = _source_name_zh(item.source)
        assets = _asset_phrase_zh(item)
        entries.append(
            DigestEntry(
                item_id=item.id,
                title=_title_zh(item),
                source=source_name,
                time=reference.strftime("%Y-%m-%d %H:%M"),
                summary_zh=_summary_zh(item),
                summary_en="",
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
            "## 重要新闻提醒\n\n"
            f"标题：{entry.title}\n\n"
            f"来源：{entry.source}\n"
            f"时间：{entry.time} 北京时间\n"
            f"摘要：{entry.summary_zh}\n"
            f"相关：{entry.impacted_assets}\n"
            f"评分：{entry.score:.0f}\n"
            f"原文：{entry.link}"
        )
    return (
        "重要新闻提醒\n\n"
        f"标题：{entry.title}\n"
        f"来源：{entry.source}\n"
        f"时间：{entry.time} 北京时间\n"
        f"摘要：{entry.summary_zh}\n"
        f"相关：{entry.impacted_assets}\n"
        f"评分：{entry.score:.0f}\n"
        f"原文：{entry.link}"
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
            f"### {index}. {entry.title}\n\n"
            f"来源：{entry.source}\n"
            f"时间：{entry.time} 北京时间\n"
            f"摘要：{entry.summary_zh}\n"
            f"相关：{entry.impacted_assets}\n"
            f"评分：{entry.score:.0f}\n"
            f"原文：{entry.link}"
        )
    return (
        f"{index}. {entry.title}\n"
        f"来源：{entry.source}\n"
        f"时间：{entry.time} 北京时间\n"
        f"摘要：{entry.summary_zh}\n"
        f"相关：{entry.impacted_assets}\n"
        f"评分：{entry.score:.0f}\n"
        f"原文：{entry.link}"
    )


def _summary_zh(item: NewsItem) -> str:
    source_name = _source_name_zh(item.source)
    topic_text = _topic_text_zh(item)
    event_text = _event_label_zh(item)
    assets = _asset_phrase_zh(item)
    if topic_text and event_text:
        return f"{source_name}发布了与{topic_text}相关的新闻，重点偏向{event_text}，建议优先关注{assets}。"
    if event_text:
        return f"{source_name}发布了重要动态，当前信号偏向{event_text}，建议优先关注{assets}。"
    if topic_text:
        return f"{source_name}发布了与{topic_text}相关的新闻，建议优先关注{assets}。"
    return f"{source_name}发布了重要新闻，建议优先关注{assets}。"


def _title_zh(item: NewsItem) -> str:
    title = clean_text(item.title)
    if _contains_cjk(title):
        return title[:52] + "..." if len(title) > 52 else title

    topic_labels = _topic_labels_zh(item, limit=2)
    event_text = _event_label_zh(item)
    if topic_labels and event_text:
        return f"{topic_labels[0]}{event_text}"
    if event_text:
        return event_text
    if topic_labels:
        return f"{topic_labels[0]}重要动态"
    return "重要新闻动态"


def _source_name_zh(source: str) -> str:
    return SOURCE_NAME_ZH.get(clean_text(source), clean_text(source) or "资讯来源")


def _topic_labels_zh(item: NewsItem, limit: int = 3) -> list[str]:
    labels: list[str] = []
    for tag in item.tags:
        tag_name = TAG_NAME_ZH.get(clean_text(tag))
        if tag_name and tag_name not in labels:
            labels.append(tag_name)
        if len(labels) >= limit:
            break
    return labels


def _topic_text_zh(item: NewsItem) -> str:
    labels = _topic_labels_zh(item, limit=2)
    return "、".join(labels)


def _event_label_zh(item: NewsItem) -> str:
    text_blob = f"{item.title}\n{item.body}".lower()
    for label, terms in EVENT_PATTERNS:
        if any(term.lower() in text_blob for term in terms):
            return label
    return ""


def _asset_phrase_zh(item: NewsItem) -> str:
    assets: list[str] = []
    for symbol in item.symbols[:3]:
        if symbol not in assets:
            assets.append(symbol)
    for label in _topic_labels_zh(item, limit=3):
        if label not in assets:
            assets.append(label)
    return "、".join(assets[:4]) if assets else "相关主题资产"


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)
