#!/usr/bin/env python3
"""Copy Google Takeout photos into year/month folders on this drive.

Album copies of the same Google photo are kept once.
Dates come from Takeout metadata, then from the filename.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

_GALLERY = Path(__file__).resolve().parent / "gallery"
if str(_GALLERY) not in sys.path:
    sys.path.insert(0, str(_GALLERY))
import library_root

ROOT = library_root.library_root()
DEST = ROOT / "Photos"
STAGING = ROOT / "_staging"
DB_PATH = ROOT / "_sort_state.sqlite"
LOG_PATH = ROOT / "_sort.log"

MEDIA_EXT = {
    ".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".webp",
    ".tif", ".tiff", ".bmp", ".dng", ".mp4", ".mov", ".m4v",
    ".3gp", ".asf", ".avi", ".mkv", ".webm", ".mpg", ".mpeg",
    ".mp", ".mp~2",
}
SKIP_EXT = {".json", ".html", ".txt", ".csv", ".pdf", ".xml"}
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
DATE_RE = re.compile(
    r"(?<!\d)(?P<y>19\d{2}|20\d{2})[-_. ]?(?P<m>0[1-9]|1[0-2])[-_. ]?(?P<d>0[1-9]|[12]\d|3[01])"
)
META_JSON_RE = re.compile(
    r"^(?P<stem>.+?)(?P<ext>\.[A-Za-z0-9]+)\.supplemental-metadata(?P<num>\(\d+\))?\.json$",
    re.IGNORECASE,
)
FB_RE = re.compile(r"FB_IMG_(\d{10,13})")
EXIF_DATE_RE = re.compile(
    rb"(?P<y>19\d{2}|20\d{2}):(?P<m>0[1-9]|1[0-2]):(?P<d>0[1-9]|[12]\d|3[01]) "
    rb"(?P<H>[0-2]\d):(?P<M>[0-5]\d):(?P<S>[0-5]\d)"
)
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".3gp", ".asf", ".avi", ".mkv", ".webm", ".mpg", ".mpeg", ".mp", ".mp~2"}
YEAR_FOLDER_RE = re.compile(r"Photos from (?P<y>19\d{2}|20\d{2})$")
COPY_CHUNK = 8 * 1024 * 1024


def log(msg):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')}  {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS by_path (
            path TEXT PRIMARY KEY,
            ts INTEGER,
            url TEXT
        );
        CREATE TABLE IF NOT EXISTS by_dir_name (
            dir TEXT,
            name TEXT,
            ts INTEGER,
            url TEXT,
            PRIMARY KEY (dir, name)
        );
        CREATE TABLE IF NOT EXISTS seen_url (
            url TEXT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS seen_hash (
            sha TEXT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS done_member (
            zip_name TEXT,
            member TEXT,
            PRIMARY KEY (zip_name, member)
        );
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    return conn


def zip_paths():
    paths = sorted(ROOT.glob("takeout-*.zip"))
    return paths


def media_paths_for_json(path):
    parent, base = path.rsplit("/", 1) if "/" in path else ("", path)
    names = []
    match = META_JSON_RE.match(base)
    if match:
        stem = match.group("stem")
        ext = match.group("ext")
        num = match.group("num") or ""
        names.append(stem + ext)
        if num:
            names.append(stem + num + ext)
    elif base.lower().endswith(".supplemental-metadata.json"):
        names.append(base[: -len(".supplemental-metadata.json")])
    elif base.lower().endswith(".json"):
        names.append(base[:-5])
    paths = []
    for name in names:
        if not name or name.endswith("/"):
            continue
        paths.append(f"{parent}/{name}" if parent else name)
    return paths


def parse_taken(payload):
    block = payload.get("photoTakenTime") or payload.get("creationTime") or {}
    raw = block.get("timestamp")
    if raw is None:
        return None
    try:
        ts = int(raw)
    except (TypeError, ValueError):
        return None
    if ts > 10**12:
        ts //= 1000
    if ts < 0:
        return None
    try:
        dt = datetime.datetime.fromtimestamp(ts)
    except (OverflowError, OSError, ValueError):
        return None
    if dt.year < 1950 or dt.year > 2027:
        return None
    return ts


def index_zips(conn):
    version = conn.execute(
        "SELECT value FROM meta WHERE key='index_version'"
    ).fetchone()
    if version and version[0] == "2":
        log("Date index already built. Skipping scan.")
        return
    conn.execute("DELETE FROM by_path")
    conn.execute("DELETE FROM by_dir_name")
    conn.commit()
    zips = zip_paths()
    log(f"Indexing dates from {len(zips)} zip files.")
    stored = 0
    for zp in zips:
        count = 0
        with zipfile.ZipFile(zp) as zf:
            for info in zf.infolist():
                name = info.filename
                if name.endswith("/") or not name.lower().endswith(".json"):
                    continue
                if info.file_size > 2_000_000:
                    continue
                media_paths = media_paths_for_json(name)
                if not media_paths:
                    continue
                try:
                    with zf.open(info) as fh:
                        payload = json.loads(fh.read().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile, KeyError):
                    continue
                if not isinstance(payload, dict):
                    continue
                ts = parse_taken(payload)
                if ts is None:
                    continue
                url = payload.get("url") or ""
                title = payload.get("title") or ""
                parent = media_paths[0].rsplit("/", 1)[0] if "/" in media_paths[0] else ""
                for media_path in media_paths:
                    conn.execute(
                        "INSERT OR IGNORE INTO by_path(path, ts, url) VALUES (?, ?, ?)",
                        (media_path, ts, url),
                    )
                    base = media_path.rsplit("/", 1)[-1]
                    conn.execute(
                        "INSERT OR IGNORE INTO by_dir_name(dir, name, ts, url) VALUES (?, ?, ?, ?)",
                        (parent, base, ts, url),
                    )
                if title:
                    conn.execute(
                        "INSERT OR IGNORE INTO by_dir_name(dir, name, ts, url) VALUES (?, ?, ?, ?)",
                        (parent, title, ts, url),
                    )
                count += 1
        conn.commit()
        stored += count
        log(f"Indexed {zp.name}: {count} dated items")
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('index_version', '2')"
    )
    conn.commit()
    log(f"Date index complete. {stored} metadata files.")


def lookup_meta(conn, member, extra_names):
    row = conn.execute(
        "SELECT ts, url FROM by_path WHERE path=?", (member,)
    ).fetchone()
    if row:
        return row
    parent = member.rsplit("/", 1)[0] if "/" in member else ""
    names = [member.rsplit("/", 1)[-1], *extra_names]
    seen = set()
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        row = conn.execute(
            "SELECT ts, url FROM by_dir_name WHERE dir=? AND name=?",
            (parent, name),
        ).fetchone()
        if row:
            return row
    return None


def filename_date(name):
    match = DATE_RE.search(name)
    if not match:
        return None
    year = int(match.group("y"))
    month = int(match.group("m"))
    day = int(match.group("d"))
    if year < 1950 or year > 2027:
        return None
    try:
        return datetime.datetime(year, month, day)
    except ValueError:
        return None


def fb_date(name):
    match = FB_RE.search(name)
    if not match:
        return None
    raw = int(match.group(1))
    if raw > 10**12:
        raw //= 1000
    try:
        dt = datetime.datetime.fromtimestamp(raw)
    except (OverflowError, OSError, ValueError):
        return None
    if dt.year < 1950 or dt.year > 2027:
        return None
    return dt


def exif_date_from_file(path):
    with path.open("rb") as fh:
        blob = fh.read(8 * 1024 * 1024)
    match = EXIF_DATE_RE.search(blob)
    if not match:
        return None
    try:
        return datetime.datetime(
            int(match.group("y")),
            int(match.group("m")),
            int(match.group("d")),
            int(match.group("H")),
            int(match.group("M")),
            int(match.group("S")),
        )
    except ValueError:
        return None


def ffprobe_date(path):
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format_tags=creation_time",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    line = proc.stdout.strip().splitlines()
    if not line:
        return None
    raw = line[0].strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    if dt.year < 1950 or dt.year > 2027:
        return None
    return dt


def embedded_date(path, kind, original_name):
    ext = ""
    if "." in original_name:
        ext = "." + original_name.rsplit(".", 1)[-1].lower()
    if kind == "video" or ext in VIDEO_EXT:
        return ffprobe_date(path)
    return exif_date_from_file(path)


def folder_year(member):
    parts = member.split("/")
    if len(parts) < 3:
        return None
    match = YEAR_FOLDER_RE.search(parts[2])
    if not match:
        return None
    return int(match.group("y"))


def dest_for(dt, year_only):
    if dt is not None:
        year = f"{dt.year:04d}"
        month = f"{dt.month:02d}-{MONTHS[dt.month - 1]}"
        return DEST / year / month
    if year_only is not None:
        return DEST / f"{year_only:04d}" / "Unknown"
    return DEST / "Unknown"


def safe_filename(name):
    name = name.replace("/", "_").replace("\x00", "").strip()
    if name in {"", ".", ".."}:
        name = "untitled"
    raw = name.encode("utf-8")
    if len(raw) <= 220:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot:
        return raw[:220].decode("utf-8", "ignore")
    ext_b = ("." + ext).encode("utf-8")
    keep = 220 - len(ext_b)
    return stem.encode("utf-8")[:keep].decode("utf-8", "ignore") + "." + ext


def unique_path(folder, filename):
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem, ext = filename, ""
    else:
        ext = "." + ext
    n = 2
    while True:
        candidate = folder / f"{stem}-{n}{ext}"
        if not candidate.exists():
            return candidate
        n += 1


def sniff_ext(header, original_name):
    ext = ""
    if "." in original_name:
        ext = "." + original_name.rsplit(".", 1)[-1]
    low = ext.lower()
    kind = None
    fixed = None
    if header.startswith(b"\xff\xd8\xff"):
        kind = "image"
        if low in {".jp", ".jpe"}:
            fixed = ".jpg"
    elif header.startswith(b"\x89PNG"):
        kind = "image"
    elif header.startswith(b"GIF8"):
        kind = "image"
    elif header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in {b"heic", b"heix", b"mif1", b"heif"}:
            kind = "image"
            if low in {"", ".heic"}:
                fixed = ".heic" if low == "" else None
        elif brand == b"qt  ":
            kind = "video"
            if low in {"", ".mp", ".mp~2"}:
                fixed = ".mov"
        elif brand in {b"3gp4", b"3gp5"}:
            kind = "video"
        else:
            kind = "video"
            if low in {"", ".mp", ".mp~2"}:
                fixed = ".mp4"
    elif header.startswith(b"0&\xb2u"):
        kind = "video"
        if low == "":
            fixed = ".asf"
    if fixed and original_name.lower().endswith(".mp~2"):
        base = original_name[: -len(ext)] if ext else original_name
        return kind, base + "-2" + fixed
    if fixed:
        if ext and original_name.lower().endswith(ext.lower()):
            base = original_name[: -len(ext)]
        else:
            base = original_name
        return kind, base + fixed
    if low == "" and kind == "video":
        return kind, original_name + ".mov"
    return kind, original_name


def extra_lookup_names(original, fixed_name, kind):
    names = []
    if fixed_name != original:
        names.append(fixed_name)
    low = original.lower()
    stem = original.rsplit(".", 1)[0] if "." in original else original
    if kind == "video" and (low.endswith(".mp") or low.endswith(".mp~2") or "." not in original):
        names.extend([stem + ".mp4", stem + ".MP4", stem + ".mov", stem + ".MOV"])
    elif kind == "image" and "." not in original:
        names.extend([original + ".jpg", original + ".JPG", original + ".jpeg", original + ".heic"])
    return names


def is_media(name):
    base = name.rsplit("/", 1)[-1]
    if not base or base.startswith("._"):
        return False
    if "." not in base:
        return True
    ext = "." + base.rsplit(".", 1)[-1].lower()
    if ext in SKIP_EXT:
        return False
    if ext in MEDIA_EXT:
        return True
    return False


def apply_mtime(path, dt, ts):
    if ts:
        stamp = float(ts)
    elif dt is not None:
        stamp = dt.timestamp()
    else:
        return
    os.utime(path, (stamp, stamp))


def extract_all(conn):
    zips = zip_paths()
    STAGING.mkdir(parents=True, exist_ok=True)
    copied = skipped = undated = errors = 0
    for index, zp in enumerate(zips, start=1):
        log(f"Opening {zp.name} ({index}/{len(zips)})")
        done = {
            row[0]
            for row in conn.execute(
                "SELECT member FROM done_member WHERE zip_name=?", (zp.name,)
            )
        }
        with zipfile.ZipFile(zp) as zf:
            members = [i for i in zf.infolist() if not i.is_dir() and is_media(i.filename)]
            log(f"{zp.name}: {len(members)} media files, {len(done)} already handled")
            for n, info in enumerate(members, start=1):
                member = info.filename
                if member in done:
                    continue
                if info.file_size <= 0:
                    conn.execute(
                        "INSERT OR IGNORE INTO done_member(zip_name, member) VALUES (?, ?)",
                        (zp.name, member),
                    )
                    continue
                try:
                    outcome = copy_member(conn, zf, info)
                except Exception as exc:
                    errors += 1
                    log(f"ERROR {zp.name} {member}: {exc}")
                    continue
                if outcome == "copied":
                    copied += 1
                elif outcome == "duplicate":
                    skipped += 1
                elif outcome == "undated":
                    undated += 1
                    copied += 1
                if n % 200 == 0:
                    conn.commit()
                    log(
                        f"{zp.name} {n}/{len(members)}  "
                        f"copied={copied} duplicates={skipped} undated={undated} errors={errors}"
                    )
        conn.commit()
        log(
            f"Finished {zp.name}. copied={copied} duplicates={skipped} "
            f"undated={undated} errors={errors}"
        )
    log(
        f"Done. copied={copied} duplicates={skipped} undated={undated} errors={errors}"
    )


def copy_member(conn, zf, info):
    member = info.filename
    original = member.rsplit("/", 1)[-1]
    meta = lookup_meta(conn, member, [])
    url = meta[1] if meta else ""
    if url and conn.execute("SELECT 1 FROM seen_url WHERE url=?", (url,)).fetchone():
        mark_done(conn, zf, member)
        conn.commit()
        return "duplicate"

    hasher = hashlib.sha256()
    tmp = STAGING / "current.partial"
    with zf.open(info) as src, tmp.open("wb") as dst:
        header = src.read(32)
        if header:
            dst.write(header)
            hasher.update(header)
        while True:
            chunk = src.read(COPY_CHUNK)
            if not chunk:
                break
            dst.write(chunk)
            hasher.update(chunk)
    kind, fixed_name = sniff_ext(header, original)
    digest = hasher.hexdigest()
    if conn.execute("SELECT 1 FROM seen_hash WHERE sha=?", (digest,)).fetchone():
        tmp.unlink(missing_ok=True)
        mark_done(conn, zf, member)
        conn.commit()
        return "duplicate"

    if meta is None:
        meta = lookup_meta(conn, member, extra_lookup_names(original, fixed_name, kind))
        url = meta[1] if meta else ""
        if url and conn.execute("SELECT 1 FROM seen_url WHERE url=?", (url,)).fetchone():
            tmp.unlink(missing_ok=True)
            mark_done(conn, zf, member)
            conn.commit()
            return "duplicate"

    ts = meta[0] if meta else None
    dt = datetime.datetime.fromtimestamp(ts) if ts else None
    if dt is None:
        dt = filename_date(fixed_name) or filename_date(original) or fb_date(original)
    if dt is None:
        dt = embedded_date(tmp, kind, original)
    year_only = None if dt is not None else folder_year(member)
    folder = dest_for(dt, year_only)
    folder.mkdir(parents=True, exist_ok=True)
    target = unique_path(folder, safe_filename(fixed_name))
    os.replace(tmp, target)
    apply_mtime(target, dt, ts)
    conn.execute("INSERT OR IGNORE INTO seen_hash(sha) VALUES (?)", (digest,))
    if url:
        conn.execute("INSERT OR IGNORE INTO seen_url(url) VALUES (?)", (url,))
    mark_done(conn, zf, member)
    conn.commit()
    if dt is None:
        return "undated"
    return "copied"


def mark_done(conn, zf, member):
    zip_name = Path(zf.filename).name
    conn.execute(
        "INSERT OR IGNORE INTO done_member(zip_name, member) VALUES (?, ?)",
        (zip_name, member),
    )


def report_match_rate(conn):
    zips = zip_paths()
    media = dated = 0
    for zp in zips:
        with zipfile.ZipFile(zp) as zf:
            for info in zf.infolist():
                if info.is_dir() or not is_media(info.filename):
                    continue
                media += 1
                if lookup_meta(conn, info.filename, []):
                    dated += 1
                elif filename_date(info.filename.rsplit("/", 1)[-1]):
                    dated += 1
                elif folder_year(info.filename):
                    dated += 1
    log(f"Date coverage: {dated}/{media} media files have a year.")
    return media, dated


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    conn = connect()
    index_zips(conn)
    if "--index-only" in sys.argv:
        report_match_rate(conn)
        return
    free = shutil.disk_usage(ROOT).free
    log(f"Free space: {free / (1024 ** 3):.1f} GiB")
    if free < 20 * 1024 ** 3:
        log("Less than 20 GiB free. Stopping.")
        sys.exit(1)
    extract_all(conn)


if __name__ == "__main__":
    main()
