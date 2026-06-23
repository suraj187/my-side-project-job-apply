"""SQLite storage. Tracks every job by dedup_key so runs only surface what's new."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .models import Job

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    dedup_key      TEXT PRIMARY KEY,
    source         TEXT,
    title          TEXT,
    company        TEXT,
    url            TEXT,
    location       TEXT,
    workplace      TEXT,
    comp           TEXT,
    posted_at      TEXT,
    external_id    TEXT,
    score          INTEGER,
    reason         TEXT,
    flags          TEXT,
    status         TEXT DEFAULT 'new',
    first_seen     TEXT,
    last_seen      TEXT,
    notion_row_id  TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def is_known(self, dedup_key: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM jobs WHERE dedup_key = ?", (dedup_key,))
        return cur.fetchone() is not None

    def upsert(self, job: Job) -> bool:
        """Insert a new job (returns True) or refresh last_seen (returns False)."""
        row = job.to_row()
        now = _now()
        if self.is_known(row["dedup_key"]):
            self.conn.execute(
                "UPDATE jobs SET last_seen=?, score=?, reason=?, flags=? WHERE dedup_key=?",
                (now, row["score"], row["reason"], row["flags"], row["dedup_key"]),
            )
            self.conn.commit()
            return False
        self.conn.execute(
            """INSERT INTO jobs
               (dedup_key, source, title, company, url, location, workplace, comp,
                posted_at, external_id, score, reason, flags, status, first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["dedup_key"], row["source"], row["title"], row["company"], row["url"],
             row["location"], row["workplace"], row["comp"], row["posted_at"],
             row["external_id"], row["score"], row["reason"], row["flags"],
             "new", now, now),
        )
        self.conn.commit()
        return True

    def recent(self, status: Optional[str] = None, limit: int = 100) -> list[sqlite3.Row]:
        q = "SELECT * FROM jobs"
        params: list = []
        if status:
            q += " WHERE status = ?"
            params.append(status)
        q += " ORDER BY score DESC, first_seen DESC LIMIT ?"
        params.append(limit)
        return list(self.conn.execute(q, params))

    def set_status(self, dedup_key: str, status: str) -> None:
        self.conn.execute("UPDATE jobs SET status=? WHERE dedup_key=?", (status, dedup_key))
        self.conn.commit()

    def set_notion_row_id(self, dedup_key: str, notion_row_id: str) -> None:
        self.conn.execute("UPDATE jobs SET notion_row_id=? WHERE dedup_key=?",
                         (notion_row_id, dedup_key))
        self.conn.commit()

    def get_notion_id_map(self) -> dict[str, str]:
        """Return {dedup_key: notion_row_id} for all jobs with notion_row_id set."""
        rows = self.conn.execute("SELECT dedup_key, notion_row_id FROM jobs WHERE notion_row_id IS NOT NULL")
        return {row[0]: row[1] for row in rows}

    def close(self) -> None:
        self.conn.close()
