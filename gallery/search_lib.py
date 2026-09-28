"""Turn a search sentence into filters and test one library item.

The gallery server imports this module. It uses the standard library only.
"""

import re
from datetime import date

YEAR_MIN = 2009
YEAR_MAX = 2026

MONTH_ALT = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec"
)

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

STOPWORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "of", "for", "to", "and", "or",
    "with", "from", "by", "as", "is", "it", "my", "our", "their", "this",
    "that", "these", "those", "into", "onto", "during", "some", "just",
    "very", "wearing", "wear", "wears", "wore", "be", "was", "were", "am",
    "are", "his", "her", "its", "me",
})

VIDEO_WORDS = frozenset({"video", "videos"})
PHOTO_WORDS = frozenset({"photo", "photos", "picture", "pictures"})

TOKEN_RE = re.compile(r"[a-z0-9]+")
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

MONTH_DAY_YEAR_RE = re.compile(
    rf"\b({MONTH_ALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(20\d{{2}})\b"
)
DAY_MONTH_YEAR_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_ALT})\s+(20\d{{2}})\b"
)
MONTH_YEAR_RE = re.compile(rf"\b({MONTH_ALT})\s+(20\d{{2}})\b")
PREP_YEAR_RE = re.compile(r"\b(?:in|from|during)\s+(20\d{2})\b")
YEAR_RE = re.compile(r"\b(20\d{2})\b")


def parse_query(text, people=None):
    """Split a sentence into person, date, media, and content words."""
    lower = (text or "").casefold()
    consumed = [False] * len(lower)
    matched = _people(lower, consumed, people)
    year, month, day = _date(lower, consumed)
    kind = _media(lower, consumed)
    words = _words(lower, consumed)
    return {
        "person": matched[0] if matched else "",
        "people": matched,
        "year": year,
        "month": month,
        "day": day,
        "kind": kind,
        "words": words,
        "text": " ".join(words),
    }


def item_matches(item, filters, caption="", ids_by_person=None, group_year="", group_month=""):
    """Return true when one item satisfies the filters.

    item is [id, name, kind, date]. kind is "video" or a still kind.
    date is YYYY-MM-DD when the gallery stored one. Otherwise the group
    year and month are used, and there is no day.
    A person matches a saved face id, or the file name when the name is a
    whole word. Each content word has to appear in the caption or the file
    name, ignoring spaces and punctuation.
    """
    filters = filters or {}
    item_id, name, kind, year, month, day = _parts(item, group_year, group_month)
    people = list(filters.get("people") or [])
    if not people and filters.get("person"):
        people = [filters["person"]]
    for person in people:
        ids = _ids_for(ids_by_person, person)
        if item_id not in ids and not _name_has_person(name, person):
            return False
    want = filters.get("kind") or ""
    if want == "video" and kind != "video":
        return False
    if want == "photo" and kind == "video":
        return False
    if filters.get("year") is not None and year != filters["year"]:
        return False
    if filters.get("month") is not None and month != filters["month"]:
        return False
    if filters.get("day") is not None and day != filters["day"]:
        return False
    file_sq = _squash(name)
    cap_sq = _squash(caption)
    for word in filters.get("words") or []:
        token = _squash(word)
        if token and token not in file_sq and token not in cap_sq:
            return False
    return True


def filter_groups(groups, filters, captions_by_id=None, ids_by_person=None):
    """Keep groups that still have at least one matching item."""
    captions_by_id = captions_by_id or {}
    kept = []
    for group in groups or []:
        items = []
        for item in group.get("items") or []:
            caption = captions_by_id.get(item[0])
            if caption is None:
                caption = captions_by_id.get(str(item[0]), "")
            if item_matches(
                item,
                filters,
                caption=caption,
                ids_by_person=ids_by_person,
                group_year=group.get("year") or "",
                group_month=group.get("month") or "",
            ):
                items.append(item)
        if items:
            kept.append({**group, "items": items})
    return kept


def _people(lower, consumed, people):
    found = []
    for name in _names(people):
        pattern = re.compile(
            r"(?<![a-z0-9])" + re.escape(name.casefold()) + r"(?![a-z0-9])"
        )
        for match in pattern.finditer(lower):
            start, end = match.span()
            if _taken(consumed, start, end):
                continue
            _mark(consumed, start, end)
            found.append((start, name))
            break
    found.sort(key=lambda pair: pair[0])
    return [name for _, name in found]


