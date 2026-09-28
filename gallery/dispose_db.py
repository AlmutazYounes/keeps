"""Stored picture scores for the review dashboard. No model code."""

import sqlite3
from pathlib import Path

ROOT = Path("/Volumes/SamsungT7/Google Photos Backup")
APP = ROOT / "gallery"
DB_PATH = APP / "dispose" / "dispose.sqlite"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
            relpath TEXT PRIMARY KEY,
            sharp REAL NOT NULL,
            spread REAL NOT NULL,
            mtime REAL NOT NULL
        )
        """
    )
    return conn


def score_map():
    if not DB_PATH.exists():
        return {}
    conn = connect()
    try:
        rows = conn.execute("SELECT relpath, sharp, spread, mtime FROM scores")
        return {rel: (sharp, spread, mtime) for rel, sharp, spread, mtime in rows}
    finally:
        conn.close()


def save_score(conn, relpath, sharp, spread, mtime):
    conn.execute(
        """
        INSERT INTO scores(relpath, sharp, spread, mtime)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(relpath) DO UPDATE SET
            sharp = excluded.sharp,
            spread = excluded.spread,
            mtime = excluded.mtime
        """,
        (relpath, sharp, spread, mtime),
    )
