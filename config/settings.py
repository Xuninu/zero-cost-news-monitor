"""Application settings and configuration loading."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
ENV_PATH = ROOT_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def ensure_runtime_dirs() -> None:
    """Create runtime folders when they do not exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class Settings:
    """Runtime settings sourced from environment variables."""

    news_db_path: Path
    log_level: str
    request_timeout_seconds: int
    wecom_webhook_url: str
    wecom_message_format: str
    urgent_threshold: float
    digest_min_score: float
    title_similarity_threshold: float
    pipeline_schedule_timezone: str
    max_digest_items: int
    youtube_verify_token: str
    youtube_webhook_secret: str
    youtube_webhook_callback_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables with sensible defaults."""
        ensure_runtime_dirs()
        return cls(
            news_db_path=Path(os.getenv("NEWS_DB_PATH", str(DATA_DIR / "news_monitor.db"))),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
            wecom_webhook_url=os.getenv("WECOM_WEBHOOK_URL", ""),
            wecom_message_format=os.getenv("WECOM_MESSAGE_FORMAT", "text").lower(),
            urgent_threshold=float(os.getenv("URGENT_THRESHOLD", "80")),
            digest_min_score=float(os.getenv("DIGEST_MIN_SCORE", "36")),
            title_similarity_threshold=float(os.getenv("TITLE_SIMILARITY_THRESHOLD", "0.92")),
            pipeline_schedule_timezone=os.getenv("PIPELINE_SCHEDULE_TIMEZONE", "Asia/Shanghai"),
            max_digest_items=int(os.getenv("MAX_DIGEST_ITEMS", "25")),
            youtube_verify_token=os.getenv("YOUTUBE_VERIFY_TOKEN", ""),
            youtube_webhook_secret=os.getenv("YOUTUBE_WEBHOOK_SECRET", ""),
            youtube_webhook_callback_url=os.getenv("YOUTUBE_WEBHOOK_CALLBACK_URL", ""),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings object."""
    return Settings.from_env()


def load_yaml_config(file_name: str) -> dict[str, Any]:
    """Load a YAML file from the config directory."""
    file_path = CONFIG_DIR / file_name
    with file_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def setup_logging(logger_name: str) -> logging.Logger:
    """Configure application logging to console and logs/."""
    ensure_runtime_dirs()
    settings = get_settings()
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_DIR / f"{logger_name.replace('.', '_')}.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger
