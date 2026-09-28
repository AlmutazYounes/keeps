"""Decide which scored still photos belong on the review dashboard."""

LEVELS = ("careful", "normal", "aggressive")


def normalize(raw_sharp, raw_spread):
    """Map a Laplacian variance and a pixel spread onto 0-100. High means sharp or varied."""
    sharp = max(0, min(100, int(round(float(raw_sharp) / 5))))
    spread = max(0, min(100, int(round(float(raw_spread) / 0.8))))
    return sharp, spread


def strength_for(sharp, spread):
    blur = max(0, 100 - int(sharp))
    flat = max(0, 100 - int(spread))
    return max(blur, flat)


def reason_for(sharp, spread, caption_reason):
    if int(sharp) <= int(spread) and int(sharp) < 55:
        return "Blurry frame"
    if int(spread) < 40:
        return "Flat color"
    if caption_reason:
        return caption_reason
    return "Low detail"


def visible(level, strength, named, caption_flag):
    """A named person stays off unless the setting is aggressive and the frame is weak."""
    level = level if level in LEVELS else "normal"
    strength = int(strength)
    if level == "careful":
        return (not named) and strength >= 80
    if level == "normal":
        if named:
            return False
        return strength >= 55 or bool(caption_flag)
    if named:
        return strength >= 75
    return strength >= 35 or bool(caption_flag)
