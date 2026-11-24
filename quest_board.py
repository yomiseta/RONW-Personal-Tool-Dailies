"""Quest Board: refreshes the commissions towards the best reward level, starts them and follows
the quests until the Quest Board is done."""
import re
import time
from difflib import SequenceMatcher

from PIL import Image, ImageGrab

import ingame
import vision
import winutil
from errors import Halt

# ----- areas, as fractions of the game window: (left, top, right, bottom) -----
EVENT_LIST_AREA = (0.048, 0.281, 0.652, 0.765)   # the list of daily events
POPUP_AREA = (0.388, 0.206, 0.588, 0.315)        # title of the Quest Board info window
ATTEMPT_AREA = (0.181, 0.311, 0.344, 0.368)      # "Attempts:0/1" in the info window
MAIN_AREA = (0.416, 0.757, 0.592, 0.835)         # the "Start Commission" button of the board
REFRESH_AREA = (0.659, 0.287, 0.797, 0.326)      # "attempts: 5", or "cost:" when none are left
CONFIRM_AREA = (0.378, 0.285, 0.604, 0.344)      # title of the "Start Commission" confirmation
TRACKER_AREA = (0.022, 0.173, 0.158, 0.429)      # the quest widget in the game world
QUESTS_TITLE_AREA = (0.04, 0.04, 0.18, 0.11)     # title of the Quests window
GO_AREA = (0.681, 0.785, 0.752, 0.831)           # the Go button of the Quests window

# The five quest cards. They are not used yet: they are for spotting rare rewards later.
QUEST_AREAS = ((0.104, 0.267, 0.242, 0.511), (0.297, 0.275, 0.447, 0.498), (0.518, 0.282, 0.654, 0.511),
               (0.194, 0.516, 0.333, 0.736), (0.390, 0.510, 0.516, 0.740))

# ----- points, as fractions of the game window -----
GO = (0.499, 0.745)            # Go in the Quest Board info window
START = (0.504, 0.796)         # Start Commission on the board
CONFIRM = (0.621, 0.688)       # Start Commission in the confirmation window
QUEST_ICON = (0.064, 0.405)    # opens the Quests window from the game world
DAILY_TAB = (0.062, 0.407)     # Daily tab of the Quests window
QUEST_GO = (0.714, 0.809)      # Go button of the Quests window

REFRESH_POINTS = ((0.222, 0.286), (0.432, 0.300), (0.638, 0.299), (0.318, 0.533), (0.494, 0.519))
COLOR_POINTS = ((0.167, 0.336), (0.370, 0.329), (0.581, 0.343), (0.258, 0.575), (0.439, 0.570))

# ----- reward levels, told apart by colour -----
LEVELS = {"LOW": (132, 182, 235), "MID": (194, 140, 198), "HIGH": (239, 160, 99)}
COLOR_TOLERANCE = 45           # largest colour distance still accepted as one of the levels
COLOR_RADIUS = 2               # the colour is the average of (2 * radius + 1) squared pixels

# ----- timing and limits -----
BOARD_WAITS = (15, 11, 5, 5)   # seconds waited before each look for the opened board
REFRESH_SETTLE = 1.0           # seconds for the card animation after a refresh
MAX_REFRESH = 30               # refreshes allowed in one run, as a safety limit
START_SETTLE = 3.0             # seconds after starting before the first look at the quest widget
FIRST_LOOK_TRIES = 8           # the quest takes a moment to show in the widget: looks before giving up
FIRST_LOOK_EVERY = 2.5         # seconds between those looks
FUZZY_MIN = 7                  # markers with at least this many letters also match with a small OCR mistake
FUZZY_RATIO = 0.86             # how alike the text must be for such a match
CHECK_EVERY = 15               # seconds between looks at the quest widget
VERIFY_FROM = 12               # from this look on, a missing marker may mean the board is finished
VERIFY_EXTRA_WAIT = 5          # seconds before the second look when the marker is missing
RECOVER_FROM = 25              # from this look on, a missing marker is looked for in the Quests window
MAX_RECOVERY = 3               # times the Quests window is used before the bot stops
MAX_CHECKS = 60                # looks at the quest widget before the bot gives up (15 minutes)


