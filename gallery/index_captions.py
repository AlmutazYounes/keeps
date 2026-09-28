#!/usr/bin/env python3
"""Write a searchable description for every still photo."""

import os
import time
from pathlib import Path

import caption_lib as C
import captions_db
import jobs_db

IMAGE_EXT = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif",
    ".tif", ".tiff", ".bmp",
}


def all_images():
    found = []
    for dirpath, dirnames, filenames in os.walk(C.PHOTOS):
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
    return found


def main():
    files = all_images()
    conn = captions_db.connect()
    done = {
        row[0]: row[1]
        for row in conn.execute("SELECT relpath, mtime FROM captions WHERE ok = 1")
    }
    pending = []
    for mtime, path in files:
        rel = str(path.relative_to(C.PHOTOS))
        if done.get(rel) == mtime:
            continue
        pending.append((mtime, path, rel))
    print(
        f"{len(files)} images. {len(files) - len(pending)} already described. {len(pending)} left.",
        flush=True,
    )
    if not pending:
        conn.close()
        jobs_db.beat("captions", "Saved in the database. Nothing new to describe.", state="idle")
        print("Nothing left to describe.", flush=True)
        return

    jobs_db.beat("captions", f"{len(pending)} photos are not in the database yet.")
    captioner = C.Captioner()
    started = time.time()
    for index, (mtime, path, rel) in enumerate(pending, start=1):
        if jobs_db.read("captions")["state"] == "paused":
            conn.commit()
            conn.close()
            print("Paused.", flush=True)
            return
        ok = 1
        try:
            text = captioner.caption_path(path)
        except Exception as error:
            text = ""
            ok = 0
            print(f"skip {rel}: {error}", flush=True)
        conn.execute(
            """
            INSERT INTO captions(relpath, caption, mtime, ok)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(relpath) DO UPDATE SET
                caption = excluded.caption,
                mtime = excluded.mtime,
                ok = excluded.ok
            """,
            (rel, text, mtime, ok),
        )
        if index % 10 == 0 or index == len(pending):
            conn.commit()
            elapsed = time.time() - started
            rate = index / elapsed if elapsed else 0
            left = (len(pending) - index) / rate if rate else 0
            sample = text[:90]
            jobs_db.beat(
                "captions",
                f"{index}/{len(pending)} new photos. {rate:.2f}/s. About {left/60:.0f} min left.",
            )
            print(
                f"{index}/{len(pending)}  {rate:.2f}/s  about {left/60:.0f} min left  {sample}",
                flush=True,
            )
    conn.commit()
    conn.close()
    jobs_db.beat("captions", "Saved in the database. Nothing new to describe.", state="idle")
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
