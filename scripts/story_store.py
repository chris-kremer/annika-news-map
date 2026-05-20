#!/usr/bin/env python3

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "story_store.sqlite"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS story_sets (
            key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            generated_at TEXT,
            refreshed_at TEXT NOT NULL,
            stale_after TEXT,
            provider TEXT,
            status TEXT NOT NULL DEFAULT 'ready',
            warning TEXT
        );

        CREATE TABLE IF NOT EXISTS country_briefings (
            country TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            generated_at TEXT,
            refreshed_at TEXT NOT NULL,
            stale_after TEXT,
            provider TEXT,
            status TEXT NOT NULL DEFAULT 'ready',
            warning TEXT
        );

        CREATE TABLE IF NOT EXISTS country_histories (
            country TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            generated_at TEXT,
            refreshed_at TEXT NOT NULL,
            stale_after TEXT,
            provider TEXT,
            status TEXT NOT NULL DEFAULT 'ready',
            warning TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_story_sets_stale_after
            ON story_sets(stale_after);
        CREATE INDEX IF NOT EXISTS idx_country_briefings_stale_after
            ON country_briefings(stale_after);
        CREATE INDEX IF NOT EXISTS idx_country_histories_stale_after
            ON country_histories(stale_after);
        """
    )
    connection.commit()


def write_story_set(
    key: str,
    payload: dict[str, Any],
    *,
    stale_after: str | None,
    status: str = "ready",
    warning: str | None = None,
) -> None:
    generated_at = payload.get("generatedAt")
    provider = payload.get("provider")
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO story_sets
                (key, payload_json, generated_at, refreshed_at, stale_after, provider, status, warning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                payload_json = excluded.payload_json,
                generated_at = excluded.generated_at,
                refreshed_at = excluded.refreshed_at,
                stale_after = excluded.stale_after,
                provider = excluded.provider,
                status = excluded.status,
                warning = excluded.warning
            """,
            (
                key,
                json.dumps(payload, ensure_ascii=False),
                generated_at,
                utc_now_iso(),
                stale_after,
                provider,
                status,
                warning,
            ),
        )
        connection.commit()


def read_story_set(key: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM story_sets WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"])
    payload["_store"] = row_metadata(row)
    return payload


def write_country_briefing(
    country: str,
    briefing: dict[str, Any],
    *,
    stale_after: str | None,
    status: str = "ready",
    warning: str | None = None,
) -> None:
    provider = briefing.get("sourceNote")
    generated_at = briefing.get("cachedAt")
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO country_briefings
                (country, payload_json, generated_at, refreshed_at, stale_after, provider, status, warning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(country) DO UPDATE SET
                payload_json = excluded.payload_json,
                generated_at = excluded.generated_at,
                refreshed_at = excluded.refreshed_at,
                stale_after = excluded.stale_after,
                provider = excluded.provider,
                status = excluded.status,
                warning = excluded.warning
            """,
            (
                country,
                json.dumps(briefing, ensure_ascii=False),
                generated_at,
                utc_now_iso(),
                stale_after,
                provider,
                status,
                warning,
            ),
        )
        connection.commit()


def read_country_briefing(country: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM country_briefings WHERE country = ?",
            (country,),
        ).fetchone()
    if not row:
        return None
    briefing = json.loads(row["payload_json"])
    briefing["_store"] = row_metadata(row)
    return briefing


def write_country_history(
    country: str,
    history: dict[str, Any],
    *,
    stale_after: str | None,
    status: str = "ready",
    warning: str | None = None,
) -> None:
    provider = history.get("provider")
    generated_at = history.get("generatedAt")
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO country_histories
                (country, payload_json, generated_at, refreshed_at, stale_after, provider, status, warning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(country) DO UPDATE SET
                payload_json = excluded.payload_json,
                generated_at = excluded.generated_at,
                refreshed_at = excluded.refreshed_at,
                stale_after = excluded.stale_after,
                provider = excluded.provider,
                status = excluded.status,
                warning = excluded.warning
            """,
            (
                country,
                json.dumps(history, ensure_ascii=False),
                generated_at,
                utc_now_iso(),
                stale_after,
                provider,
                status,
                warning,
            ),
        )
        connection.commit()


def read_country_history(country: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM country_histories WHERE country = ?",
            (country,),
        ).fetchone()
    if not row:
        return None
    history = json.loads(row["payload_json"])
    history["_store"] = row_metadata(row)
    return history


def stale_country_names(limit: int, now_iso: str | None = None) -> list[str]:
    now_iso = now_iso or utc_now_iso()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT country FROM country_briefings
            WHERE stale_after IS NULL OR stale_after <= ?
            ORDER BY COALESCE(stale_after, '') ASC, country ASC
            LIMIT ?
            """,
            (now_iso, limit),
        ).fetchall()
    return [row["country"] for row in rows]


def row_metadata(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "generatedAt": row["generated_at"],
        "refreshedAt": row["refreshed_at"],
        "staleAfter": row["stale_after"],
        "provider": row["provider"],
        "status": row["status"],
        "warning": row["warning"],
    }
