"""Lightweight database helpers built around :mod:`sqlite3`.

The schema is intentionally compact to keep the project easy to run on
machines that only ship with Python's standard library.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional


CREATE_STATEMENTS: List[str] = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT UNIQUE NOT NULL,
        username TEXT,
        first_name TEXT,
        role TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        base_url TEXT NOT NULL,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        country TEXT NOT NULL,
        inbound_id INTEGER NOT NULL,
        volume_gb INTEGER NOT NULL,
        duration_days INTEGER NOT NULL,
        multi_user INTEGER NOT NULL DEFAULT 1,
        price REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
        status TEXT NOT NULL,
        receipt_file_id TEXT,
        config_id TEXT,
        expires_at TEXT,
        traffic_used REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        approved_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
]


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with sensible defaults."""

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    """Create tables if they do not exist."""

    cursor = conn.cursor()
    for statement in CREATE_STATEMENTS:
        cursor.execute(statement)
    conn.commit()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Cursor]:
    """Context manager that wraps a transaction."""

    cursor = conn.cursor()
    try:
        yield cursor
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def fetch_one(cursor: sqlite3.Cursor) -> Optional[Dict[str, str]]:
    """Convert a single row into a dictionary."""

    row = cursor.fetchone()
    return dict(row) if row else None


def fetch_all(cursor: sqlite3.Cursor) -> List[Dict[str, str]]:
    """Convert rows into a list of dictionaries."""

    rows = cursor.fetchall()
    return [dict(row) for row in rows]
