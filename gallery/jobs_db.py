"""Progress for the face and caption jobs. No model code."""

import os
import sqlite3
import time
from pathlib import Path

ROOT = Path("/Volumes/SamsungT7/Google Photos Backup")
APP = ROOT / "gallery"
DB_PATH = APP / "jobs" / "jobs.sqlite"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            name TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            pid INTEGER,
            note TEXT NOT NULL DEFAULT '',
            updated REAL NOT NULL
        )
        """
    )
    return conn


def beat(name, note, state="running", force=False):
    if not force and state != "paused" and read(name)["state"] == "paused":
        return
    conn = connect()
    conn.execute(
        """
        INSERT INTO jobs(name, state, pid, note, updated)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            state = excluded.state,
            pid = excluded.pid,
            note = excluded.note,
            updated = excluded.updated
        """,
        (
            name,
            state,
            os.getpid() if state == "running" else None,
            str(note)[:240],
            time.time(),
        ),
    )
    conn.commit()
    conn.close()


def read(name):
    empty = {"state": "idle", "pid": None, "note": "", "updated": 0}
    if not DB_PATH.exists():
        return empty
    conn = connect()
    try:
        row = conn.execute(
            "SELECT state, pid, note, updated FROM jobs WHERE name = ?",
            (name,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return empty
    return {"state": row[0], "pid": row[1], "note": row[2] or "", "updated": row[3]}


def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True