# Only these markers are clicked. Clicking a monster quest would send the character back to the
# monster's first spawn point and the quest would never finish, so those are only watched.
CLICK_MARKERS = ("Commemorative Photo",)


# What the quest widget shows while a commission is running.
MARKERS = ("Defeat", "Eliminate", "Repel", "Chase away", "Capture Hydras", "Exorcise", "Catch", "Pummel",
           "Provide spa", "Head to", "Commemorative Photo", "Order Member", "Wealthy Merchant", "Sorrowful",
           "Gang of Thieves", "Boastful Blacksmith", "Girl Group Audience", "Mage Couple",
           "Assassin Guild Member", "Prontera Soldier", "Fishmonger", "Monster Enthusiast",
           "Little Bear Squad", "Gravekeeper", "Graveyard Notice", "Church Acolyte")


# ----- the Event window: steps 1 to 5 -----
def _open_and_read(bot, hwnd):
    """Opens the Quest Board info window from the Event list and returns its attempts as (done, total)."""
    ingame.begin(bot, hwnd, "Quest Board: opening the Event window.")
    ingame.click_fraction(bot, hwnd, ingame.EVENT_ICON, "Event icon")

    ingame.begin(bot, hwnd, "Quest Board: looking for it in the Event list.")
    word = ingame.wait_word(bot, hwnd, EVENT_LIST_AREA, "board", "Event list", confirm=0.3)
    ingame.click_word(bot, hwnd, word, "Quest Board")

    ingame.begin(bot, hwnd, "Quest Board: checking the info window.")
    ingame.wait_word(bot, hwnd, POPUP_AREA, "board", "Quest Board info window")
    done, total = ingame.wait_ratio(bot, hwnd, ATTEMPT_AREA, "Quest Board attempts")
    bot.log(f"Quest Board attempts: {done}/{total}.")
    return done, total


def _finish(bot, hwnd, daily):
    ingame.leave_windows(bot, hwnd)
    daily.quest_board = 1
    bot.log("Quest Board done.", "OK")


# ----- the board: steps 6 to 8 -----
def _wait_for_board(bot, hwnd):
    """After Go, the character walks to the board. Looks for the Start Commission button at set times."""
    for number, wait in enumerate(BOARD_WAITS, 1):
        bot.log(f"Quest Board: waiting {wait} seconds for the board (look {number} of {len(BOARD_WAITS)}).")
        bot.sleep(wait)
        ingame.clear_loot(bot, hwnd)
        if ingame.find_word(ingame.read_words(bot, hwnd, MAIN_AREA), "commission"):
            bot.log("Quest Board: the board is open.")
            return
    raise Halt("Stopped: the Quest Board did not open (the word 'Commission' was not detected "
               f"after {len(BOARD_WAITS)} looks).")


def _distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _level(color):
    """The reward level a colour belongs to (LOW, MID or HIGH), or None when it matches none."""
    name, gap = min(((n, _distance(color, ref)) for n, ref in LEVELS.items()), key=lambda item: item[1])
    return name if gap <= COLOR_TOLERANCE else None


def _sample_colors(hwnd):
    """Average colour around each of the five level points, from one capture of the game window."""
    left, top, width, height = winutil.get_rect(hwnd)
    try:
        shot = ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True).convert("RGB")
    except Exception as err:
        raise Halt(f"Stopped: the screen could not be captured ({type(err).__name__}).")
    colors = []
    for fx, fy in COLOR_POINTS:
        px, py = round(width * fx), round(height * fy)
        box = (max(px - COLOR_RADIUS, 0), max(py - COLOR_RADIUS, 0),
               min(px + COLOR_RADIUS + 1, width), min(py + COLOR_RADIUS + 1, height))
        colors.append(shot.crop(box).resize((1, 1), Image.BOX).getpixel((0, 0)))
    return colors


