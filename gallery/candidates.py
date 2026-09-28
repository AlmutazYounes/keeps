"""Decide which still photos are worth a delete review. Standard library only."""

import re

SCREENSHOT_RE = re.compile(r"screen\s*shot")
DOCUMENT_RE = re.compile(
    r"^(?:a )?(?:picture of a )?(?:piece of paper|sheet of paper|document|receipt|whiteboard)\b"
)
BLUR_RE = re.compile(r"\b(?:blurry|blurred|out of focus)\b")
PERSON_RE = re.compile(r"\b(?:person|people|man|woman|child|baby|boy|girl|face|faces)\b")


def reason_for(name, caption, has_face):
    """Return a short reason, or an empty string when the photo should stay."""
    if has_face:
        return ""
    text = caption or ""
    if not text.strip():
        return ""
    lower = text.casefold()
    label = (name or "").casefold()
    if SCREENSHOT_RE.search(lower) or SCREENSHOT_RE.search(label):
        return "Screenshot"
    if DOCUMENT_RE.search(lower) and not PERSON_RE.search(lower):
        return "Document"
    if BLUR_RE.search(lower) and not PERSON_RE.search(lower):
        return "Blurry"
    return ""
