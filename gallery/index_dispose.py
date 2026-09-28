#!/usr/bin/env python3
"""Score still photos for the review dashboard. The gallery does not start this."""

import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import dispose_db
import dispose_lib
import jobs_db

import library_root

PHOTOS = library_root.photos_dir()
IMAGE_EXT = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif",
    ".tif", ".tiff", ".bmp",
}


def all_images():
    found = []
    for dirpath, dirnames, filenames in os.walk(PHOTOS):
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


def read_gray(path):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is not None:
        return image
    tmp = Path(tempfile.mkdtemp()) / "frame.jpg"
    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", "-Z", "480", "--out", str(tmp), str(path)],
            capture_output=True,
            timeout=20,
        )
        if tmp.exists() and tmp.stat().st_size > 0:
            return cv2.imread(str(tmp), cv2.IMREAD_GRAYSCALE)
    finally:
        tmp.unlink(missing_ok=True)
        try:
            tmp.parent.rmdir()
        except OSError:
            pass
    return None


def measure(path):
    image = read_gray(path)
    if image is None:
        return None
    height, width = image.shape[:2]
    scale = 256 / max(height, width, 1)
    if scale < 1:
        image = cv2.resize(image, (max(1, int(width * scale)), max(1, int(height * scale))))
    raw_sharp = float(cv2.Laplacian(image, cv2.CV_64F).var())
    raw_spread = float(image.std())
    return dispose_lib.normalize(raw_sharp, raw_spread)


def main():
    files = all_images()
    conn = dispose_db.connect()
    saved = {
        rel: mtime
        for rel, _sharp, _spread, mtime in conn.execute("SELECT relpath, sharp, spread, mtime FROM scores")
    }
    pending = []
    for mtime, path in files:
        rel = str(path.relative_to(PHOTOS))
        old = saved.get(rel)
        if old is not None and abs(float(old) - float(mtime)) < 0.001:
            continue
        pending.append((rel, path, mtime))
    total = len(files)
    jobs_db.beat("dispose", "Looking at %s photos" % len(pending))
    done = 0
    for rel, path, mtime in pending:
        scored = measure(path)
        done += 1
        if scored is None:
            continue
        sharp, spread = scored
        dispose_db.save_score(conn, rel, sharp, spread, mtime)
        if done % 20 == 0:
            conn.commit()
            jobs_db.beat("dispose", "Scored %s of %s" % (done, len(pending)))
    conn.commit()
    conn.close()
    jobs_db.beat("dispose", "Scored %s still photos" % total, state="done")


if __name__ == "__main__":
    main()