def _read_levels(bot, hwnd):
    """Reward levels of the five quests. The cards animate after a refresh, so the colours are read
    again until two reads in a row agree. Returns (levels, colors)."""
    previous = None
    for _ in range(6):
        colors = _sample_colors(hwnd)
        levels = [_level(c) for c in colors]
        if levels == previous:
            break
        previous = levels
        bot.sleep(0.4)
    text = ", ".join(f"{i + 1}={level or '?'}" for i, level in enumerate(levels))
    bot.log(f"Quest Board: reward levels {text}.")
    for i, level in enumerate(levels):
        if level is None:
            bot.log(f"Quest Board: quest {i + 1} has an unknown colour RGB {colors[i]}. It will not be refreshed.", "WARN")
    return levels, colors


def _next_target(levels):
    """The quest to refresh next: the first LOW one, and when none is left, the first MID one."""
    for wanted in ("LOW", "MID"):
        for i, level in enumerate(levels):
            if level == wanted:
                return i
    return None


def _peek_refresh(bot, hwnd):
    """One look at the refresh label. Returns the free attempts left, 0 when it shows the cost
    instead, or None when it could not be read."""
    words = ingame.read_words(bot, hwnd, REFRESH_AREA)
    text = vision.norm(" ".join(w.text for w in words))
    found = re.search(r"attempts(\d+)", text)
    if found:
        return int(found.group(1))
    if "cost" in text and "attempts" not in text:
        return 0
    return None


def _read_refresh(bot, hwnd):
    """Free refresh attempts left, read every half second, up to 10 times."""
    for attempt in range(1, ingame.TRIES + 1):
        left = _peek_refresh(bot, hwnd)
        if left is not None:
            return left
        if attempt < ingame.TRIES:
            ingame.clear_loot(bot, hwnd)
            bot.sleep(ingame.POLL)
    raise Halt(f"Stopped: the refresh attempts ('attempts:' or 'cost:') could not be read after {ingame.TRIES} tries.")


def _wait_refresh_used(bot, hwnd, before):
    """After clicking Refresh, waits until the free attempts drop below `before`."""
    for attempt in range(1, ingame.TRIES + 1):
        bot.sleep(ingame.POLL)
        left = _peek_refresh(bot, hwnd)
        if left is not None and left < before:
            return left
        ingame.clear_loot(bot, hwnd)
    raise Halt(f"Stopped: the refresh attempts did not drop after clicking Refresh ({ingame.TRIES} tries).")


def _refresh_quests(bot, hwnd):
    """Refreshes blue quests until none is left, then purple ones, while free attempts remain."""
    for _ in range(MAX_REFRESH):
        ingame.begin(bot, hwnd, "Quest Board: checking the quests.")
        levels, _ = _read_levels(bot, hwnd)
        target = _next_target(levels)
        if target is None:
            bot.log("Quest Board: no quest is left to improve.")
            return
        left = _read_refresh(bot, hwnd)
        if left == 0:
            bot.log("Quest Board: no free refresh attempts left.")
            return
        bot.log(f"Quest Board: refreshing quest {target + 1} ({levels[target]}). Free attempts left: {left}.")
        ingame.click_fraction(bot, hwnd, REFRESH_POINTS[target], f"Refresh {target + 1}")
        _wait_refresh_used(bot, hwnd, left)
        bot.sleep(REFRESH_SETTLE)
    raise Halt(f"Stopped: {MAX_REFRESH} refreshes were made and the quests are still not settled.")


def _start_commission(bot, hwnd):
    """Clicks Start Commission. When a quest is not top level, the game asks to confirm."""
    ingame.begin(bot, hwnd, "Quest Board: checking the quests before starting.")
    levels, _ = _read_levels(bot, hwnd)
    expect_confirm = any(level != "HIGH" for level in levels)

    ingame.click_fraction(bot, hwnd, START, "Start Commission")
    if expect_confirm:
        ingame.begin(bot, hwnd, "Quest Board: waiting for the confirmation window.")
        ingame.wait_word(bot, hwnd, CONFIRM_AREA, "start", "Start Commission confirmation")
        bot.sleep(0.3)
        ingame.click_fraction(bot, hwnd, CONFIRM, "Start Commission (confirm)")
    else:
        # All five are top level, so no window is expected. A quick look in case the colours misled.
        bot.sleep(1.0)
        if ingame.find_word(ingame.read_words(bot, hwnd, CONFIRM_AREA), "start"):
            bot.log("The confirmation window appeared anyway. Confirming.")
            bot.sleep(0.3)
            ingame.click_fraction(bot, hwnd, CONFIRM, "Start Commission (confirm)")
    bot.log("Quest Board: commission started.")


