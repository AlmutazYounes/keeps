"""Which installed model each AI job should load. Standard library only."""

import json
from pathlib import Path

import library_root

APP = library_root.program_dir()
MODELS = APP / "models"
CHOICES = APP / "jobs" / "model_choices.json"

CAPTION_FILES = (
    "tokenizer.json",
    "onnx/vision_encoder_q4f16.onnx",
    "onnx/embed_tokens_q4f16.onnx",
    "onnx/encoder_model_q4f16.onnx",
    "onnx/decoder_model_q4f16.onnx",
    "onnx/decoder_model_merged_q4.onnx",
)

ROLES = (
    {
        "id": "faces_detect",
        "title": "Face finder",
        "note": "Finds a face in a still photo.",
        "options": (
            {
                "id": "10g_bnkps",
                "label": "10G face finder",
                "files": ("10g_bnkps.onnx",),
            },
        ),
    },
    {
        "id": "faces_embed",
        "title": "Face match",
        "note": "Turns a face into a vector so the same person stays together.",
        "options": (
            {
                "id": "arcface_w600k_r50",
                "label": "ArcFace R50",
                "files": ("arcface_w600k_r50_batch.onnx",),
            },
        ),
    },
    {
        "id": "captions",
        "title": "Descriptions",
        "note": "Writes the sentence search uses.",
    },
)


def _inside(path):
    base = MODELS.resolve()
    target = path.resolve()
    return target == base or base in target.parents


def _ready(files):
    for rel in files:
        path = MODELS / rel
        if not _inside(path) or not path.is_file():
            return False
    return True


def caption_options():
    found = []
    if not MODELS.is_dir():
        return found
    for folder in sorted(MODELS.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        files = tuple(f"{folder.name}/{name}" for name in CAPTION_FILES)
        if not _ready(files):
            continue
        label = "Florence-2 base" if folder.name == "florence2" else folder.name
        found.append({"id": folder.name, "label": label, "files": files})
    return found


def _role(role_id):
    for role in ROLES:
        if role["id"] == role_id:
            return role
    return None


def _options(role):
    if role["id"] == "captions":
        return caption_options()
    return list(role["options"])


def _saved():
    if not CHOICES.is_file():
        return {}
    try:
        data = json.loads(CHOICES.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _selected(role, saved):
    options = _options(role)
    wanted = saved.get(role["id"])
    for option in options:
        if option["id"] == wanted and _ready(option["files"]):
            return option["id"]
    for option in options:
        if _ready(option["files"]):
            return option["id"]
    return options[0]["id"] if options else ""


def view():
    saved = _saved()
    roles = []
    for role in ROLES:
        options = []
        for option in _options(role):
            options.append({
                "id": option["id"],
                "label": option["label"],
                "installed": _ready(option["files"]),
            })
        roles.append({
            "id": role["id"],
            "title": role["title"],
            "note": role["note"],
            "selected": _selected(role, saved),
            "options": options,
        })
    return roles


def _option_by_id(role, option_id):
    for option in _options(role):
        if option["id"] == option_id:
            return option
    return None


def save_choices(choices):
    if not isinstance(choices, dict):
        raise ValueError("bad choices")
    saved = _saved()
    for role_id, option_id in choices.items():
        role = _role(role_id)
        if role is None:
            raise ValueError("unknown role")
        option = _option_by_id(role, str(option_id))
        if option is None or not _ready(option["files"]):
            raise ValueError("unavailable model")
        saved[role_id] = option["id"]
    CHOICES.parent.mkdir(parents=True, exist_ok=True)
    CHOICES.write_text(json.dumps(saved))
    return view()


def model_file(role_id):
    role = _role(role_id)
    if role is None or role_id == "captions":
        raise ValueError("unknown role")
    option = _option_by_id(role, _selected(role, _saved()))
    if option is None:
        raise ValueError("unavailable model")
    path = MODELS / option["files"][0]
    if not _inside(path):
        raise ValueError("outside models")
    return path


def caption_dir():
    role = _role("captions")
    option = _option_by_id(role, _selected(role, _saved()))
    if option is None:
        raise ValueError("unavailable model")
    path = MODELS / option["id"]
    if not _inside(path) or not path.is_dir():
        raise ValueError("unavailable model")
    return path
