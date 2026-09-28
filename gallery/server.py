#!/usr/bin/env python3
"""Local photo library browser for the sorted Google Photos backup.

Originals stay in Photos/. Thumbnails are cached under gallery/cache/.
"""

import json
import mimetypes
import os
import shutil
import signal
import time
import plistlib
import re
import socket
import subprocess
import threading
import urllib.request
from datetime import datetime, timezone

import captions_db
import candidates
import categories
import dispose_db
import edits
import dispose_lib
import faces_db
import jobs_db
import library_actions
import model_choices
import search_lib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path("/Volumes/SamsungT7/Google Photos Backup")
PHOTOS = ROOT / "Photos"
APP = ROOT / "gallery"
CACHE = APP / "cache" / "thumbs"
VIEWS = APP / "cache" / "views"
PAGE = APP / "static" / "index.html"
FACES_PAGE = APP / "static" / "faces.html"
SETTINGS_PAGE = APP / "static" / "settings.html"
REVIEW_PAGE = APP / "static" / "review.html"
CATEGORIES_PAGE = APP / "static" / "categories.html"
CARTO_KEY_PATH = APP / "carto.key"
CARTO_KEY_MARK = "%%CARTO_KEY%%"
VENV_PYTHON = APP / ".venv" / "bin" / "python"
INDEX_JOBS = {
    "faces": "index_faces.py",
    "captions": "index_captions.py",
}
FACE_CROPS = APP / "cache" / "faces"
FACE_BOXES = APP / "cache" / "facebox"
PLACE_PATH = APP / "cache" / "places.json"
PLACE_LOCK = threading.Lock()
GEO_PATH = APP / "cache" / "geo.json"
GEO_LOCK = threading.Lock()
GEO = {"by_rel": {}, "done": False, "total": 0, "scanned": 0}
_geo_started = False
US_STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}
HOST = "127.0.0.1"
PORT = 8765

IMAGE_EXT = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif",
    ".tif", ".tiff", ".bmp",
}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".3gp", ".asf", ".webm"}
BROWSER_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MONTH_NAMES = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}

LIBRARY = {"ready": False, "count": 0, "groups": [], "by_id": {}}
LIBRARY_LOCK = threading.Lock()
SEM = threading.Semaphore(4)
LOCKS = {}
LOCKS_GUARD = threading.Lock()


def lock_for(key):
    with LOCKS_GUARD:
        lock = LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            LOCKS[key] = lock
        return lock


def kind_for(ext):
    if ext in VIDEO_EXT:
        return "video"
    if ext in BROWSER_IMAGE:
        return "image"
    return "convert"


def month_sort_value(month):
    if month == "Unknown":
        return -1
    try:
        return int(month[:2])
    except ValueError:
        return -1


def year_sort_value(year):
    if year.isdigit():
        return int(year)
    return -1


def label_for(year, month):
    if year == "Unknown":
        return "Undated"
    if month == "Unknown":
        return f"Undated {year}"
    nice = MONTH_NAMES.get(month[:2], month)
    return f"{nice} {year}"


def scan():
    found = []
    for dirpath, dirnames, filenames in os.walk(PHOTOS):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        folder = Path(dirpath)
        rel_dir = folder.relative_to(PHOTOS)
        parts = rel_dir.parts
        year = parts[0] if parts else "Unknown"
        month = parts[1] if len(parts) > 1 else "Unknown"
        for name in filenames:
            if name.startswith("."):
                continue
            ext = Path(name).suffix.lower()
            if ext not in IMAGE_EXT and ext not in VIDEO_EXT:
                continue
            path = folder / name
            try:
                stat = path.stat()
            except OSError:
                continue
            taken = datetime.fromtimestamp(stat.st_mtime)
            date = ""
            if year.isdigit() and month != "Unknown" and taken.year == int(year):
                date = taken.strftime("%Y-%m-%d")
            found.append({
                "rel": str(path.relative_to(PHOTOS)),
                "name": name,
                "ext": ext,
                "kind": kind_for(ext),
                "year": year,
                "month": month,
                "date": date,
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            })

    found.sort(key=lambda item: item["mtime"], reverse=True)
    buckets = {}
    for photo in found:
        buckets.setdefault((photo["year"], photo["month"]), []).append(photo)

    keys = sorted(
        buckets,
        key=lambda pair: (year_sort_value(pair[0]), month_sort_value(pair[1])),
        reverse=True,
    )
    groups = []
    by_id = {}
    next_id = 1
    for year, month in keys:
        items = []
        for photo in buckets[(year, month)]:
            photo["id"] = next_id
            by_id[next_id] = photo
            items.append([next_id, photo["name"], photo["kind"], photo["date"]])
            next_id += 1
        groups.append({
            "year": year,
            "month": month,
            "label": label_for(year, month),
            "items": items,
        })
    LIBRARY["groups"] = groups
    LIBRARY["by_id"] = by_id
    LIBRARY["count"] = len(by_id)
    LIBRARY["ready"] = True
    print(f"Indexed {LIBRARY['count']} files in {len(groups)} months.", flush=True)


def thumb_path(photo):
    return CACHE / f"{photo['id']}.jpg"


def view_path(photo):
    return VIEWS / f"{photo['id']}.jpg"


def run_thumb(src, dest, kind):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".tmp.jpg")
    tmp.unlink(missing_ok=True)
    if kind == "video":
        commands = [
            [
                "ffmpeg", "-y", "-ss", "0", "-i", str(src), "-map", "0:v:0",
                "-frames:v", "1", "-vf", "scale=480:-2", str(tmp),
            ],
            [
                "ffmpeg", "-y", "-ss", "0", "-i", str(src),
                "-frames:v", "1", "-vf", "scale=480:-2", str(tmp),
            ],
        ]
        for cmd in commands:
            subprocess.run(cmd, capture_output=True)
            if tmp.exists() and tmp.stat().st_size > 0:
                break
    else:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", "-Z", "480", "--out", str(tmp), str(src)],
            capture_output=True,
        )
    if tmp.exists() and tmp.stat().st_size > 0:
        os.replace(tmp, dest)
        return True
    tmp.unlink(missing_ok=True)
    return False


def client_gone(conn):
    """True when the browser already dropped this connection."""
    if conn is None:
        return True
    try:
        conn.setblocking(False)
        try:
            data = conn.recv(1, socket.MSG_PEEK)
        finally:
            conn.setblocking(True)
    except BlockingIOError:
        return False
    except OSError:
        return True
    return data == b""


