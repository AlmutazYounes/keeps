"""Photo captions. No model code, so the photo server can import it."""

import sqlite3

import library_root

ROOT = library_root.library_root()
APP = library_root.data_dir()
DB_PATH = APP / "captions" / "captions.sqlite"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS captions (
            relpath TEXT PRIMARY KEY,
            caption TEXT NOT NULL,
            mtime REAL NOT NULL,
            ok INTEGER NOT NULL
        )
        """
    )
    return conn


def caption_map():
    if not DB_PATH.exists():
        return {}
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT relpath, caption FROM captions WHERE ok = 1 AND caption != ''"
        )
        return {relpath: text for relpath, text in rows}
    finally:
        conn.close()


def clear_for_rerun():
    conn = connect()
    conn.execute("DELETE FROM captions")
    conn.commit()
    conn.close()


def saved_times():
    if not DB_PATH.exists():
        return {}
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT relpath, mtime FROM captions WHERE ok = 1"
        )
        return {relpath: mtime for relpath, mtime in rows}
    finally:
        conn.close()


def one(relpath):
    if not DB_PATH.exists():
        return ""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT caption FROM captions WHERE relpath = ? AND ok = 1",
            (relpath,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return ""
    return row[0]
