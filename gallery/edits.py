"""Crop, rotate, and straighten a still photo with sips. Standard library only."""

import shutil
import subprocess
from pathlib import Path


def degrees_for(turns, straighten):
    turns = int(turns) % 4
    tilt = max(-15.0, min(15.0, float(straighten or 0)))
    return turns * 90 + tilt


def crop_box(width, height, crop):
    x = float(crop["x"])
    y = float(crop["y"])
    w = float(crop["w"])
    h = float(crop["h"])
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 1.001 or y + h > 1.001:
        raise ValueError("bad crop")
    left = int(round(x * width))
    top = int(round(y * height))
    pixels_w = max(1, int(round(w * width)))
    pixels_h = max(1, int(round(h * height)))
    left = min(left, width - 1)
    top = min(top, height - 1)
    pixels_w = min(pixels_w, width - left)
    pixels_h = min(pixels_h, height - top)
    if pixels_w < 1 or pixels_h < 1:
        raise ValueError("bad crop")
    return top, left, pixels_h, pixels_w


def copy_name(folder, name):
    folder = Path(folder)
    stem = Path(name).stem
    suffix = Path(name).suffix
    candidate = f"{stem} copy{suffix}"
    number = 2
    while (folder / candidate).exists():
        candidate = f"{stem} copy {number}{suffix}"
        number += 1
    return candidate


def pixel_size(path):
    proc = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    size = {}
    for line in proc.stdout.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.strip().partition(":")
        size[key.strip()] = value.strip()
    return int(float(size["pixelWidth"])), int(float(size["pixelHeight"]))


def render_edit(src, dest, turns=0, straighten=0, crop=None):
    src = Path(src)
    dest = Path(dest)
    if dest.resolve() == src.resolve():
        raise ValueError("same file")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    degrees = degrees_for(turns, straighten)
    if abs(degrees) >= 0.05:
        result = subprocess.run(
            ["sips", "-r", f"{degrees:.2f}", str(dest)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or not dest.is_file() or dest.stat().st_size <= 0:
            dest.unlink(missing_ok=True)
            detail = (result.stderr or result.stdout or "rotate failed").strip()
            raise RuntimeError(detail)
    if not crop:
        return dest
    width, height = pixel_size(dest)
    top, left, pixels_h, pixels_w = crop_box(width, height, crop)
    result = subprocess.run(
        [
            "sips",
            "--cropOffset", str(top), str(left),
            "-c", str(pixels_h), str(pixels_w),
            str(dest),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0 or not dest.is_file() or dest.stat().st_size <= 0:
        dest.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout or "crop failed").strip()
        raise RuntimeError(detail)
    return dest
