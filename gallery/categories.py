"""Group still photos by screenshot, document, and saved location."""

import math
import re

SCREENSHOT_RE = re.compile(r"screen\s*shot")
DOCUMENT_RE = re.compile(
    r"^(?:a )?(?:picture of a )?(?:piece of paper|sheet of paper|document|receipt|whiteboard)\b"
)
ANIMAL_RE = re.compile(
    r"\b(?:dogs?|cats?|birds?|horses?|animals?|puppy|puppies|kitten|kittens|cows?|sheep|fish|pets?|rabbits?|deer)\b"
)
FOOD_RE = re.compile(
    r"\b(?:food|meals?|pizza|sandwich(?:es)?|cakes?|breakfast|lunch|dinner|desserts?|restaurants?|fruits?|coffee|hot dogs?)\b"
)
NATURE_RE = re.compile(
    r"\b(?:mountains?|beach(?:es)?|forests?|oceans?|lakes?|rivers?|sunsets?|waterfalls?|deserts?|landscapes?|seas?|woods)\b"
)
VEHICLE_RE = re.compile(
    r"\b(?:cars?|trucks?|buses|bus|bicycles?|bikes?|motorcycles?|boats?|airplanes?|trains?|vehicles?)\b"
)
HOT_DOG_RE = re.compile(r"\bhot dogs?\b")
CAR_SEAT_RE = re.compile(r"\bcar\s*seat\b")
COORD_RE = re.compile(r"-?\d+\.\d+")


def kinds_for(name, caption):
    """Return the kinds a caption supports. An empty caption is not proof."""
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
    if ANIMAL_RE.search(HOT_DOG_RE.sub(" ", lower)):
        found.append("animal")
    if FOOD_RE.search(lower):
        found.append("food")
    if NATURE_RE.search(lower):
        found.append("nature")
    if VEHICLE_RE.search(CAR_SEAT_RE.sub(" ", lower)):
        found.append("vehicle")
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


def map_points(spots):
    """Group saved coordinates. The label stays a coordinate when no city is saved."""
    buckets = {}
    for lat, lon, label in spots or []:
        key = place_key(lat, lon)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "lat": float(f"{float(lat):.3f}"),
                "lon": float(f"{float(lon):.3f}"),
                "count": 0,
                "label": label or key.replace(",", ", "),
            }
            buckets[key] = bucket
        bucket["count"] += 1
        if COORD_RE.match(str(bucket["label"])) and label and not COORD_RE.match(str(label)):
            bucket["label"] = label
    return sorted(buckets.values(), key=lambda item: (-item["count"], item["label"]))


def nearest_place(points, lat, lon, limit_km=40):
    best = None
    best_km = None
    for point in points or []:
        km = _km(float(lat), float(lon), float(point["lat"]), float(point["lon"]))
        if best_km is None or km < best_km:
            best = point
            best_km = km
    if best is None or best_km > limit_km:
        return None
    return best


def _km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    arc = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(arc))


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
