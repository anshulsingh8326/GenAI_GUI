"""Mock-phase placeholder images (Pillow).

Until the real ComfyUI pipeline lands (the T2I feature step), "generated"
images are deterministic gradient placeholders - written as real PNG files so
the whole asset pipeline (files, hashes, thumbnails, serving, favorites) runs
exactly as it will with real outputs. Palettes match the GUI placeholder look.
"""

from __future__ import annotations

import random
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PALETTES: list[tuple[str, str]] = [
    ("#b8a7ee", "#8fe6c0"),
    ("#ffc29e", "#b8a7ee"),
    ("#9ecbff", "#b8a7ee"),
    ("#8fe6c0", "#9ecbff"),
    ("#ffb3c7", "#ffc29e"),
    ("#b8a7ee", "#ffb3c7"),
    ("#8fe6c0", "#ffc29e"),
    ("#9ecbff", "#8fe6c0"),
]

_FONT_CANDIDATES = ("segoeui.ttf", "arial.ttf", "calibri.ttf")


def _hash_string(text: str) -> int:
    h = 0
    for ch in text:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _diagonal_gradient(size: int, c1: tuple[int, int, int], c2: tuple[int, int, int]) -> Image.Image:
    """Cheap diagonal gradient: build small, upscale."""
    small = Image.new("RGB", (32, 32))
    pixels = small.load()
    assert pixels is not None
    for y in range(32):
        for x in range(32):
            t = (x + y) / 62
            pixels[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))
    return small.resize((size, size), Image.LANCZOS)


def _blob(size: int, cx: float, cy: float, radius: float, color: tuple[int, int, int, int]) -> Image.Image:
    """Soft circle overlay (drawn small + blurred, then upscaled)."""
    layer = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse(
        (
            cx * 256 - radius * 256,
            cy * 256 - radius * 256,
            cx * 256 + radius * 256,
            cy * 256 + radius * 256,
        ),
        fill=color,
    )
    layer = layer.filter(ImageFilter.GaussianBlur(26))
    return layer.resize((size, size), Image.BILINEAR)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_placeholder_png(label: str, index: int = 0, width: int = 1024, height: int = 1024) -> bytes:
    """Deterministic pastel placeholder - same input gives the same image."""
    c1, c2 = _hex(PALETTES[(_hash_string(label) + index) % len(PALETTES)][0]), _hex(
        PALETTES[(_hash_string(label) + index) % len(PALETTES)][1]
    )
    size = max(width, height)
    base = _diagonal_gradient(size, c1, c2)

    rng = random.Random(_hash_string(label) + index * 7)
    base = Image.alpha_composite(
        base.convert("RGBA"), _blob(size, rng.uniform(0.25, 0.7), rng.uniform(0.2, 0.55), 0.34, (255, 255, 255, 110))
    )
    base = Image.alpha_composite(
        base.convert("RGBA"), _blob(size, rng.uniform(0.7, 0.9), rng.uniform(0.68, 0.88), 0.24, (22, 20, 40, 45))
    ).convert("RGB")

    # centered if the requested aspect isn't square
    left = (size - width) // 2
    top = (size - height) // 2
    if (width, height) != (size, size):
        base = base.crop((left, top, left + width, top + height))

    # label chip at the bottom
    draw = ImageDraw.Draw(base, "RGBA")
    short = label if len(label) <= 42 else label[:41] + "..."
    font = _load_font(max(18, width // 28))
    try:
        box = draw.textbbox((0, 0), short, font=font)
        text_w, text_h = box[2] - box[0], box[3] - box[1]
    except Exception:  # noqa: BLE001 - very old bitmap fonts
        text_w, text_h = len(short) * 10, 16
    pad_x, pad_y = 22, 14
    chip_w = min(width - 48, text_w + pad_x * 2)
    chip_h = text_h + pad_y * 2
    x0, y0 = 24, height - chip_h - 24
    draw.rounded_rectangle((x0, y0, x0 + chip_w, y0 + chip_h), radius=14, fill=(255, 255, 255, 90))
    draw.text((x0 + pad_x, y0 + pad_y - 2), short, font=font, fill=(28, 24, 48, 210))

    buffer = BytesIO()
    base.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