# ----- following the quests: steps 9 to 11 -----
def _lines(words):
    """Groups OCR words into text lines, each sorted from left to right."""
    lines = []
    for w in sorted(words, key=lambda word: word.y + word.h / 2):
        centre = w.y + w.h / 2
        if lines and abs(centre - lines[-1]["centre"]) <= max(lines[-1]["height"], w.h) * 0.6:
            lines[-1]["words"].append(w)
        else:
            lines.append({"centre": centre, "height": w.h, "words": [w]})
    return [sorted(line["words"], key=lambda word: word.x) for line in lines]


def _fuzzy_find(text, key):
    """Where in `text` a piece nearly equal to `key` starts, or -1. Allows a letter or two to be misread."""
    best, best_at = 0.0, -1
    for size in (len(key) - 1, len(key), len(key) + 1):
        for at in range(len(text) - size + 1):
            ratio = SequenceMatcher(None, text[at:at + size], key).ratio()
            if ratio > best:
                best, best_at = ratio, at
    return best_at if best >= FUZZY_RATIO else -1


def _marker_rect(words, marker):
    """Rectangle (left, top, right, bottom) where the marker's text is, or None.
    The widget wraps long quest names onto a second line, so the text of all lines is read as one
    flow, ignoring spaces and punctuation. The rectangle is that of the part on the first line."""
    key = vision.norm(marker)
    ordered, line_of = [], []
    for number, line in enumerate(_lines(words)):
        ordered += line
        line_of += [number] * len(line)
    texts = [vision.norm(w.text) for w in ordered]
    joined = "".join(texts)
    start = joined.find(key)
    if start < 0 and len(key) >= FUZZY_MIN:
        start = _fuzzy_find(joined, key)
    if start < 0:
        return None
    owner = []
    for index, text in enumerate(texts):
        owner += [index] * len(text)
    used = sorted(set(owner[start:start + len(key)]))
    first_line = line_of[used[0]]
    part = [ordered[i] for i in used if line_of[i] == first_line]
    return (min(w.x for w in part), min(w.y for w in part),
            max(w.x + w.w for w in part), max(w.y + w.h for w in part))


def _look(bot, hwnd):
    """Looks for a marker in the quest widget. Returns (hit, text): `hit` is (marker, rectangle) for the
    topmost marker or None, and `text` is what was read, for the log. The widget is read twice, as a plain
    picture and as white text only, and each reading is searched on its own, because the two readings
    of the same words would mix together if they were joined."""
    seen = []
    for mode in ("white", "normal"):
        words = ingame.read_words(bot, hwnd, TRACKER_AREA, mode)
        seen.append(" ".join(w.text for w in words))
        found = []
        for marker in MARKERS:
            rect = _marker_rect(words, marker)
            if rect:
                found.append((marker, rect))
        if found:
            return min(found, key=lambda item: item[1][1]), " | ".join(seen)
    return None, " | ".join(seen)


def _click_marker(bot, hwnd, hit, seen_markers):
    """Clicks the marker only when it is one of CLICK_MARKERS. Any other marker is just noted in the
    log, once each time it changes."""
    marker, rect = hit
    if marker in CLICK_MARKERS:
        ingame.click_word(bot, hwnd, rect, f"Quest marker '{marker}'")
    elif not seen_markers or seen_markers[-1] != marker:
        bot.log(f"Quest Board: the quest is '{marker}'. It is not clicked, so the quest keeps running.")
    seen_markers.append(marker)


def _verify_done(bot, hwnd, daily):
    """Looks at the Quest Board attempts again. Returns True when it is done (1/1)."""
    bot.log("Quest Board: checking whether it is finished.")
    done, total = _open_and_read(bot, hwnd)
    if done >= total:
        _finish(bot, hwnd, daily)
        return True
    bot.log(f"Quest Board is not finished yet ({done}/{total}).")
    ingame.leave_windows(bot, hwnd)
    return False