def ensure_jpeg(photo, dest, size, still=None):
    def wanted():
        return True if still is None else bool(still())

    if dest.exists() and dest.stat().st_size > 0:
        return dest
    if not wanted():
        return None
    src = PHOTOS / photo["rel"]
    with lock_for((dest.parent.name, photo["id"])):
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        if not wanted():
            return None
        with SEM:
            if dest.exists() and dest.stat().st_size > 0:
                return dest
            if not wanted():
                return None
            if photo["kind"] == "video" and size == 480:
                ok = run_thumb(src, dest, "video")
            elif photo["kind"] == "video":
                ok = False
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.stem + ".tmp.jpg")
                subprocess.run(
                    ["sips", "-s", "format", "jpeg", "-Z", str(size), "--out", str(tmp), str(src)],
                    capture_output=True,
                )
                ok = tmp.exists() and tmp.stat().st_size > 0
                if ok:
                    os.replace(tmp, dest)
                else:
                    tmp.unlink(missing_ok=True)
        return dest if ok else None


def people_payload():
    if not faces_db.DB_PATH.exists():
        return {"ready": False, "people": [], "scanned": 0}
    rel_to_photo = {photo["rel"]: photo for photo in LIBRARY["by_id"].values()}
    conn = faces_db.connect()
    scanned_row = conn.execute("SELECT value FROM meta WHERE key = 'scanned'").fetchone()
    total_row = conn.execute("SELECT value FROM meta WHERE key = 'total'").fetchone()
    qualified = conn.execute(
        """
        SELECT p.id, p.name, p.cover_face_id, COUNT(DISTINCT f.relpath) AS n
        FROM people p
        JOIN faces f ON f.person_id = p.id
        GROUP BY p.id
        HAVING n >= 10
        ORDER BY n DESC
        """
    ).fetchall()
    people = [
        person_record(conn, person_id, name, cover_id, count, rel_to_photo)
        for person_id, name, cover_id, count in qualified
    ]
    conn.close()
    return {
        "ready": True,
        "scanned": int(scanned_row[0]) if scanned_row else 0,
        "total": int(total_row[0]) if total_row else 0,
        "people": people,
    }


def person_record(conn, person_id, name, cover_id, count, rel_to_photo):
    rows = conn.execute(
        """
        SELECT relpath FROM faces
        WHERE person_id = ?
        ORDER BY score DESC
        """,
        (person_id,),
    ).fetchall()
    ids = []
    photos = []
    seen = set()
    for (relpath,) in rows:
        if relpath in seen:
            continue
        seen.add(relpath)
        photo = rel_to_photo.get(relpath)
        if photo is None:
            continue
        ids.append(photo["id"])
        if len(photos) < 8:
            photos.append({
                "id": photo["id"],
                "name": Path(relpath).name,
                "kind": photo["kind"],
            })
    return {
        "id": person_id,
        "name": name,
        "count": len(ids) or count,
        "cover": f"/face-crop/{cover_id}" if cover_id else "",
        "ids": ids,
        "photos": photos,
    }


def search_payload(query):
    people = people_payload().get("people") or []
    facts = category_facts()
    parsed = search_lib.parse_query(query, people, facts["names"])
    ids_by_person = {}
    for person in people:
        name = (person.get("name") or "").strip()
        if name:
            ids_by_person[name.casefold()] = person.get("ids") or []
    texts = captions_db.caption_map()
    captions = {}
    for photo_id, photo in LIBRARY["by_id"].items():
        text = texts.get(photo["rel"])
        if text:
            captions[photo_id] = text
    matched = search_lib.filter_groups(
        LIBRARY["groups"],
        parsed,
        captions,
        ids_by_person,
        facts["kinds"],
        facts["places"],
    )
    ids = [item[0] for group in matched for item in group["items"]]
    return {"filters": parsed, "count": len(ids), "ids": ids}


def person_detail(person_id):
    if not faces_db.DB_PATH.exists() or not LIBRARY["ready"]:
        return None
    rel_to_photo = {photo["rel"]: photo for photo in LIBRARY["by_id"].values()}
    conn = faces_db.connect()
    row = conn.execute(
        """
        SELECT p.name, p.cover_face_id, COUNT(DISTINCT f.relpath)
        FROM people p
        JOIN faces f ON f.person_id = p.id
        WHERE p.id = ?
        GROUP BY p.id
        """,
        (person_id,),
    ).fetchone()
    if row is None:
        conn.close()
        return None
    record = person_record(conn, person_id, row[0], row[1], row[2], rel_to_photo)
    conn.close()
    return record


def format_bytes(size):
    if size >= 1_000_000_000:
        return f"{size / 1_000_000_000:.1f} GB"
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f} MB"
    if size >= 1_000:
        return f"{size / 1_000:.0f} KB"
    return f"{size} B"


def number_or_none(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def trim_num(value, digits=2):
    return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")


def shutter_text(seconds):
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    if seconds >= 1:
        return f"{trim_num(seconds, 1)}s"
    return f"1/{max(1, round(1 / seconds))}"


def local_when(moment, assume_utc=True):
    if moment is None:
        return "", ""
    if isinstance(moment, str):
        text = moment.strip()
        for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                moment = datetime.strptime(text[:19], fmt)
                break
            except ValueError:
                continue
        else:
            return "", ""
        assume_utc = False
    if moment.tzinfo is None:
        if assume_utc:
            moment = moment.replace(tzinfo=timezone.utc)
        else:
            moment = moment.replace(tzinfo=datetime.now().astimezone().tzinfo)
    local = moment.astimezone()
    offset = local.strftime("%z")
    zone = f"GMT{offset[:3]}:{offset[3:]}" if len(offset) == 5 else (local.tzname() or "")
    headline = local.strftime("%b %-d")
    if local.year != datetime.now().astimezone().year:
        headline = f"{headline}, {local.year}"
    when = f"{local.strftime('%a')}, {local.strftime('%-I:%M %p')} {zone}".strip()
    return headline, when


def spotlight(path):
    proc = subprocess.run(
        ["mdls", "-plist", "-", str(path)],
        capture_output=True,
        timeout=8,
    )
    if proc.returncode != 0 or not proc.stdout:
        return {}
    try:
        data = plistlib.loads(proc.stdout)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def sips_meta(path):
    proc = subprocess.run(
        ["sips", "-g", "all", str(path)],
        capture_output=True,
        text=True,
        timeout=8,
    )
    meta = {}
    for line in proc.stdout.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.strip().partition(":")
        meta[key.strip()] = value.strip()
    return meta


def parse_iso6709(value):
    match = re.match(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)", value or "")
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def video_probe(path):
    proc = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True,
        timeout=12,
    )
    if proc.returncode != 0 or not proc.stdout:
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def ultra_hdr(path):
    if path.suffix.lower() not in {".jpg", ".jpeg"}:
        return False
    try:
        with path.open("rb") as handle:
            return b"hdrgm" in handle.read(131072)
    except OSError:
        return False


