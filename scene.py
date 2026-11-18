"""Reading the game screen: which screen is showing right now."""
import vision
import winutil

STRIP = (0.0, 0.72, 1.0, 1.0)   # the bottom of the window: HUD markers, Game Menu, "Tap blank area", Continue Adventure


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


def in_game_score(words):
    """Counts the HUD markers at the edge of the game world. OCR sometimes misses one,
    so two out of four is enough to call it the game world."""
    return sum(has(words, p) for p in ("base", "job", "auto", "target list"))


def in_game(words):
    return in_game_score(words) >= 2


def in_game_detail(words):
    return " ".join(f"{name}={int(has(words, p))}" for name, p in
                    (("Base", "base"), ("Job", "job"), ("Auto", "auto"), ("TargetList", "target list")))


def menu_open(words):
    """The Game Menu is open when its core words are read, or at least 3 of its 5 words.
    "Customer Support" is stacked on two lines, so each word counts on its own."""
    support = has(words, "customer") or has(words, "support")
    count = sum([support, has(words, "unstuck"), has(words, "settings"),
                 has(words, "rankings"), has(words, "ban notice")])
    return (support and has(words, "unstuck") and has(words, "settings")) or count >= 3