def _recover(bot, hwnd):
    """The marker may have scrolled out of the quest widget. Resumes the commission from the Quests window."""
    bot.log("Quest Board: the quest may be hidden in the widget. Opening the Quests window.")
    ingame.ensure_world(bot, hwnd)
    ingame.begin(bot, hwnd, "Quest Board: clicking the quest icon.")
    ingame.click_fraction(bot, hwnd, QUEST_ICON, "Quest icon")
    ingame.wait_word(bot, hwnd, QUESTS_TITLE_AREA, "quests", "Quests window")
    ingame.click_fraction(bot, hwnd, DAILY_TAB, "Daily tab")
    ingame.begin(bot, hwnd, "Quest Board: looking for the Go button.")
    ingame.wait_word(bot, hwnd, GO_AREA, "go", "Go button of the Daily quest")
    ingame.click_fraction(bot, hwnd, QUEST_GO, "Go")


def _first_look(bot, hwnd):
    """The quest takes a moment to appear in the widget after starting. Looks every few seconds
    and returns the first marker found, or None when none appears."""
    for attempt in range(1, FIRST_LOOK_TRIES + 1):
        ingame.clear_loot(bot, hwnd)
        hit, seen = _look(bot, hwnd)
        if hit:
            return hit
        bot.log(f"Quest Board: no quest marker yet ({attempt}/{FIRST_LOOK_TRIES}). Text read: {seen[:110]}", "WARN")
        if attempt < FIRST_LOOK_TRIES:
            bot.sleep(FIRST_LOOK_EVERY)
    return None


def _watch(bot, hwnd, daily, can_restart):
    """Follows the running commission. Returns "done", or "restart" when the quest never began."""
    bot.sleep(START_SETTLE)
    ingame.ensure_world(bot, hwnd)
    bot.log("Quest Board: following the quests.")
    first = _first_look(bot, hwnd)
    if first is None:
        if can_restart:
            bot.log("Quest Board: no quest marker appeared. Repeating the flow once.", "WARN")
            return "restart"
        raise Halt("Stopped: no quest marker was detected, even after repeating the Quest Board flow.")

    recoveries = 0
    seen_markers = []
    for check in range(1, MAX_CHECKS + 1):
        started = time.monotonic()
        if check == 1:
            hit = first
        else:
            ingame.clear_loot(bot, hwnd)
            hit, seen = _look(bot, hwnd)
        if hit:
            _click_marker(bot, hwnd, hit, seen_markers)
        elif check >= VERIFY_FROM:
            bot.log(f"Quest Board: no marker at look {check} (text read: {seen[:90]}). "
                    f"Looking again in {VERIFY_EXTRA_WAIT} seconds.")
            bot.sleep(VERIFY_EXTRA_WAIT)
            ingame.clear_loot(bot, hwnd)
            hit, seen = _look(bot, hwnd)
            if hit:
                _click_marker(bot, hwnd, hit, seen_markers)
            elif _verify_done(bot, hwnd, daily):
                return "done"
            elif check >= RECOVER_FROM:
                recoveries += 1
                if recoveries > MAX_RECOVERY:
                    raise Halt("Stopped: the quest could not be resumed from the Quests window.")
                _recover(bot, hwnd)
        bot.sleep(max(CHECK_EVERY - (time.monotonic() - started), 1.0))
    raise Halt(f"Stopped: the Quest Board is still not finished after {MAX_CHECKS} looks.")


def run(bot, hwnd, daily):
    ingame.require_assets()

    for round_number in (1, 2):
        done, total = _open_and_read(bot, hwnd)
        if done >= total:
            _finish(bot, hwnd, daily)
            return

        ingame.begin(bot, hwnd, "Quest Board: pressing Go.")
        ingame.click_fraction(bot, hwnd, GO, "Go")
        _wait_for_board(bot, hwnd)
        _refresh_quests(bot, hwnd)
        _start_commission(bot, hwnd)

        if _watch(bot, hwnd, daily, can_restart=(round_number == 1)) == "done":
            return
        ingame.ensure_world(bot, hwnd)   # back to the game world before the flow is repeated