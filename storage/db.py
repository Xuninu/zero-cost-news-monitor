"""SQLite persistence layer for the news monitoring pipeline."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from config.settings import get_settings
from dedup.dedup import DuplicateCandidate, normalize_url
from normalize.schema import NewsItem, parse_dt


class Database:
    """Small SQLite wrapper tailored to the v1 pipeline."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.db_path = Path(db_path or settings.news_db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a SQLite connection with Row objects enabled."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS news_items (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT,
                    url TEXT NOT NULL,
                    normalized_url TEXT NOT NULL UNIQUE,
                    author TEXT,
                    published_at TEXT,
                    fetched_at TEXT NOT NULL,
                    language TEXT,
                    tags TEXT NOT NULL,
                    symbols TEXT NOT NULL,
                    score REAL NOT NULL DEFAULT 0,
                    score_reasons TEXT NOT NULL,
                    is_urgent INTEGER NOT NULL DEFAULT 0,
                    fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sent_items (
                    item_id TEXT NOT NULL,
                    delivery_type TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    message_id TEXT,
                    PRIMARY KEY (item_id, delivery_type),
                    FOREIGN KEY (item_id) REFERENCES news_items(id)
                );

                CREATE TABLE IF NOT EXISTS run_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_name TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stats TEXT NOT NULL,
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_news_items_published_at
                ON news_items (published_at DESC);

                CREATE INDEX IF NOT EXISTS idx_news_items_score
                ON news_items (score DESC);

                CREATE INDEX IF NOT EXISTS idx_sent_items_sent_at
                ON sent_items (sent_at DESC);
                """
            )

    def find_item_id_by_url(self, url: str) -> str | None:
        """Return an existing item ID for a normalized URL."""
        normalized = normalize_url(url)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM news_items WHERE normalized_url = ? LIMIT 1",
                (normalized,),
            ).fetchone()
        return None if row is None else str(row["id"])

    def fetch_recent_title_candidates(self, hours: int = 72, limit: int = 300) -> list[DuplicateCandidate]:
        """Return recent items for similarity checks."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, url
                FROM news_items
                WHERE COALESCE(published_at, fetched_at) >= ?
                ORDER BY COALESCE(published_at, fetched_at) DESC
                LIMIT ?
                """,
                (cutoff.isoformat(), limit),
            ).fetchall()
        return [
            DuplicateCandidate(item_id=str(row["id"]), title=str(row["title"]), url=str(row["url"]))
            for row in rows
        ]

    def upsert_item(self, item: NewsItem) -> bool:
        """Insert or update a news item. Returns True if inserted or updated."""
        payload = self._serialize_item(item)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO news_items (
                    id, source, source_type, title, body, url, normalized_url, author,
                    published_at, fetched_at, language, tags, symbols, score,
                    score_reasons, is_urgent, fingerprint
                ) VALUES (
                    :id, :source, :source_type, :title, :body, :url, :normalized_url, :author,
                    :published_at, :fetched_at, :language, :tags, :symbols, :score,
                    :score_reasons, :is_urgent, :fingerprint
                )
                ON CONFLICT(id) DO UPDATE SET
                    source = excluded.source,
                    source_type = excluded.source_type,
                    title = excluded.title,
                    body = excluded.body,
                    url = excluded.url,
                    normalized_url = excluded.normalized_url,
                    author = excluded.author,
                    published_at = excluded.published_at,
                    fetched_at = excluded.fetched_at,
                    language = excluded.language,
                    tags = excluded.tags,
                    symbols = excluded.symbols,
                    score = excluded.score,
                    score_reasons = excluded.score_reasons,
                    is_urgent = excluded.is_urgent,
                    fingerprint = excluded.fingerprint
                """,
                payload,
            )
        return True

    def mark_sent(self, item_id: str, delivery_type: str, message_id: str | None = None) -> None:
        """Mark an item as already pushed to downstream delivery."""
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO sent_items (item_id, delivery_type, sent_at, message_id)
                VALUES (?, ?, ?, ?)
                """,
                (item_id, delivery_type, datetime.now(UTC).isoformat(), message_id),
            )

    def has_been_sent(self, item_id: str) -> bool:
        """Return whether an item has already been sent via any channel."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sent_items WHERE item_id = ? LIMIT 1",
                (item_id,),
            ).fetchone()
        return row is not None

    def fetch_pending_digest_items(self, limit: int, min_score: float = 0.0) -> list[NewsItem]:
        """Return scored items that have not been sent yet."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT n.*
                FROM news_items n
                LEFT JOIN sent_items s ON n.id = s.item_id
                WHERE s.item_id IS NULL
                  AND n.score >= ?
                ORDER BY n.is_urgent DESC, n.score DESC, COALESCE(n.published_at, n.fetched_at) DESC
                LIMIT ?
                """,
                (min_score, limit),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def fetch_recent_items(self, hours: int = 24, limit: int = 200) -> list[NewsItem]:
        """Return recent items for debugging or API inspection."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM news_items
                WHERE COALESCE(published_at, fetched_at) >= ?
                ORDER BY COALESCE(published_at, fetched_at) DESC
                LIMIT ?
                """,
                (cutoff.isoformat(), limit),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def log_run(
        self,
        job_name: str,
        started_at: datetime,
        ended_at: datetime,
        status: str,
        stats: dict[str, Any],
        error: str | None = None,
    ) -> None:
        """Persist a structured run log entry."""
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO run_logs (job_name, started_at, ended_at, status, stats, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job_name,
                    started_at.isoformat(),
                    ended_at.isoformat(),
                    status,
                    json.dumps(stats, ensure_ascii=False),
                    error,
                ),
            )

    def healthcheck(self) -> dict[str, Any]:
        """Return basic database health details."""
        with self.connect() as conn:
            item_count = conn.execute("SELECT COUNT(*) AS count FROM news_items").fetchone()["count"]
            run_count = conn.execute("SELECT COUNT(*) AS count FROM run_logs").fetchone()["count"]
        return {
            "database_path": str(self.db_path),
            "news_item_count": int(item_count),
            "run_log_count": int(run_count),
        }

    def _serialize_item(self, item: NewsItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "source": item.source,
            "source_type": item.source_type,
            "title": item.title,
            "body": item.body,
            "url": item.url,
            "normalized_url": normalize_url(item.url),
            "author": item.author,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "fetched_at": item.fetched_at.isoformat(),
            "language": item.language,
            "tags": json.dumps(item.tags, ensure_ascii=False),
            "symbols": json.dumps(item.symbols, ensure_ascii=False),
            "score": float(item.score),
            "score_reasons": json.dumps(item.score_reasons, ensure_ascii=False),
            "is_urgent": 1 if item.is_urgent else 0,
            "fingerprint": item.fingerprint,
        }

    def _row_to_item(self, row: sqlite3.Row) -> NewsItem:
        return NewsItem(
            id=str(row["id"]),
            source=str(row["source"]),
            source_type=str(row["source_type"]),
            title=str(row["title"]),
            body=str(row["body"] or ""),
            url=str(row["url"]),
            author=str(row["author"] or ""),
            published_at=parse_dt(row["published_at"]),
            fetched_at=parse_dt(row["fetched_at"]),
            language=str(row["language"] or "unknown"),
            tags=json.loads(str(row["tags"] or "[]")),
            symbols=json.loads(str(row["symbols"] or "[]")),
            score=float(row["score"] or 0.0),
            score_reasons=json.loads(str(row["score_reasons"] or "[]")),
            is_urgent=bool(row["is_urgent"]),
            fingerprint=str(row["fingerprint"]),
        )
