"""Building blocks shared by the in-game daily activities.

Positions and areas are fractions of the game window, so they keep working at any window size.
Every step starts by closing item pop-ups, because loot windows can appear at any moment and
would cover whatever the step is about to read or click.
"""
import random
import re
from pathlib import Path

import inputs
import scene
import vision
import winutil
from errors import Halt

BASE = Path(__file__).parent
LOOT_ICON = BASE / "assets" / "loot_close.png"
LOOT_AREA = (0.359, 0.596, 0.880, 0.828)   # where the item pop-up appears
LOOT_PAD = 0.04                            # extra margin: the red X sits on the pop-up's top corner
LOOT_REF_WIDTH = 1440                      # game window width when the X picture was captured
LOOT_THRESHOLD = 0.6
LOOT_MAX = 8                               # pop-ups closed in a row before giving up

EVENT_ICON = (0.790, 0.079)                # the Event icon in the top bar of the game world

POLL = 0.5                                 # seconds between looks for a word
TRIES = 10                                 # looks before the bot stops and reports
MAX_ESC = 8                                # Esc presses allowed while returning to the game world

_RATIO = re.compile(r"(\d+)\s*/\s*(\d+)")


def require_assets(*extra):
    """Stops the bot with a clear message when a needed picture is missing from the assets folder."""
    for path in (LOOT_ICON, *extra):
        if not path.exists():
            raise Halt(f"Stopped: {path.name} not found in the 'assets' folder: {path}")


# ----- positions -----
def screen_point(hwnd, fx, fy):
    """Screen pixel of a point given as fractions of the game window."""
    left, top, width, height = winutil.get_rect(hwnd)
    return left + round(width * fx), top + round(height * fy)


def read_words(bot, hwnd, area, mode="both"):
    """OCR of a part of the game window. `area` is (left, top, right, bottom) as fractions."""
    return vision.ocr_words(bot, vision.region(winutil.get_rect(hwnd), *area), mode)


def find_word(words, target):
    """Rectangle (left, top, right, bottom) of the target word among OCR words, or None.
    A longer word that contains the target also counts, since OCR often glues neighbouring marks on."""
    hits = vision.find_phrases(words, target)
    if hits:
        return hits[0]
    key = vision.norm(target)
    if len(key) >= 4:
        for w in words:
            text = vision.norm(w.text)
            if key in text and len(text) <= len(key) + 2:
                return w.x, w.y, w.x + w.w, w.y + w.h
    return None


# ----- item pop-ups -----
def clear_loot(bot, hwnd):
    """Closes item pop-ups by clicking the red X exactly at its centre. Looks again after each
    one, because another pop-up may follow. Returns how many were closed."""
    closed = 0
    for _ in range(LOOT_MAX):
        rect = winutil.get_rect(hwnd)
        fl, ft, fr, fb = LOOT_AREA
        area = (max(fl - LOOT_PAD, 0.0), max(ft - LOOT_PAD, 0.0), min(fr + LOOT_PAD, 1.0), min(fb + LOOT_PAD, 1.0))
        hits, _ = vision.find_image(bot, vision.region(rect, *area), LOOT_ICON,
                                    LOOT_THRESHOLD, rect[2] / LOOT_REF_WIDTH)
        if not hits:
            return closed
        left, top, right, bottom = hits[0]
        winutil.activate(hwnd)
        inputs.click_point(bot, hwnd, (left + right) // 2, (top + bottom) // 2)
        closed += 1
        bot.log(f"Item pop-up closed (#{closed}).")
        bot.sleep(0.5)
    return closed


def begin(bot, hwnd, text):
    """Start of a step: closes item pop-ups first, then logs what the step does."""
    clear_loot(bot, hwnd)
    bot.log(text)


# ----- clicking -----
def click_fraction(bot, hwnd, point, what):
    """Clicks a fixed point of the game window, exactly, with no random offset."""
    x, y = screen_point(hwnd, *point)
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.1, 0.2))
    inputs.click_point(bot, hwnd, x, y)
    bot.log(f"{what}: clicked at x={x}, y={y}.")


