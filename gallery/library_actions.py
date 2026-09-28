"""Remove library items and send the files to Trash. Standard library only."""

import subprocess
from pathlib import Path


def photo_file(root, rel):
    base = Path(root).resolve()
    path = (base / rel).resolve()
    if path != base and base not in path.parents:
        raise ValueError("outside library")
    if not path.is_file():
        raise FileNotFoundError(rel)
    return path


def drop_photos(library, ids):
    wanted = set()
    for value in ids:
        try:
            wanted.add(int(value))
        except (TypeError, ValueError):
            continue
    by_id = library["by_id"]
    removed = []
    for photo_id in wanted:
        photo = by_id.pop(photo_id, None)
        if photo is not None:
            removed.append(photo)
    found = {photo["id"] for photo in removed}
    groups = []
    for group in library["groups"]:
        items = [item for item in group["items"] if item[0] not in found]
        if items:
            group["items"] = items
            groups.append(group)
    library["groups"] = groups
    library["count"] = len(by_id)
    return removed


def move_to_trash(paths):
    files = [str(Path(path)) for path in paths]
    if not files:
        return
    script = """on run argv
tell application "Finder"
repeat with posixPath in argv
set pathText to posixPath as text
set theItem to (POSIX file pathText) as alias
delete theItem
end repeat
end tell
end run"""
    result = subprocess.run(
        ["osascript", "-e", script, "--", *files],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Trash failed").strip()
        raise RuntimeError(detail)
