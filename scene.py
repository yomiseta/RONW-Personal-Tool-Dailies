"""Reading the game screen: which screen is showing right now."""
from pathlib import Path

import vision
import winutil
from errors import StepFailed

BASE = Path(__file__).parent

STRIP = (0.0, 0.72, 1.0, 1.0)   # the bottom of the window: reward windows, dialogs, Continue Adventure

# The game world is recognised by two small things that are always there: the "UTC+" clock text at
# the top left and the inventory icon at the bottom right. Both are read in tiny areas, which is quick.
UTC_AREA = (0.047, 0.031, 0.085, 0.057)
BAG_AREA = (0.937, 0.941, 0.966, 0.983)
BAG_ICON = BASE / "assets" / "inventory.png"
BAG_REF_WIDTH = 1440            # game window width when the inventory picture was captured
BAG_THRESHOLD = 0.6

# The Game Menu is recognised by the word "Settings" or "Casual", either one is enough.
MENU_SETTINGS_AREA = (0.917, 0.822, 0.976, 0.891)
MENU_CASUAL_AREA = (0.921, 0.820, 0.971, 0.890)


def read_strip(bot, hwnd):
    """Reads only the bottom strip of the game window. This is much quicker than reading the whole
    window, and everything needed to follow the loading and the pop-ups is inside it."""
    rect = winutil.get_rect(hwnd)
    return rect, vision.ocr_words(bot, vision.region(rect, *STRIP), "both")


def read(bot, hwnd):
    """Reads all text in the game window. Returns (window rectangle, words).
    Both OCR passes are used because the in-game text is white with a dark outline."""
    rect = winutil.get_rect(hwnd)
    return rect, vision.ocr_words(bot, rect, "both")


def has(words, phrase):
    return bool(vision.find_phrases(words, phrase))


def _text_in(bot, hwnd, area):
    """The text of one small part of the game window, lower-cased and without spaces or punctuation."""
    words = vision.ocr_words(bot, vision.region(winutil.get_rect(hwnd), *area), "both")
    return vision.norm(" ".join(w.text for w in words))


def menu_visible(bot, hwnd):
    """True when the Game Menu is open: "Settings" or "Casual" is read in its spot."""
    if "settings" in _text_in(bot, hwnd, MENU_SETTINGS_AREA):
        return True
    return "casual" in _text_in(bot, hwnd, MENU_CASUAL_AREA)


def world_visible(bot, hwnd):
    """True when both the "UTC+" text and the inventory icon are found. The icon is only searched
    for when the text was found, so a screen that is not the game world costs one quick read."""
    if "utc" not in _text_in(bot, hwnd, UTC_AREA):
        return False
    if not BAG_ICON.exists():
        raise StepFailed(f"inventory.png not found in the 'assets' folder: {BAG_ICON}")
    rect = winutil.get_rect(hwnd)
    hits, _ = vision.find_image(bot, vision.region(rect, *BAG_AREA), BAG_ICON,
                                BAG_THRESHOLD, rect[2] / BAG_REF_WIDTH)
    return bool(hits)


def screen_state(bot, hwnd):
    """"menu" when the Game Menu is open, "world" when the game world is showing, otherwise None.
    The menu is checked first because it is one quick read, and it hides the inventory icon."""
    if menu_visible(bot, hwnd):
        return "menu"
    if world_visible(bot, hwnd):
        return "world"
    return None