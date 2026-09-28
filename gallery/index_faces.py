#!/usr/bin/env python3
"""Find faces in every photo and group the same person together."""

import os
import time
from pathlib import Path

import cv2
import numpy as np

import faces_db
import faces_lib as F
import jobs_db

IMAGE_EXT = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif",
    ".tif", ".tiff", ".bmp",
}
MATCH_THRESH = 0.42


def all_images():
    found = []
    for dirpath, dirnames, filenames in os.walk(F.PHOTOS):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        folder = Path(dirpath)
        for name in filenames:
            if name.startswith("."):
                continue
            path = folder / name
            if path.suffix.lower() not in IMAGE_EXT:
                continue
            try:
                found.append((path.stat().st_mtime, path))
            except OSError:
                continue
    found.sort(reverse=True)
    return [path for _, path in found]


def load_centers(conn):
    centers = {}
    for person_id, blob in conn.execute("SELECT person_id, embedding FROM faces"):
        if not blob:
            continue
        vector = np.frombuffer(blob, dtype=np.float32).copy()
        slot = centers.setdefault(person_id, {
            "sum": np.zeros(512, dtype=np.float32),
            "count": 0,
        })
        slot["sum"] += vector
        slot["count"] += 1
    for slot in centers.values():
        slot["center"] = slot["sum"] / (np.linalg.norm(slot["sum"]) + 1e-8)
    return centers


def assign(centers, vector):
    best_id = None
    best_score = MATCH_THRESH
    for person_id, slot in centers.items():
        score = float(np.dot(vector, slot["center"]))
        if score > best_score:
            best_id = person_id
            best_score = score
    return best_id


def remember(centers, person_id, vector):
    slot = centers.setdefault(person_id, {
        "sum": np.zeros(512, dtype=np.float32),
        "count": 0,
        "center": vector,
    })
    slot["sum"] = slot["sum"] + vector
    slot["count"] += 1
    slot["center"] = slot["sum"] / (np.linalg.norm(slot["sum"]) + 1e-8)


def main():
    files = all_images()
    conn = faces_db.connect()
    faces_db.merge_same_names(conn)
    conn.execute("INSERT OR IGNORE INTO scanned(relpath) SELECT DISTINCT relpath FROM faces")
    already = conn.execute("SELECT COUNT(*) FROM scanned").fetchone()[0]
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('scanned', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(already),),
    )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('total', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(len(files)),),
    )
    conn.commit()
    done = {row[0] for row in conn.execute("SELECT relpath FROM scanned")}
    centers = load_centers(conn)
    pending = [path for path in files if str(path.relative_to(F.PHOTOS)) not in done]
    print(
        f"{len(files)} images. {len(done)} already scanned. {len(pending)} left.",
        flush=True,
    )
    if not pending:
        faces_db.export_metadata(conn)
        conn.close()
        jobs_db.beat("faces", "Saved in the database. Nothing new to scan.", state="idle")
        print("Nothing left to scan.", flush=True)
        return
    jobs_db.beat("faces", f"{len(pending)} photos are not in the database yet.")

    det = F.session(F.DET_PATH)
    rec = F.session(F.REC_PATH)
    F.CROP_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    new_faces = 0
    for index, path in enumerate(pending, start=1):
        rel = str(path.relative_to(F.PHOTOS))
        image = F.load_bgr(path)
        if image is None:
            conn.execute("INSERT OR IGNORE INTO scanned(relpath) VALUES (?)", (rel,))
            continue
        height, width = image.shape[:2]
        alive = {row[0] for row in conn.execute("SELECT id FROM people")}
        for gone in [person_id for person_id in centers if person_id not in alive]:
            centers.pop(gone, None)
        for face in F.detect_faces(det, image):
            aligned = F.align_face(image, face["kps"])
            if aligned is None:
                continue
            vector = F.embed_face(rec, aligned)
            person_id = assign(centers, vector)
            x1, y1, x2, y2 = face["box"]
            if person_id is None:
                cursor = conn.execute(
                    "INSERT INTO people(name, cover_face_id) VALUES ('', NULL)"
                )
                person_id = cursor.lastrowid
            face_cursor = conn.execute(
                """
                INSERT INTO faces(relpath, x1, y1, x2, y2, score, person_id, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rel, x1 / width, y1 / height, x2 / width, y2 / height,
                    face["score"], person_id, vector.tobytes(),
                ),
            )
            remember(centers, person_id, vector)
            new_faces += 1
            cover = conn.execute(
                "SELECT cover_face_id FROM people WHERE id = ?",
                (person_id,),
            ).fetchone()
            if cover and cover[0] is None:
                crop = F.square_crop(image, face["box"])
                if crop is not None:
                    face_id = face_cursor.lastrowid
                    cv2.imwrite(str(F.CROP_DIR / f"{face_id}.jpg"), crop)
                    conn.execute(
                        "UPDATE people SET cover_face_id = ? WHERE id = ?",
                        (face_id, person_id),
                    )
        conn.execute("INSERT OR IGNORE INTO scanned(relpath) VALUES (?)", (rel,))
        if index % 20 == 0 or index == len(pending):
            scanned_now = conn.execute("SELECT COUNT(*) FROM scanned").fetchone()[0]
            conn.execute(
                "INSERT INTO meta(key, value) VALUES ('scanned', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(scanned_now),),
            )
            conn.commit()
            elapsed = time.time() - started
            rate = index / elapsed if elapsed else 0
            left = (len(pending) - index) / rate if rate else 0
            note = (
                f"{index}/{len(pending)} new photos. "
                f"{rate:.1f}/s. About {left/60:.0f} min left."
            )
            jobs_db.beat("faces", note)
            print(
                f"{index}/{len(pending)}  new_faces={new_faces}  "
                f"{rate:.1f}/s  about {left/60:.0f} min left",
                flush=True,
            )
        if index % 200 == 0:
            faces_db.export_metadata(conn)
    scanned_now = conn.execute("SELECT COUNT(*) FROM scanned").fetchone()[0]
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('scanned', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(scanned_now),),
    )
    conn.commit()
    faces_db.export_metadata(conn)
    people = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    conn.close()
    jobs_db.beat(
        "faces",
        f"Saved in the database. {new_faces} new faces this run.",
        state="idle",
    )
    print(f"Done. {new_faces} new faces. {people} people total.", flush=True)


if __name__ == "__main__":
    main()
