"""SQLite bootstrap - the app's local database.

Group 1 only creates the schema; jobs and assets get written by the features
that own them (jobs service, library service) in later groups. Short-lived
connections per call keep this trivially thread-safe for FastAPI.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER,
  status        TEXT NOT NULL DEFAULT 'queued',
  progress      INTEGER NOT NULL DEFAULT 0,
  tab           TEXT,
  module        TEXT,
  model_id      TEXT,
  model_name    TEXT,
  recipe        TEXT,
  prompt        TEXT,
  enhanced_prompt TEXT,
  seed          INTEGER,
  params_json   TEXT,
  stages_json   TEXT,
  result_ids_json TEXT,
  error         TEXT
);

CREATE TABLE IF NOT EXISTS assets (
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL,
  path        TEXT,
  thumb_path  TEXT,
  label       TEXT,
  prompt      TEXT,
  model       TEXT,
  seed        INTEGER,
  created_at  INTEGER,
  favorite    INTEGER NOT NULL DEFAULT 0,
  tags_json   TEXT,
  nsfw        INTEGER NOT NULL DEFAULT 0,
  width       INTEGER,
  height      INTEGER,
  bytes       INTEGER,
  sha256      TEXT,
  origin_job  TEXT
);

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(paths.DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    paths.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with connection() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '1')")


def _migrate(conn: sqlite3.Connection) -> None:
    """Tiny forward-only migrations for DBs created before a column existed.

    SQLite's CREATE TABLE IF NOT EXISTS doesn't touch existing tables, so new
    columns need an explicit ALTER here. Keep each step idempotent.
    """
    job_columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "progress" not in job_columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN progress INTEGER NOT NULL DEFAULT 0")


def table_names() -> list[str]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [row["name"] for row in rows]
