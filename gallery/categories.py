"""Group still photos by screenshot, document, and saved location."""

import re

SCREENSHOT_RE = re.compile(r"screen\s*shot")
DOCUMENT_RE = re.compile(
    r"^(?:a )?(?:picture of a )?(?:piece of paper|sheet of paper|document|receipt|whiteboard)\b"
)
COORD_RE = re.compile(r"-?\d+\.\d+")


def kinds_for(name, caption):
    """Return screenshot, document, or both. An empty caption is not proof."""
    text = caption or ""
    if not text.strip():
        return []
    lower = text.casefold()
    label = (name or "").casefold()
    found = []
    if SCREENSHOT_RE.search(lower) or SCREENSHOT_RE.search(label):
        found.append("screenshot")
    if DOCUMENT_RE.search(lower):
        found.append("document")
    return found


def place_key(lat, lon):
    return f"{float(lat):.3f},{float(lon):.3f}"


def place_label(lat, lon, names):
    key = place_key(lat, lon)
    saved = str((names or {}).get(key) or "").strip()
    if saved:
        return saved
    return f"{float(lat):.3f}, {float(lon):.3f}"


def search_names(label):
    """Names a person can type. Coordinates are not names."""
    text = (label or "").strip()
    if not text or COORD_RE.match(text):
        return []
    names = []
    city = text.split(",")[0].strip()
    if len(city) >= 3 and not COORD_RE.fullmatch(city):
        names.append(city)
    if text.casefold() != city.casefold() and len(text) >= 3:
        names.append(text)
    return names


def place_matches(photo_label, query_place):
    photo = (photo_label or "").strip().casefold()
    query = (query_place or "").strip().casefold()
    if not query:
        return True
    if not photo:
        return False
    if photo == query or photo.startswith(query + ","):
        return True
    return photo.split(",")[0].strip() == query.split(",")[0].strip()


def parse_mdls(text):
    """Return latitude, longitude pairs in file order. Missing GPS is None."""
    coords = []
    lat = None
    seen_lat = False
    for line in (text or "").splitlines():
        if "kMDItemLatitude" in line:
            lat = _coord(line)
            seen_lat = True
            continue
        if "kMDItemLongitude" in line and seen_lat:
            coords.append((lat, _coord(line)))
            lat = None
            seen_lat = False
    return coords


def _coord(line):
    value = line.split("=", 1)[-1].strip()
    if not value or value == "(null)":
        return None
    try:
        return float(value)
    except ValueError:
        return None
