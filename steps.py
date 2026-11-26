"""Small helpers shared by the preparation steps (inventory, reward retrieval, mails)."""
import re
from pathlib import Path

import ingame
import vision
import winutil
from errors import Halt

BASE = Path(__file__).parent
ASSETS = BASE / "assets"
REF_WIDTH = 1440             # game window width when the marker pictures were captured
BADGE_THRESHOLD = 0.7        # how alike a red "!" badge must be to the saved picture

_RATIO = re.compile(r"(\d+)\s*/\s*(\d+)")


def need_assets(*names):
    """Stops the bot with a clear message when a marker picture is missing from the assets folder."""
    for name in names:
        if not (ASSETS / name).exists():
            raise Halt(f"Stopped: {name} not found in the 'assets' folder: {ASSETS / name}")


def has_text(bot, hwnd, area, target):
    """One look: True when the target text is read in the area. Spaces and punctuation are ignored."""
    words = ingame.read_words(bot, hwnd, area)
    return vision.norm(target) in vision.norm(" ".join(w.text for w in words))


def wait_text(bot, hwnd, area, target, what):
    """Looks for a text every half second, up to 10 times, closing item pop-ups in between.
    Stops the bot when it never shows up."""
    for attempt in range(1, ingame.TRIES + 1):
        if has_text(bot, hwnd, area, target):
            return
        if attempt < ingame.TRIES:
            ingame.clear_loot(bot, hwnd)
            bot.sleep(ingame.POLL)
    raise Halt(f"Stopped: the word '{target}' was not detected ({what}) after {ingame.TRIES} tries.")


def look(bot, hwnd, area, icon, threshold=BADGE_THRESHOLD, ref_width=REF_WIDTH):
    """One look for a picture in an area. Returns (rectangle or None, best score)."""
    rect = winutil.get_rect(hwnd)
    hits, best = vision.find_image(bot, vision.region(rect, *area), icon, threshold, rect[2] / ref_width)
    return (hits[0] if hits else None), best


def wait_icon(bot, hwnd, area, icon, what, threshold=BADGE_THRESHOLD, ref_width=REF_WIDTH):
    """Looks for a picture every half second, up to 10 times. Stops the bot when it never shows up."""
    for attempt in range(1, ingame.TRIES + 1):
        hit, _ = look(bot, hwnd, area, icon, threshold, ref_width)
        if hit:
            return hit
        if attempt < ingame.TRIES:
            ingame.clear_loot(bot, hwnd)
            bot.sleep(ingame.POLL)
    raise Halt(f"Stopped: the icon '{what}' was not detected after {ingame.TRIES} tries.")


def try_ratio(bot, hwnd, area, tries=3):
    """Reads a number pair such as 158/200. Returns (first, second), or None when it cannot be read."""
    for attempt in range(1, tries + 1):
        text = " ".join(w.text for w in ingame.read_words(bot, hwnd, area))
        found = _RATIO.search(text)
        if found:
            return int(found.group(1)), int(found.group(2))
        if attempt < tries:
            bot.sleep(ingame.POLL)
    return None