def place_label(address):
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("hamlet")
        or address.get("county")
        or ""
    )
    for prefix in ("City of ", "Town of ", "Village of "):
        city = city.removeprefix(prefix)
    city = city.strip()
    state = address.get("state") or ""
    if address.get("country_code") == "us":
        state = US_STATES.get(state, state)
    if city and state:
        return f"{city}, {state}"
    return city or state


def place_name(lat, lon):
    key = f"{lat:.3f},{lon:.3f}"
    with PLACE_LOCK:
        try:
            cache = json.loads(PLACE_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            cache = {}
        if key in cache:
            return cache[key]
    label = ""
    try:
        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?format=jsonv2&lat={lat}&lon={lon}&zoom=12"
        )
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Keeps/1.0 (personal photo library)"},
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode())
        label = place_label(payload.get("address") or {})
    except Exception:
        label = ""
    if not label:
        return ""
    with PLACE_LOCK:
        try:
            cache = json.loads(PLACE_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            cache = {}
        cache[key] = label
        PLACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLACE_PATH.write_text(json.dumps(cache))
    return label


def people_in(relpath):
    if not faces_db.DB_PATH.exists():
        return []
    conn = faces_db.connect()
    rows = conn.execute(
        """
        SELECT f.id, f.person_id, p.name, f.score
        FROM faces f
        JOIN people p ON p.id = f.person_id
        WHERE f.relpath = ?
        ORDER BY f.score DESC
        """,
        (relpath,),
    ).fetchall()
    conn.close()
    seen = set()
    people = []
    for face_id, person_id, name, _score in rows:
        if person_id in seen:
            continue
        seen.add(person_id)
        people.append({
            "id": person_id,
            "face_id": face_id,
            "name": name.strip(),
        })
    return people


def photo_info(photo):
    src = PHOTOS / photo["rel"]
    info = {
        "name": photo["name"],
        "folder": str(Path(photo["rel"]).parent),
        "kind": photo["kind"],
        "size": format_bytes(photo["size"]),
        "people": people_in(photo["rel"]),
    }
    meta = {}
    try:
        meta = spotlight(src)
    except Exception:
        meta = {}
    width = meta.get("kMDItemPixelWidth")
    height = meta.get("kMDItemPixelHeight")
    taken = meta.get("kMDItemContentCreationDate")
    make = meta.get("kMDItemAcquisitionMake") or ""
    model = meta.get("kMDItemAcquisitionModel") or ""
    fnumber = meta.get("kMDItemFNumber")
    shutter = meta.get("kMDItemExposureTimeSeconds")
    focal = meta.get("kMDItemFocalLength")
    focal35 = meta.get("kMDItemFocalLength35mm")
    iso = meta.get("kMDItemISOSpeed")
    lat = meta.get("kMDItemLatitude")
    lon = meta.get("kMDItemLongitude")
    altitude = meta.get("kMDItemAltitude")
    software = meta.get("kMDItemCreator") or ""
    description = meta.get("kMDItemDescription") or ""
    if isinstance(description, str) and description.strip() in {"", "(null)"}:
        description = ""
    duration = meta.get("kMDItemDurationSeconds")
    codecs = meta.get("kMDItemCodecs") or []
    if not width or not model or taken is None:
        try:
            basic = sips_meta(src)
        except Exception:
            basic = {}
        width = width or number_or_none(basic.get("pixelWidth"))
        height = height or number_or_none(basic.get("pixelHeight"))
        make = make or basic.get("make") or ""
        model = model or basic.get("model") or ""
        software = software or basic.get("software") or ""
        if taken is None and basic.get("creation"):
            taken = basic["creation"]
    if photo["kind"] == "video":
        try:
            probe = video_probe(src)
        except Exception:
            probe = {}
        tags = (probe.get("format") or {}).get("tags") or {}
        if not model:
            make = make or tags.get("com.android.manufacturer") or tags.get("com.apple.quicktime.make") or ""
            model = tags.get("com.android.model") or tags.get("com.apple.quicktime.model") or ""
        if lat is None or lon is None:
            lat, lon = parse_iso6709(tags.get("location") or tags.get("location-eng") or "")
    if make and model and make.lower() not in model.lower():
        info["camera"] = f"{make} {model}".strip()
    elif model or make:
        info["camera"] = (model or make).strip()
    bits = []
    if fnumber:
        bits.append(f"f/{trim_num(fnumber)}")
    shutter_label = shutter_text(shutter)
    if shutter_label:
        bits.append(shutter_label)
    if focal:
        lens = f"{trim_num(focal)}mm"
        if focal35 and abs(float(focal35) - float(focal)) > 1:
            lens = f"{lens} ({trim_num(focal35, 0)}mm)"
        bits.append(lens)
    if iso:
        bits.append(f"ISO{int(float(iso))}")
    if bits:
        info["exposure"] = "  ".join(bits)
    if width and height:
        pixels = int(width) * int(height)
        info["pixels"] = f"{pixels / 1_000_000:.1f}MP"
        info["dimensions"] = f"{int(width)} × {int(height)}"
    headline, when = local_when(taken)
    if not headline:
        headline, when = local_when(datetime.fromtimestamp(photo["mtime"], timezone.utc))
    if headline:
        info["date"] = headline
        info["when"] = when
    caption = captions_db.one(photo["rel"])
    if caption:
        info["description"] = caption
    elif description:
        info["description"] = description.strip()
    if software and not str(software).endswith("fps"):
        info["software"] = str(software)
    if isinstance(altitude, (int, float)):
        info["altitude"] = f"{round(altitude)} m"
    if duration:
        total = int(round(float(duration)))
        info["duration"] = f"{total // 60}:{total % 60:02d}"
    if isinstance(codecs, list) and codecs:
        info["codecs"] = ", ".join(str(item) for item in codecs)
    if ultra_hdr(src):
        info["hdr"] = "Ultra HDR"
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        info["latitude"] = round(float(lat), 6)
        info["longitude"] = round(float(lon), 6)
        info["place"] = place_name(float(lat), float(lon))
    return info


def ensure_face_box(face_id):
    dest = FACE_BOXES / f"{face_id}.jpg"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    with lock_for(("facebox", face_id)):
        if dest.is_file() and dest.stat().st_size > 0:
            return dest
        if not faces_db.DB_PATH.exists():
            return None
        conn = faces_db.connect()
        row = conn.execute(
            "SELECT relpath, x1, y1, x2, y2 FROM faces WHERE id = ?",
            (face_id,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        src = PHOTOS / row[0]
        if not src.is_file():
            return None
        proc = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(src)],
            capture_output=True,
            text=True,
            timeout=8,
        )
        size = {}
        for line in proc.stdout.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.strip().partition(":")
            size[key.strip()] = value.strip()
        try:
            width = int(float(size["pixelWidth"]))
            height = int(float(size["pixelHeight"]))
        except (KeyError, ValueError):
            return None
        x1, y1, x2, y2 = row[1:]
        box_w = max(1.0, (x2 - x1) * width)
        box_h = max(1.0, (y2 - y1) * height)
        side = min(width, height, max(box_w, box_h) * 1.8)
        side = max(32.0, side)
        center_x = (x1 + x2) / 2 * width
        center_y = (y1 + y2) / 2 * height
        left = int(max(0, min(width - side, center_x - side / 2)))
        top = int(max(0, min(height - side, center_y - side / 2)))
        side = int(side)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.stem + ".tmp.jpg")
        tmp.unlink(missing_ok=True)
        subprocess.run(
            [
                "sips", "--cropOffset", str(top), str(left),
                "-c", str(side), str(side),
                "-s", "format", "jpeg",
                "--out", str(tmp), str(src),
            ],
            capture_output=True,
            timeout=15,
        )
        if tmp.exists() and tmp.stat().st_size > 0:
            os.replace(tmp, dest)
            return dest
        tmp.unlink(missing_ok=True)
        return None


