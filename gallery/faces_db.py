"""Face index storage. No model code, so the photo server can import it."""

import json
import sqlite3
from pathlib import Path

ROOT = Path("/Volumes/SamsungT7/Google Photos Backup")
APP = ROOT / "gallery"
DB_PATH = APP / "faces" / "faces.sqlite"
META_PATH = APP / "faces" / "image_faces.json"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            cover_face_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS faces (
            id INTEGER PRIMARY KEY,
            relpath TEXT NOT NULL,
            x1 REAL, y1 REAL, x2 REAL, y2 REAL,
            score REAL,
            person_id INTEGER,
            embedding BLOB
        );
        CREATE TABLE IF NOT EXISTS scanned (
            relpath TEXT PRIMARY KEY
        );
        CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);
        CREATE INDEX IF NOT EXISTS idx_faces_path ON faces(relpath);
        """
    )
    return conn


def export_metadata(conn):
    grouped = {}
    rows = conn.execute(
        """
        SELECT f.relpath, f.person_id, p.name, f.x1, f.y1, f.x2, f.y2, f.score
        FROM faces f JOIN people p ON p.id = f.person_id
        ORDER BY f.relpath, f.score DESC
        """
    )
    for relpath, person_id, name, x1, y1, x2, y2, score in rows:
        grouped.setdefault(relpath, []).append({
            "person_id": person_id,
            "name": name,
            "box": [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)],
            "score": round(score, 3),
        })
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(json.dumps(grouped, indent=2))
    return grouped


def merge_people(conn, source_id, target_id):
    conn.execute(
        "UPDATE faces SET person_id = ? WHERE person_id = ?",
        (target_id, source_id),
    )
    target_cover = conn.execute(
        "SELECT cover_face_id FROM people WHERE id = ?",
        (target_id,),
    ).fetchone()
    if target_cover and not target_cover[0]:
        source_cover = conn.execute(
            "SELECT cover_face_id FROM people WHERE id = ?",
            (source_id,),
        ).fetchone()
        if source_cover and source_cover[0]:
            conn.execute(
                "UPDATE people SET cover_face_id = ? WHERE id = ?",
                (source_cover[0], target_id),
            )
    conn.execute("DELETE FROM people WHERE id = ?", (source_id,))


def merge_same_names(conn):
    rows = conn.execute(
        "SELECT id, name FROM people WHERE trim(name) != '' ORDER BY id"
    ).fetchall()
    keeper = {}
    merged = 0
    for person_id, name in rows:
        key = name.strip().lower()
        if key in keeper:
            merge_people(conn, person_id, keeper[key])
            merged += 1
        else:
            keeper[key] = person_id
    return merged


def scanned_set():
    if not DB_PATH.exists():
        return set()
    conn = connect()
    try:
        return {row[0] for row in conn.execute("SELECT relpath FROM scanned")}
    finally:
        conn.close()


def add_face(relpath, box, name=""):
    x1, y1, x2, y2 = [float(value) for value in box]
    if min(x1, y1, x2, y2) < 0 or max(x1, y1, x2, y2) > 1:
        raise ValueError("bad box")
    if x2 - x1 < 0.02 or y2 - y1 < 0.02:
        raise ValueError("bad box")
    conn = connect()
    person = conn.execute(
        "INSERT INTO people(name, cover_face_id) VALUES ('', NULL)"
    )
    person_id = person.lastrowid
    face = conn.execute(
        """
        INSERT INTO faces(relpath, x1, y1, x2, y2, score, person_id, embedding)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (relpath, x1, y1, x2, y2, 1.0, person_id),
    )
    face_id = face.lastrowid
    conn.execute(
        "UPDATE people SET cover_face_id = ? WHERE id = ?",
        (face_id, person_id),
    )
    conn.commit()
    export_metadata(conn)
    conn.close()
    merged_into = None
    cleaned = str(name or "").strip()
    if cleaned:
        merged_into = set_name(person_id, cleaned)
        if merged_into:
            person_id = merged_into
    return {
        "face_id": face_id,
        "person_id": person_id,
        "merged_into": merged_into,
    }


def set_name(person_id, name):
    conn = connect()
    name = name.strip()
    merged_into = None
    if name:
        existing = conn.execute(
            """
            SELECT id FROM people
            WHERE id != ? AND lower(trim(name)) = lower(?)
            ORDER BY id LIMIT 1
            """,
            (person_id, name),
        ).fetchone()
        if existing:
            merge_people(conn, person_id, existing[0])
            merged_into = existing[0]
        else:
            conn.execute(
                "UPDATE people SET name = ? WHERE id = ?",
                (name, person_id),
            )
    else:
        conn.execute("UPDATE people SET name = '' WHERE id = ?", (person_id,))
    conn.commit()
    export_metadata(conn)
    conn.close()
    return merged_into
