"""Rule-based scorer for normalized news items."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

from config.settings import get_settings, load_yaml_config
from normalize.schema import NewsItem, utc_now


@dataclass(slots=True)
class ScoreResult:
    """Output returned by the rule-based scorer."""

    total_score: float
    reasons: list[str]
    is_urgent: bool
    matched_tags: list[str] = field(default_factory=list)
    matched_symbols: list[str] = field(default_factory=list)


class RuleBasedScorer:
    """Score items using static YAML-configured business rules."""

    def __init__(
        self,
        keyword_config: dict[str, Any] | None = None,
        ticker_config: dict[str, Any] | None = None,
    ) -> None:
        self.settings = get_settings()
        self.keyword_config = keyword_config or load_yaml_config("keywords.yaml")
        self.ticker_config = ticker_config or load_yaml_config("tickers.yaml")
        self.scoring_config = self.keyword_config.get("scoring", {})

    def score_item(self, item: NewsItem, duplicate_count: int = 0) -> ScoreResult:
        """Return the total score, reasons, urgency flag, and derived tags/symbols."""
        score = 0.0
        reasons: list[str] = []
        matched_tags: list[str] = list(item.tags)
        matched_symbols: list[str] = list(item.symbols)
        urgent_hit = False
        text_blob = f"{item.title}\n{item.body}".lower()

        default_source_weight = float(self.scoring_config.get("default_source_weight", 3))
        source_weights = self.scoring_config.get("source_weights", {})
        source_weight = float(source_weights.get(item.source_type, default_source_weight))
        score += source_weight
        reasons.append(f"source_type:{item.source_type}+{source_weight:g}")

        source_name_weights = self.scoring_config.get("source_name_weights", {})
        if item.source in source_name_weights:
            boost = float(source_name_weights[item.source])
            score += boost
            reasons.append(f"source:{item.source}+{boost:g}")

        for group in self.scoring_config.get("keyword_groups", []):
            matched_terms = [term for term in group.get("terms", []) if term.lower() in text_blob]
            if not matched_terms:
                continue
            boost = float(group.get("weight", 0))
            score += boost
            reasons.append(f"keyword:{group.get('label', 'group')}+{boost:g}")
            matched_tags.extend(group.get("tags", []))

        for urgency_group in self.scoring_config.get("urgency_keywords", []):
            matched_terms = [term for term in urgency_group.get("terms", []) if term.lower() in text_blob]
            if not matched_terms:
                continue
            boost = float(urgency_group.get("boost", 0))
            score += boost
            urgent_hit = True
            reasons.append(f"urgency:{urgency_group.get('label', 'group')}+{boost:g}")

        for ticker in self.ticker_config.get("tickers", []):
            aliases = [str(alias).lower() for alias in ticker.get("aliases", [])]
            if not aliases or not any(alias in text_blob for alias in aliases):
                continue
            symbol = str(ticker.get("symbol"))
            boost = float(ticker.get("weight", 0))
            score += boost
            reasons.append(f"ticker:{symbol}+{boost:g}")
            matched_symbols.append(symbol)
            matched_tags.extend(ticker.get("tags", []))

        if "official" in {tag.lower() for tag in item.tags}:
            official_boost = float(self.scoring_config.get("official_source_boost", 0))
            score += official_boost
            reasons.append(f"official_source+{official_boost:g}")

        recency_boost = self._recency_boost(item)
        if recency_boost:
            score += recency_boost
            reasons.append(f"recency+{recency_boost:g}")

        if duplicate_count > 0:
            penalty_per_match = float(self.scoring_config.get("duplicate_penalty_per_match", 0))
            max_penalty = float(self.scoring_config.get("max_duplicate_penalty", 0))
            penalty = min(max_penalty, duplicate_count * penalty_per_match)
            score -= penalty
            reasons.append(f"duplicate_penalty-{penalty:g}")

        score = round(max(score, 0.0), 2)
        urgent_threshold = float(
            self.scoring_config.get("urgent_threshold", self.settings.urgent_threshold)
        )
        is_urgent = score >= urgent_threshold or (urgent_hit and score >= urgent_threshold - 10)

        return ScoreResult(
            total_score=score,
            reasons=reasons,
            is_urgent=is_urgent,
            matched_tags=list(dict.fromkeys(matched_tags)),
            matched_symbols=list(dict.fromkeys(matched_symbols)),
        )

    def _recency_boost(self, item: NewsItem) -> float:
        """Boost recently published items more heavily."""
        reference = item.published_at or item.fetched_at
        reference_utc = reference.astimezone(UTC)
        age_hours = (utc_now() - reference_utc).total_seconds() / 3600
        for rule in self.scoring_config.get("recency_boosts", []):
            if age_hours <= float(rule.get("max_hours", 0)):
                return float(rule.get("boost", 0))
        return 0.0