def click_word(bot, hwnd, rect, what):
    """Clicks the exact centre of a word found on screen."""
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.1, 0.2))
    inputs.click_point(bot, hwnd, x, y)
    bot.log(f"{what}: clicked at x={x}, y={y}.")


def press_esc(bot, hwnd):
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.1, 0.2))
    inputs.press_escape(bot)


# ----- waiting for something on screen -----
def wait_word(bot, hwnd, area, target, what, confirm=None):
    """Looks for a word every half second, up to 10 times, and returns its rectangle.
    With `confirm`, a found word is looked for once more after that many seconds, and the
    position of the second sighting is returned, so a moving screen cannot cause a misplaced click.
    Stops the bot when the word never shows up."""
    for attempt in range(1, TRIES + 1):
        rect = find_word(read_words(bot, hwnd, area), target)
        if rect and confirm:
            bot.sleep(confirm)
            rect = find_word(read_words(bot, hwnd, area), target)
        if rect:
            return rect
        if attempt < TRIES:
            clear_loot(bot, hwnd)   # a pop-up may be covering the word
            bot.sleep(POLL)
    raise Halt(f"Stopped: the word '{target}' was not detected ({what}) after {TRIES} tries.")


def wait_image(bot, hwnd, area, icon, what, threshold=0.7, ref_width=LOOT_REF_WIDTH):
    """Looks for a picture every half second, up to 10 times, and returns its rectangle.
    Used for marks that text recognition cannot read, such as a single key letter.
    Stops the bot when the picture never shows up."""
    for attempt in range(1, TRIES + 1):
        rect = winutil.get_rect(hwnd)
        hits, _ = vision.find_image(bot, vision.region(rect, *area), icon, threshold, rect[2] / ref_width)
        if hits:
            return hits[0]
        if attempt < TRIES:
            clear_loot(bot, hwnd)   # a pop-up may be covering it
            bot.sleep(POLL)
    raise Halt(f"Stopped: the picture '{icon.name}' was not detected ({what}) after {TRIES} tries.")


def wait_ratio(bot, hwnd, area, what, accept=None):
    """Reads a number pair such as 5/5 from an area, every half second, up to 10 times.
    Returns (first, second). `accept(first, second)` can reject a reading that is not the expected one yet."""
    for attempt in range(1, TRIES + 1):
        text = " ".join(w.text for w in read_words(bot, hwnd, area))
        found = _RATIO.search(text)
        if found:
            first, second = int(found.group(1)), int(found.group(2))
            if accept is None or accept(first, second):
                return first, second
        if attempt < TRIES:
            clear_loot(bot, hwnd)
            bot.sleep(POLL)
    raise Halt(f"Stopped: the numbers ({what}) could not be read after {TRIES} tries.")


# ----- back to the game world -----
def ensure_world(bot, hwnd):
    """Presses Esc until the game world is on screen: HUD markers visible and no Game Menu.
    The screen is read before each press, so Esc is never pressed once the world is showing."""
    for _ in range(MAX_ESC):
        _, words = scene.read_strip(bot, hwnd)
        if scene.menu_open(words):
            press_esc(bot, hwnd)       # the Game Menu is open: close it
            bot.sleep(0.6)
            continue
        if scene.in_game(words):
            bot.sleep(0.5)             # look once more before trusting it
            _, words = scene.read_strip(bot, hwnd)
            if scene.in_game(words) and not scene.menu_open(words):
                return
            continue
        press_esc(bot, hwnd)
        bot.sleep(0.6)
    raise Halt("Stopped: the game world could not be reached with Esc.")


def leave_windows(bot, hwnd):
    """Closes the open game windows with two Esc presses, then makes sure the world is showing."""
    bot.sleep(1.0)
    press_esc(bot, hwnd)
    bot.sleep(0.5)
    press_esc(bot, hwnd)
    ensure_world(bot, hwnd)