"""Where the photo library lives. Standard library only."""

import json
import subprocess
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
CONFIG = CODE / "gallery" / "library.json"


def code_root():
    return CODE


def program_dir():
    return CODE / "gallery"


def _saved_path():
    if not CONFIG.is_file():
        return None, ""
    try:
        data = json.loads(CONFIG.read_text())
    except (OSError, json.JSONDecodeError):
        return None, "missing"
    raw = data.get("root") if isinstance(data, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        return None, "missing"
    path = Path(raw).expanduser()
    try:
        path = path.resolve()
    except OSError:
        return None, "missing"
    if not path.is_dir():
        return path, "missing"
    try:
        next(path.iterdir(), None)
    except PermissionError:
        return path, "denied"
    except OSError:
        return path, "missing"
    return path, ""


def library_root():
    path, problem = _saved_path()
    if path is not None and not problem:
        return path
    return CODE


def data_dir():
    return library_root() / "gallery"


def photos_dir():
    return library_root() / "Photos"


def save_root(raw):
    text = str(raw or "").strip()
    if not text:
        raise ValueError("not a folder")
    path = Path(text).expanduser()
    try:
        path = path.resolve()
    except OSError as exc:
        raise ValueError("not a folder") from exc
    if not path.is_dir():
        raise ValueError("not a folder")
    try:
        next(path.iterdir(), None)
    except PermissionError as exc:
        raise PermissionError("cannot read") from exc
    except OSError as exc:
        raise ValueError("not a folder") from exc
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"root": str(path)}) + "\n")
    return path


def choose_folder():
    script = 'POSIX path of (choose folder with prompt "Choose the library folder")'
    try:
        done = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("cancelled") from exc
    if done.returncode != 0 or not done.stdout.strip():
        raise ValueError("cancelled")
    return save_root(done.stdout.strip())


def describe(active):
    active_path = Path(active).resolve()
    saved, problem = _saved_path()
    target = saved if saved is not None and not problem else active_path
    return {
        "active": str(active_path),
        "saved": "" if saved is None else str(saved),
        "code": str(CODE),
        "restart": bool(saved is not None and not problem and saved != active_path),
        "missing": problem == "missing",
        "denied": problem == "denied",
        "photos": (target / "Photos").is_dir(),
        "custom": saved is not None and not problem,
    }