def ensure_geo():
    global _geo_started
    with GEO_LOCK:
        if _geo_started:
            return
        _geo_started = True
        _load_geo()
    threading.Thread(target=scan_geo, name="geo", daemon=True).start()


def _load_geo():
    try:
        saved = json.loads(GEO_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return
    by_rel = {}
    for rel, point in (saved.get("by_rel") or {}).items():
        if isinstance(point, list) and len(point) == 2:
            by_rel[str(rel)] = [float(point[0]), float(point[1])]
    GEO["by_rel"] = by_rel
    GEO["scanned"] = len(by_rel)
    GEO["done"] = False


def _save_geo():
    payload = {
        "by_rel": GEO["by_rel"],
        "scanned": GEO["scanned"],
        "total": GEO["total"],
        "done": GEO["done"],
    }
    GEO_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = GEO_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    os.replace(tmp, GEO_PATH)


def scan_geo():
    try:
        listed = subprocess.run(
            ["mdfind", "-onlyin", str(PHOTOS), "kMDItemLatitude >= -90"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        with GEO_LOCK:
            GEO["done"] = True
        return
    paths = []
    for line in listed.stdout.splitlines():
        path = Path(line.strip())
        if path.suffix.lower() in VIDEO_EXT:
            continue
        try:
            rel = str(path.relative_to(PHOTOS))
        except ValueError:
            continue
        paths.append((rel, path))
    with GEO_LOCK:
        known = set(GEO["by_rel"])
        GEO["total"] = len(paths)
    missing = [(rel, path) for rel, path in paths if rel not in known]
    for start in range(0, len(missing), 80):
        chunk = missing[start:start + 80]
        try:
            listed = subprocess.run(
                [
                    "mdls", "-name", "kMDItemLatitude", "-name", "kMDItemLongitude",
                    *[str(path) for _, path in chunk],
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            pairs = categories.parse_mdls(listed.stdout)
        except (OSError, subprocess.TimeoutExpired):
            pairs = []
        if len(pairs) != len(chunk):
            continue
        with GEO_LOCK:
            for (rel, _path), pair in zip(chunk, pairs):
                if pair[0] is None or pair[1] is None:
                    continue
                GEO["by_rel"][rel] = [pair[0], pair[1]]
            GEO["scanned"] = len(GEO["by_rel"])
            _save_geo()
    with GEO_LOCK:
        GEO["done"] = True
        GEO["scanned"] = len(GEO["by_rel"])
        _save_geo()


def saved_place_names():
    with PLACE_LOCK:
        try:
            data = json.loads(PLACE_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
    if not isinstance(data, dict):
        return {}
    return data


def category_facts():
    ensure_geo()
    texts = captions_db.caption_map() if captions_db.DB_PATH.exists() else {}
    names = saved_place_names()
    with GEO_LOCK:
        points = dict(GEO["by_rel"])
        geo = {
            "done": GEO["done"],
            "scanned": GEO["scanned"],
            "total": GEO["total"],
        }
    kinds = {}
    places = {}
    shots = []
    docs = []
    animals = []
    food = []
    nature = []
    vehicles = []
    spots = []
    for photo in LIBRARY["by_id"].values():
        if photo["kind"] == "video":
            continue
        caption = texts.get(photo["rel"]) or ""
        found = categories.kinds_for(photo["name"], caption)
        if found:
            kinds[photo["id"]] = found
        if "screenshot" in found:
            shots.append(photo["id"])
        if "document" in found:
            docs.append(photo["id"])
        if "animal" in found:
            animals.append(photo["id"])
        if "food" in found:
            food.append(photo["id"])
        if "nature" in found:
            nature.append(photo["id"])
        if "vehicle" in found:
            vehicles.append(photo["id"])
        point = points.get(photo["rel"])
        if not point:
            continue
        label = categories.place_label(point[0], point[1], names)
        places[photo["id"]] = label
        spots.append((point[0], point[1], label))
    labels = []
    seen = set()
    for label in places.values():
        for name in categories.search_names(label):
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            labels.append(name)
    labels.sort(key=len, reverse=True)
    return {
        "kinds": kinds,
        "places": places,
        "screenshots": shots,
        "documents": docs,
        "animals": animals,
        "food": food,
        "nature": nature,
        "vehicles": vehicles,
        "spots": spots,
        "names": labels,
        "geo": geo,
    }


def category_payload():
    facts = category_facts()
    groups = {}
    for photo_id, label in facts["places"].items():
        groups.setdefault(label, []).append(photo_id)
    cards = []
    for label, ids in groups.items():
        cards.append({"label": label, "count": len(ids), "cover": ids[0]})
    cards.sort(key=lambda card: (
        0 if categories.search_names(card["label"]) else 1,
        -card["count"],
        card["label"],
    ))
    return {
        "screenshots": _kind_card(facts["screenshots"]),
        "documents": _kind_card(facts["documents"]),
        "animals": _kind_card(facts["animals"]),
        "food": _kind_card(facts["food"]),
        "nature": _kind_card(facts["nature"]),
        "vehicles": _kind_card(facts["vehicles"]),
        "map": categories.map_points(facts["spots"]),
        "places": cards,
        "names": facts["names"],
        "index": {
            "kinds": {str(photo_id): found for photo_id, found in facts["kinds"].items()},
            "places": {str(photo_id): label for photo_id, label in facts["places"].items()},
        },
        "geo": facts["geo"],
    }


def _kind_card(ids):
    return {"count": len(ids), "cover": ids[0] if ids else None}


DISPOSE_SCRIPT = "index_dispose.py"


def named_face_paths():
    if not faces_db.DB_PATH.exists():
        return set()
    conn = faces_db.connect()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT f.relpath
            FROM faces f
            JOIN people p ON p.id = f.person_id
            WHERE trim(p.name) != ''
            """
        )
        return {row[0] for row in rows}
    finally:
        conn.close()


def dispose_running():
    row = jobs_db.read("dispose")
    return script_running(DISPOSE_SCRIPT) or (
        row["state"] == "running" and jobs_db.pid_alive(row["pid"])
    )


def start_dispose():
    if dispose_running():
        return "running"
    if not VENV_PYTHON.is_file():
        return "no-indexer"
    subprocess.Popen(
        [str(VENV_PYTHON), "-u", str(APP / DISPOSE_SCRIPT)],
        cwd=str(APP),
        start_new_session=True,
    )
    return "started"


def review_payload(level):
    if level not in dispose_lib.LEVELS:
        level = "normal"
    texts = captions_db.caption_map() if captions_db.DB_PATH.exists() else {}
    scores = dispose_db.score_map()
    named = named_face_paths()
    faced = set()
    if faces_db.DB_PATH.exists():
        conn = faces_db.connect()
        try:
            faced = {row[0] for row in conn.execute("SELECT DISTINCT relpath FROM faces")}
        finally:
            conn.close()
    waiting = 0
    kept = 0
    items = []
    for photo in LIBRARY["by_id"].values():
        if photo["kind"] == "video":
            continue
        row = scores.get(photo["rel"])
        if row is None:
            waiting += 1
            continue
        sharp, spread, _mtime = row
        caption = texts.get(photo["rel"]) or ""
        caption_reason = candidates.reason_for(photo["name"], caption, photo["rel"] in faced)
        power = dispose_lib.strength_for(sharp, spread)
        if not dispose_lib.visible(level, power, photo["rel"] in named, bool(caption_reason)):
            kept += 1
            continue
        items.append({
            "id": photo["id"],
            "reason": dispose_lib.reason_for(sharp, spread, caption_reason),
            "strength": power,
        })
    items.sort(key=lambda item: (-item["strength"], item["id"]))
    shown = len(items)
    row = jobs_db.read("dispose")
    return {
        "level": level,
        "running": dispose_running(),
        "note": row["note"],
        "scanned": len(scores),
        "waiting": waiting,
        "shown": shown,
        "kept": kept,
        "items": items[:400],
    }


def candidate_payload():
    texts = captions_db.caption_map() if captions_db.DB_PATH.exists() else {}
    faced = set()
    if faces_db.DB_PATH.exists():
        conn = faces_db.connect()
        try:
            faced = {row[0] for row in conn.execute("SELECT DISTINCT relpath FROM faces")}
        finally:
            conn.close()
    items = []
    for photo in LIBRARY["by_id"].values():
        if photo["kind"] == "video":
            continue
        caption = texts.get(photo["rel"]) or ""
        if not caption:
            continue
        reason = candidates.reason_for(photo["name"], caption, photo["rel"] in faced)
        if not reason:
            continue
        items.append({
            "id": photo["id"],
            "name": photo["name"],
            "reason": reason,
            "caption": caption,
        })
    items.sort(key=lambda item: (item["reason"], item["name"]))
    return {"count": len(items), "items": items}


def remember_file(path):
    path = Path(path)
    rel = path.relative_to(PHOTOS)
    parts = rel.parts
    year = parts[0] if parts else "Unknown"
    month = parts[1] if len(parts) > 1 else "Unknown"
    stat = path.stat()
    taken = datetime.fromtimestamp(stat.st_mtime)
    date = ""
    if year.isdigit() and month != "Unknown" and taken.year == int(year):
        date = taken.strftime("%Y-%m-%d")
    photo = {
        "rel": str(rel),
        "name": path.name,
        "ext": path.suffix.lower(),
        "kind": kind_for(path.suffix.lower()),
        "year": year,
        "month": month,
        "date": date,
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "label": label_for(year, month),
    }
    with LIBRARY_LOCK:
        return library_actions.add_photo(LIBRARY, photo)


def save_edit(photo_id, mode, turns, straighten, crop):
    photo = LIBRARY["by_id"].get(int(photo_id))
    if photo is None or photo["kind"] == "video":
        raise LookupError(photo_id)
    src = library_actions.photo_file(PHOTOS, photo["rel"])
    if mode == "replace":
        tmp = src.with_name("." + src.name + ".editing")
        try:
            edits.render_edit(src, tmp, turns, straighten, crop)
            os.replace(tmp, src)
        finally:
            tmp.unlink(missing_ok=True)
        stat = src.stat()
        with LIBRARY_LOCK:
            photo["size"] = stat.st_size
            photo["mtime"] = stat.st_mtime
        for path in (thumb_path(photo), view_path(photo)):
            path.unlink(missing_ok=True)
        return {"ok": True, "replaced": True, "id": photo["id"], "name": photo["name"]}
    dest = src.parent / edits.copy_name(src.parent, src.name)
    edits.render_edit(src, dest, turns, straighten, crop)
    stored = remember_file(dest)
    return {
        "ok": True,
        "replaced": False,
        "id": stored["id"],
        "name": stored["name"],
        "item": [stored["id"], stored["name"], stored["kind"], stored["date"]],
        "year": stored["year"],
        "month": stored["month"],
        "label": label_for(stored["year"], stored["month"]),
    }


def add_manual_face(photo_id, box, name):
    photo = LIBRARY["by_id"].get(int(photo_id))
    if photo is None or photo["kind"] == "video":
        raise LookupError(photo_id)
    x1 = float(box["x"])
    y1 = float(box["y"])
    x2 = x1 + float(box["w"])
    y2 = y1 + float(box["h"])
    record = faces_db.add_face(photo["rel"], (x1, y1, x2, y2), name)
    crop = ensure_face_box(record["face_id"])
    if crop is not None:
        FACE_CROPS.mkdir(parents=True, exist_ok=True)
        target = FACE_CROPS / f"{record['face_id']}.jpg"
        if not target.is_file():
            shutil.copyfile(crop, target)
    return record


def delete_ids(raw_ids):
    with LIBRARY_LOCK:
        chosen = []
        seen = set()
        for value in raw_ids:
            try:
                photo_id = int(value)
            except (TypeError, ValueError):
                continue
            if photo_id in seen:
                continue
            seen.add(photo_id)
            photo = LIBRARY["by_id"].get(photo_id)
            if photo is not None:
                chosen.append(photo)
        existing = []
        missing = []
        for photo in chosen:
            try:
                existing.append((photo, library_actions.photo_file(PHOTOS, photo["rel"])))
            except FileNotFoundError:
                missing.append(photo)
        if existing:
            library_actions.move_to_trash([path for _, path in existing])
        removed = library_actions.drop_photos(
            LIBRARY,
            [photo["id"] for photo, _ in existing] + [photo["id"] for photo in missing],
        )
        for photo in removed:
            for path in (thumb_path(photo), view_path(photo)):
                path.unlink(missing_ok=True)
        return [photo["id"] for photo in removed]


def read_carto_key(path=None):
    key_path = CARTO_KEY_PATH if path is None else path
    if not key_path.is_file():
        return ""
    return key_path.read_text(encoding="utf-8").strip()


def categories_page(path=None, key_path=None):
    page = CATEGORIES_PAGE if path is None else path
    html = page.read_text(encoding="utf-8")
    return html.replace(CARTO_KEY_MARK, read_carto_key(key_path)).encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        try:
            self.route()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            print(f"ERROR {self.path}: {exc}", flush=True)
            self.respond(500, b"error", "text/plain")

    def do_POST(self):
        try:
            self.route_post()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            print(f"ERROR POST {self.path}: {exc}", flush=True)
            self.respond(500, b"error", "text/plain")

    def route(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html", "/videos"):
            data = PAGE.read_bytes()
            self.respond(200, data, "text/html; charset=utf-8")
            return
        if path == "/faces":
            self.respond(200, FACES_PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/settings":
            self.respond(200, SETTINGS_PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/review":
            self.respond(200, REVIEW_PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/categories":
            self.respond(200, categories_page(), "text/html; charset=utf-8")
            return
        if path == "/api/categories":
            if not LIBRARY["ready"]:
                self.respond(503, b'{"ready":false}', "application/json")
                return
            body = json.dumps(category_payload()).encode()
            self.respond(200, body, "application/json")
            return
        if path == "/api/review":
            if not LIBRARY["ready"]:
                self.respond(503, b'{"ready":false}', "application/json")
                return
            params = parse_qs(urlparse(self.path).query)
            level = (params.get("level") or ["normal"])[0]
            body = json.dumps(review_payload(level)).encode()
            self.respond(200, body, "application/json")
            return
        if path == "/api/candidates":
            if not LIBRARY["ready"]:
                self.respond(503, b'{"ready":false}', "application/json")
                return
            body = json.dumps(candidate_payload()).encode()
            self.respond(200, body, "application/json")
            return
        if path == "/api/models":
            body = json.dumps({"roles": model_choices.view()}).encode()
            self.respond(200, body, "application/json")
            return
        if path == "/api/sync":
            if not LIBRARY["ready"]:
                self.respond(503, b'{"ready":false}', "application/json")
                return
            body = json.dumps(sync_payload()).encode()
            self.respond(200, body, "application/json")
            return
        if path == "/api/people":
            body = json.dumps(people_payload()).encode()
            self.respond(200, body, "application/json")
            return
        if path.startswith("/api/people/"):
            token = path.rstrip("/").split("/")[-1]
            if not token.isdigit():
                self.respond(404, b"not found", "text/plain")
                return
            record = person_detail(int(token))
            if record is None:
                self.respond(404, b"not found", "text/plain")
                return
            self.respond(200, json.dumps(record).encode(), "application/json")
            return
        if path.startswith("/face-crop/"):
            token = path[11:].split(".", 1)[0]
            crop = FACE_CROPS / f"{token}.jpg"
            if not token.isdigit() or not crop.is_file():
                self.respond(404, b"not found", "text/plain")
                return
            self.serve_path(crop, "image/jpeg", cache="private, max-age=3600")
            return
        if path.startswith("/api/info/"):
            photo = self.photo_from_token(path[len("/api/info/"):])
            if photo is None:
                self.respond(404, b"not found", "text/plain")
                return
            body = json.dumps(photo_info(photo)).encode()
            self.respond(200, body, "application/json")
            return
        if path.startswith("/face-box/"):
            token = path[len("/face-box/"):].split(".", 1)[0]
            if not token.isdigit():
                self.respond(404, b"not found", "text/plain")
                return
            crop = ensure_face_box(int(token))
            if crop is None:
                self.respond(404, b"not found", "text/plain")
                return
            self.serve_path(crop, "image/jpeg", cache="private, max-age=86400")
            return
        if path == "/api/search":
            if not LIBRARY["ready"]:
                self.respond(503, b'{"ready":false}', "application/json")
                return
            params = parse_qs(urlparse(self.path).query)
            query = (params.get("q") or [""])[0]
            body = json.dumps(search_payload(query)).encode()
            self.respond(200, body, "application/json")
            return
        if path == "/api/captions":
            if not LIBRARY["ready"]:
                self.respond(503, b'{"ready":false}', "application/json")
                return
            texts = captions_db.caption_map()
            by_id = {}
            for photo_id, photo in LIBRARY["by_id"].items():
                text = texts.get(photo["rel"])
                if text:
                    by_id[str(photo_id)] = text
            body = json.dumps({"count": len(by_id), "by_id": by_id}, separators=(",", ":")).encode()
            self.respond(200, body, "application/json")
            return
        if path == "/api/library":
            if not LIBRARY["ready"]:
                self.respond(503, b'{"ready":false}', "application/json")
                return
            payload = {
                "count": LIBRARY["count"],
                "groups": LIBRARY["groups"],
            }
            body = json.dumps(payload, separators=(",", ":")).encode()
            self.respond(200, body, "application/json")
            return
        if path.startswith("/thumb/"):
            self.serve_derived(path[7:], thumb_path, 480, "thumb")
            return
        if path.startswith("/view/"):
            self.serve_derived(path[6:], view_path, 2000, "view")
            return
        if path.startswith("/media/"):
            self.serve_original(path[7:])
            return
        if path.startswith("/vendor/"):
            self.serve_vendor(path[len("/vendor/"):])
            return
        self.respond(404, b"not found", "text/plain")

    def route_post(self):
        path = urlparse(self.path).path
        if path == "/api/models":
            self.save_model_choices()
            return
        if path == "/api/sync":
            self.control_sync_request()
            return
        if path == "/api/delete":
            self.delete_selected()
            return
        if path == "/api/edit":
            self.save_photo_edit()
            return
        if path == "/api/faces":
            self.save_manual_face()
            return
        if path == "/api/review/start":
            status = start_dispose()
            if status == "no-indexer":
                self.respond(400, b'{"ok":false}', "application/json")
                return
            self.respond(200, json.dumps({"ok": True, "status": status}).encode(), "application/json")
            return
        if not path.startswith("/api/people/"):
            self.respond(404, b"not found", "text/plain")
            return
        token = path.rstrip("/").split("/")[-1]
        if not token.isdigit():
            self.respond(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        name = str(payload.get("name", "")).strip()[:80]
        merged_into = faces_db.set_name(int(token), name)
        body = json.dumps({
            "ok": True,
            "name": name,
            "merged_into": merged_into,
        }).encode()
        self.respond(200, body, "application/json")

    def json_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 100000:
            return None
        return json.loads(self.rfile.read(length) or b"{}")

    def control_sync_request(self):
        payload = self.json_body()
        if payload is None:
            self.respond(413, b"too large", "text/plain")
            return
        try:
            control_sync(payload.get("job"), payload.get("action"))
        except ValueError:
            self.respond(400, b'{"ok":false}', "application/json")
            return
        except RuntimeError:
            body = json.dumps({"ok": False, **sync_payload()}).encode()
            self.respond(409, body, "application/json")
            return
        body = json.dumps({"ok": True, **sync_payload()}).encode()
        self.respond(200, body, "application/json")

    def save_model_choices(self):
        payload = self.json_body()
        if payload is None:
            self.respond(413, b"too large", "text/plain")
            return
        choices = payload.get("choices")
        try:
            roles = model_choices.save_choices(choices)
        except ValueError:
            self.respond(400, b'{"ok":false}', "application/json")
            return
        body = json.dumps({"ok": True, "roles": roles}).encode()
        self.respond(200, body, "application/json")

    def save_photo_edit(self):
        payload = self.json_body()
        if payload is None:
            self.respond(413, b"too large", "text/plain")
            return
        mode = payload.get("mode")
        if mode not in ("copy", "replace"):
            self.respond(400, b"bad edit", "text/plain")
            return
        crop = payload.get("crop")
        if crop is not None and not isinstance(crop, dict):
            self.respond(400, b"bad edit", "text/plain")
            return
        try:
            result = save_edit(
                payload.get("id"),
                mode,
                payload.get("turns") or 0,
                payload.get("straighten") or 0,
                crop,
            )
        except (LookupError, ValueError, FileNotFoundError, OSError, TypeError):
            self.respond(400, b"bad edit", "text/plain")
            return
        except RuntimeError:
            self.respond(500, b"edit failed", "text/plain")
            return
        self.respond(200, json.dumps(result).encode(), "application/json")

    def save_manual_face(self):
        payload = self.json_body()
        if payload is None:
            self.respond(413, b"too large", "text/plain")
            return
        box = payload.get("box")
        if not isinstance(box, dict):
            self.respond(400, b"bad face", "text/plain")
            return
        try:
            record = add_manual_face(payload.get("id"), box, payload.get("name") or "")
        except (LookupError, ValueError, FileNotFoundError, TypeError):
            self.respond(400, b"bad face", "text/plain")
            return
        body = json.dumps({"ok": True, **record}).encode()
        self.respond(200, body, "application/json")

    def delete_selected(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 100000:
            self.respond(413, b"too large", "text/plain")
            return
        payload = json.loads(self.rfile.read(length) or b"{}")
        raw_ids = payload.get("ids") or []
        if not isinstance(raw_ids, list) or len(raw_ids) > 200:
            self.respond(400, b"bad ids", "text/plain")
            return
        removed = delete_ids(raw_ids)
        body = json.dumps({"ok": True, "removed": removed}).encode()
        self.respond(200, body, "application/json")

    def photo_from_token(self, token):
        token = token.split(".", 1)[0]
        if not token.isdigit():
            return None
        return LIBRARY["by_id"].get(int(token))

    def serve_vendor(self, rel):
        if not rel or rel.startswith("/") or ".." in rel.split("/"):
            self.respond(404, b"not found", "text/plain")
            return
        root = (APP / "static" / "vendor").resolve()
        file = (root / rel).resolve()
        if root not in file.parents or not file.is_file():
            self.respond(404, b"not found", "text/plain")
            return
        ctype = mimetypes.types_map.get(file.suffix.lower(), "application/octet-stream")
        if file.suffix == ".js":
            ctype = "text/javascript"
        self.serve_path(file, ctype, cache="private, max-age=86400")

    def serve_derived(self, token, path_fn, size, cache_name):
        photo = self.photo_from_token(token)
        if photo is None:
            self.respond(404, b"not found", "text/plain")
            return
        if cache_name == "view" and photo["kind"] == "video":
            self.serve_original(token)
            return
        if cache_name == "view" and photo["kind"] == "image":
            self.serve_original(token)
            return
        dest = path_fn(photo)
        ready = ensure_jpeg(photo, dest, size, still=lambda: not client_gone(self.connection))
        if ready is None:
            if client_gone(self.connection):
                return
            self.respond(404, b"preview unavailable", "text/plain")
            return
        self.serve_path(ready, "image/jpeg", cache="private, max-age=2592000")

    def serve_original(self, token):
        photo = self.photo_from_token(token)
        if photo is None:
            self.respond(404, b"not found", "text/plain")
            return
        src = PHOTOS / photo["rel"]
        if not src.is_file():
            self.respond(404, b"missing", "text/plain")
            return
        ctype = mimetypes.types_map.get(photo["ext"], "application/octet-stream")
        if photo["ext"] == ".heic":
            ctype = "image/heic"
        if photo["ext"] == ".mov":
            ctype = "video/quicktime"
        self.serve_path(src, ctype, cache="private, max-age=86400")

    def serve_path(self, path, content_type, cache):
        size = path.stat().st_size
        start, end = 0, size - 1
        status = 200
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            spec = range_header.split("=", 1)[1].split(",")[0].strip()
            left, _, right = spec.partition("-")
            if left == "":
                start = max(0, size - int(right or "0"))
            else:
                start = int(left)
                end = int(right) if right else size - 1
            end = min(end, size - 1)
            if start >= size or start > end:
                body = b""
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def still_photos():
    return [photo for photo in LIBRARY["by_id"].values() if photo["kind"] != "video"]


def same_time(left, right):
    try:
        return abs(float(left) - float(right)) < 0.001
    except (TypeError, ValueError):
        return False


def job_counts(name):
    photos = still_photos()
    total = len(photos)
    if name == "faces":
        scanned = faces_db.scanned_set()
        synced = sum(1 for photo in photos if photo["rel"] in scanned)
    else:
        saved = captions_db.saved_times()
        synced = sum(
            1 for photo in photos
            if photo["rel"] in saved and same_time(saved[photo["rel"]], photo["mtime"])
        )
    return synced, max(0, total - synced), total


def script_running(script):
    result = subprocess.run(
        ["pgrep", "-fl", script],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if script in line and "server.py" not in line:
            return True
    return False


def job_view(name):
    synced, remaining, total = job_counts(name)
    row = jobs_db.read(name)
    paused = row["state"] == "paused"
    running = script_running(INDEX_JOBS[name]) or (
        row["state"] == "running" and jobs_db.pid_alive(row["pid"])
    )
    if paused and running:
        label = "Stopping"
        note = "Pause was asked. It stops after the current photo."
    elif paused:
        running = False
        label = "Paused"
        note = "Paused. Continue picks up photos that are not saved yet."
    elif remaining == 0:
        running = False
        label = "Up to date"
        note = "Saved in the database. Rewrite runs the model again."
    elif running:
        label = "In progress"
        note = row["note"] or "Working through photos that are not in the database yet."
    else:
        label = "Waiting"
        note = "New photos are waiting. Continue starts them."
    return {
        "synced": synced,
        "remaining": remaining,
        "total": total,
        "running": running,
        "paused": paused,
        "label": label,
        "note": note,
    }


def sync_payload():
    return {
        "images": len(still_photos()),
        "faces": job_view("faces"),
        "captions": job_view("captions"),
    }


def indexer_pids(script):
    result = subprocess.run(
        ["pgrep", "-fl", script],
        capture_output=True,
        text=True,
    )
    pids = []
    for line in result.stdout.splitlines():
        if script not in line or "server.py" in line or "pgrep" in line:
            continue
        token = line.split(None, 1)[0]
        if token.isdigit():
            pids.append(int(token))
    return pids


def stop_indexer(script):
    pids = indexer_pids(script)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue
    deadline = time.time() + 3
    while time.time() < deadline and script_running(script):
        time.sleep(0.1)
    if script_running(script):
        for pid in indexer_pids(script):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                continue
        time.sleep(0.2)
    return not script_running(script)


def start_indexer(name):
    script = INDEX_JOBS[name]
    if script_running(script):
        return False
    if not VENV_PYTHON.is_file():
        jobs_db.beat(name, "The indexer is not installed.", state="idle", force=True)
        return False
    subprocess.Popen(
        [str(VENV_PYTHON), "-u", script],
        cwd=str(APP),
        start_new_session=True,
    )
    jobs_db.beat(name, "Starting.", state="running", force=True)
    return True


def control_sync(name, action):
    if name not in INDEX_JOBS or action not in ("pause", "continue", "rewrite"):
        raise ValueError("bad sync")
    script = INDEX_JOBS[name]
    if action == "pause":
        jobs_db.beat(
            name,
            "Paused. Continue picks up photos that are not saved yet.",
            state="paused",
            force=True,
        )
        stop_indexer(script)
        return
    if action == "continue":
        jobs_db.beat(name, "Continuing.", state="idle", force=True)
        view = job_view(name)
        if view["remaining"] and not view["running"]:
            start_indexer(name)
        return
    if not stop_indexer(script):
        jobs_db.beat(
            name,
            "That job is still running. Pause it, then rewrite.",
            state="paused",
            force=True,
        )
        raise RuntimeError("busy")
    jobs_db.beat(name, "Clearing the saved rows.", state="idle", force=True)
    if name == "faces":
        faces_db.clear_for_rerun()
    else:
        captions_db.clear_for_rerun()
    start_indexer(name)


def resume_jobs():
    if not LIBRARY["ready"]:
        return
    for name, script in INDEX_JOBS.items():
        view = job_view(name)
        print(
            f"{name}: {view['synced']} synced, {view['remaining']} remaining, "
            f"running={view['running']} paused={view['paused']}",
            flush=True,
        )
        if view["paused"] or view["remaining"] == 0 or view["running"]:
            continue
        if start_indexer(name):
            print(f"{name}: started {script} for {view['remaining']} photos", flush=True)
        else:
            print(f"{name}: no indexer at {VENV_PYTHON}", flush=True)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    VIEWS.mkdir(parents=True, exist_ok=True)
    print("Scanning library...", flush=True)
    scan()
    resume_jobs()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Open http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