def _names(people):
    found = []
    seen = set()
    for person in people or []:
        if isinstance(person, dict):
            name = person.get("name") or ""
        else:
            name = person or ""
        name = str(name).strip()
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        found.append(name)
    found.sort(key=len, reverse=True)
    return found


def _date(lower, consumed):
    checks = (
        (MONTH_DAY_YEAR_RE, lambda match: (
            int(match.group(3)),
            MONTHS[match.group(1)],
            int(match.group(2)),
        )),
        (DAY_MONTH_YEAR_RE, lambda match: (
            int(match.group(3)),
            MONTHS[match.group(2)],
            int(match.group(1)),
        )),
        (MONTH_YEAR_RE, lambda match: (
            int(match.group(2)),
            MONTHS[match.group(1)],
            None,
        )),
        (PREP_YEAR_RE, lambda match: (int(match.group(1)), None, None)),
        (YEAR_RE, lambda match: (int(match.group(1)), None, None)),
    )
    for pattern, picker in checks:
        for match in pattern.finditer(lower):
            start, end = match.span()
            if _taken(consumed, start, end):
                continue
            year, month, day = picker(match)
            if not _valid_date(year, month, day):
                continue
            _mark(consumed, start, end)
            return year, month, day
    return None, None, None


def _valid_date(year, month, day):
    if year < YEAR_MIN or year > YEAR_MAX:
        return False
    if month is None and day is None:
        return True
    if month is None or not 1 <= month <= 12:
        return False
    if day is None:
        return True
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _media(lower, consumed):
    kind = ""
    spans = []
    for match in TOKEN_RE.finditer(lower):
        start, end = match.span()
        if _taken(consumed, start, end):
            continue
        word = match.group()
        if word in VIDEO_WORDS:
            kind = "video"
            spans.append((start, end))
        elif word in PHOTO_WORDS:
            kind = "photo"
            spans.append((start, end))
    for start, end in spans:
        _mark(consumed, start, end)
    return kind


def _words(lower, consumed):
    words = []
    seen = set()
    for match in TOKEN_RE.finditer(lower):
        start, end = match.span()
        if _taken(consumed, start, end):
            continue
        word = match.group()
        if word in STOPWORDS or word in VIDEO_WORDS or word in PHOTO_WORDS:
            continue
        if word in seen:
            continue
        seen.add(word)
        words.append(word)
    return words


def _parts(item, group_year, group_month):
    if isinstance(item, dict):
        item_id = item.get("id")
        name = item.get("name") or ""
        kind = item.get("kind") or ""
        raw = item.get("date") or ""
    else:
        item_id = item[0]
        name = item[1]
        kind = item[2]
        raw = item[3] if len(item) > 3 and item[3] else ""
    if isinstance(raw, str) and ISO_RE.fullmatch(raw[:10]):
        year, month, day = raw[:10].split("-")
        return item_id, name, kind, int(year), int(month), int(day)
    year = int(group_year) if str(group_year).isdigit() else None
    month = None
    prefix = str(group_month or "")[:2]
    if prefix.isdigit():
        month = int(prefix)
    return item_id, name, kind, year, month, None


def _ids_for(ids_by_person, person):
    if not ids_by_person or not person:
        return set()
    key = person.casefold()
    raw = None
    if key in ids_by_person:
        raw = ids_by_person[key]
    else:
        for name, ids in ids_by_person.items():
            if str(name).casefold() == key:
                raw = ids
                break
    return _id_set(raw)


def _id_set(values):
    found = set()
    for value in values or []:
        found.add(value)
        if isinstance(value, int):
            found.add(str(value))
        elif isinstance(value, str) and value.isdigit():
            found.add(int(value))
    return found


def _name_has_person(filename, person):
    needle = person.casefold()
    pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
    return re.search(pattern, (filename or "").casefold()) is not None


def _squash(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").casefold())


def _taken(consumed, start, end):
    return any(consumed[start:end])


def _mark(consumed, start, end):
    for index in range(start, end):
        consumed[index] = True
