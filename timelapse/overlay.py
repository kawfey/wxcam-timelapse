"""Burn a bottom-strip overlay (local datetime + camera title) onto a still.

Overlay-at-capture so every stored JPEG is self-documenting: the daily rollup and
the client viewer both just show the frames as-is, no re-annotation needed.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

# Common macOS/Linux font locations, in preference order. Falls back to Pillow's
# bundled bitmap font if none are found (ugly but never crashes).
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

TIME_FMT = "%Y-%m-%d %H:%M:%S %Z"


@lru_cache(maxsize=8)
def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def apply_overlay(img: Image.Image, title: str, when: datetime) -> Image.Image:
    """Return a copy of `img` with a translucent bottom strip: title (left) +
    timestamp (right). `when` should be tz-aware (local time)."""
    img = img.convert("RGB")
    w, h = img.size

    # Scale the strip to image height so it reads on both 480p and 1080p sources.
    strip_h = max(24, int(h * 0.075))
    font = _load_font(int(strip_h * 0.5))
    pad = int(strip_h * 0.28)

    # Translucent black strip via an RGBA overlay composited back to RGB.
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, h - strip_h, w, h], fill=(0, 0, 0, 140))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    ts = when.strftime(TIME_FMT)
    text_y = h - strip_h + (strip_h - _text_h(draw, font)) / 2

    # Title on the left (truncated if it would collide with the timestamp).
    ts_w = _text_w(draw, font, ts)
    max_title_w = w - ts_w - 3 * pad
    title = _truncate(draw, font, title, max_title_w)
    draw.text((pad, text_y), title, font=font, fill=(255, 255, 255))

    # Timestamp on the right.
    draw.text((w - ts_w - pad, text_y), ts, font=font, fill=(255, 255, 255))
    return img


def _text_w(draw: ImageDraw.ImageDraw, font, text: str) -> int:
    l, _, r, _ = draw.textbbox((0, 0), text, font=font)
    return r - l


def _text_h(draw: ImageDraw.ImageDraw, font) -> int:
    _, t, _, b = draw.textbbox((0, 0), "Ag", font=font)
    return b - t


def _truncate(draw, font, text: str, max_w: int) -> str:
    if max_w <= 0 or _text_w(draw, font, text) <= max_w:
        return text
    ell = "…"
    while text and _text_w(draw, font, text + ell) > max_w:
        text = text[:-1]
    return (text + ell) if text else ell
