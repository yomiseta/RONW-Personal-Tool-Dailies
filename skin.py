"""Loads the console skin (background image) and generates a default one when none is available."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, ImageTk

import theme

BASE = Path(__file__).parent


def make_default_skin(path, size=(480, 540)):
    """Draws a dark gradient with a grid and a neon border, so the app never depends on an external image."""
    w, h = size
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    top, bottom = (11, 13, 20), (34, 14, 52)
    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    for x in range(0, w, 32):
        d.line([(x, 0), (x, h)], fill=(24, 30, 48))
    for y in range(0, h, 32):
        d.line([(0, y), (w, y)], fill=(24, 30, 48))
    d.rectangle([0, 0, w - 1, h - 1], outline=theme.CYAN, width=2)
    d.rectangle([5, 5, w - 6, h - 6], outline=theme.MAGENTA, width=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def load_skin(skin_path, size):
    """Returns a PhotoImage of exactly `size`. Falls back to the default skin if the file cannot be read."""
    p = Path(skin_path)
    if not p.is_absolute():
        p = BASE / p
    try:
        img = Image.open(p).convert("RGB")
    except Exception:
        default = BASE / "skins" / "default.png"
        if not default.exists():
            make_default_skin(default)
        img = Image.open(default).convert("RGB")
    img = ImageOps.fit(img, size, Image.LANCZOS)  # crop to fill instead of stretching
    return ImageTk.PhotoImage(img)