"""Getting from the game's title screen into the game world.

Each call to advance() looks at the screen once, works out where the game is and performs
the single action that moves it forward. Nothing relies on the previous call having worked,
so the goal loop can simply call it again until the game world is ready.

Screens, in the order they are recognised:
  character select  "Continue Adventure" is visible -> pick the first character, continue
  exit dialog       "quit the game"                  -> Cancel
  title screen      "tap the screen"                 -> tap it
  game world        HUD markers (Base / Job / Auto)  -> close pop-ups, clear the Game Menu
  anything else     loading or unknown               -> wait, or press Esc to reach the title screen
"""
import random
import time
from pathlib import Path

import game
import inputs
import scene
import vision
import winutil
from errors import StepFailed

BASE = Path(__file__).parent
CLOSE_X_ICON = BASE / "assets" / "close_x.png"
CLOSE_X_REF_WIDTH = 1225        # game window width when the X picture was captured
CLOSE_X_THRESHOLD = 0.5
CLOSE_X_AREA = (0.0, 0.04, 1.0, 1.0)

LEVEL_COLUMN = 0.45             # the character list sits in the left part of the window
CONTINUE_RETRY_AFTER = 6        # seconds before Continue Adventure is clicked again
LOAD_TIMEOUT = 150              # seconds the world may take to load after Continue Adventure
MAX_RESIZES = 4
MAX_ESC_UNKNOWN = 30
MAX_POPUPS = 12
MAX_MENU_ESC = 20
MAX_MENU_CLOSE = 3


class CharacterState:
    """What the stages have already done. The screen itself stays the source of truth."""

    def __init__(self):
        self.resizes = 0
        self.character_selected = False   # the first character was clicked; retries only press Continue
        self.continue_clicked_at = None
        self.unknown_count = 0
        self.popups_closed = 0
        self.menu_esc = 0
        self.menu_seen = False      # the Game Menu was opened by us and still has to be closed
        self.menu_close_tries = 0
        self.ready = False


def _rect_of(word):
    return word.x, word.y, word.x + word.w, word.y + word.h


def _continue_button(words):
    """Rectangle of the "Continue Adventure" button, which OCR reads as two lines of text."""
    hits = vision.find_phrases(words, "continue adventure")
    if hits:
        return hits[0]
    first, second = vision.find_phrases(words, "continue"), vision.find_phrases(words, "adventure")
    if first and second:
        a, b = first[0], second[0]
        return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])
    return None


def _first_level_text(words, rect):
    """The "Lv." text of the first character: the topmost one in the left part of the window."""
    limit = rect[0] + rect[2] * LEVEL_COLUMN
    found = [w for w in words if vision.norm(w.text).startswith("lv") and w.x < limit]
    return min(found, key=lambda w: w.y) if found else None


def _level_click_rect(word):
    """Rectangle of just the "Lv." letters inside the word OCR read (for example "Lv.32").
    Clicking the middle of the whole word would land on the number."""
    text = word.text.strip()
    letters = 3 if text[:3].lower().replace("l", "l") and len(text) >= 3 else len(text)
    share = min(1.0, letters / max(len(text), 1))
    right = word.x + max(int(word.w * share), 6)
    return word.x, word.y, right, word.y + word.h


def _press_escape(bot, hwnd):
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.15, 0.3))
    inputs.press_escape(bot)
    bot.sleep(random.uniform(0.7, 1.1))


def _click_phrase(bot, hwnd, words, phrase):
    hits = vision.find_phrases(words, phrase)
    if not hits:
        return False
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.15, 0.3))
    inputs.click_rect(bot, hwnd, hits[0])
    return True


def _find_popup_x(bot, rect):
    hits, _ = vision.find_image(bot, vision.region(rect, *CLOSE_X_AREA), CLOSE_X_ICON,
                                CLOSE_X_THRESHOLD, rect[2] / CLOSE_X_REF_WIDTH)
    return hits[0] if hits else None


def _same_spot(a, b, tolerance=6):
    """True when two rectangles (left, top, right, bottom) sit at the same place, give or take a few pixels."""
    return all(abs(p - q) <= tolerance for p, q in zip(a, b))


def _settled_targets(bot, hwnd, rect, level, button):
    """Reads the screen again until the window, the Lv. text and the Continue Adventure button
    stop moving between two reads. The character screen animates while it appears, so clicking
    a position read a moment earlier can land beside the target.
    Returns (level rectangle, button rectangle), or None if they did not settle."""
    for _ in range(5):
        bot.sleep(0.6)
        new_rect, words = scene.read(bot, hwnd)
        new_level, new_button = _first_level_text(words, new_rect), _continue_button(words)
        if new_level is None or new_button is None:
            return None
        settled = (_same_spot(new_rect, rect) and _same_spot(_level_click_rect(new_level), level)
                   and _same_spot(new_button, button))
        rect, level, button = new_rect, _level_click_rect(new_level), new_button
        if settled:
            return level, button
    return None


def _settled_button(bot, hwnd, button):
    """Waits until the Continue Adventure button holds the same position on two reads in a row.
    Selecting a character makes the button move, so a single read can catch it mid-motion."""
    previous = None
    for _ in range(6):
        bot.sleep(0.5)
        rect, words = scene.read(bot, hwnd)
        current = _continue_button(words)
        if current is None:
            continue
        if previous is not None and _same_spot(current, previous):
            return current
        previous = current
    return previous or button


def _character_select(bot, hwnd, rect, words, button, st):
    """The Lv. text is only clickable when the window fits the screen. The game can switch itself
    to full screen while it loads, which pushes the character list out of view. So: Continue
    Adventure is there, but Lv. is not -> fit the window again and look once more."""
    level = _first_level_text(words, rect)
    if level is None and not st.character_selected:
        st.resizes += 1
        if st.resizes > MAX_RESIZES:
            raise StepFailed("The character list is still not visible after resizing the window.")
        bot.log(f"Continue Adventure is visible but Lv. is not. Fitting the game window again "
                f"({st.resizes}/{MAX_RESIZES})...", "WARN")
        game.arrange(bot)
        bot.sleep(1.5)
        return
    st.resizes = 0

    if st.continue_clicked_at is not None and time.monotonic() - st.continue_clicked_at < CONTINUE_RETRY_AFTER:
        bot.sleep(1.0)  # the click was just made, give the game time to react
        return

    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.15, 0.3))

    if not st.character_selected:
        targets = _settled_targets(bot, hwnd, rect, _level_click_rect(level), button)
        if targets is None:
            return  # the screen was still changing, the next pass starts again from a fresh read
        level_rect, button = targets
        candidates = [f"'{w.text}'@{w.x},{w.y}" for w in words if vision.norm(w.text).startswith("lv")]
        bot.log(f"Lv. read: {', '.join(candidates)}. Clicking the Lv. of the first character at "
                f"x={level_rect[0]}-{level_rect[2]}, y={level_rect[1]}-{level_rect[3]}.")
        inputs.click_rect(bot, hwnd, level_rect, jitter=0.1)
        st.character_selected = True
        bot.log("First character selected.")
        bot.sleep(random.uniform(0.7, 1.0))

    # Selecting a character moves the button, so it is clicked only once it holds still.
    button = _settled_button(bot, hwnd, button)
    inputs.click_rect(bot, hwnd, button, jitter=0.04, hover_ms=250)
    st.continue_clicked_at = time.monotonic()
    bot.log(f"Continue Adventure clicked at x={button[0]}-{button[2]}, y={button[1]}-{button[3]}. "
            f"Waiting for the game world...")


def _game_world(bot, hwnd, rect, words, st):
    """Closes the welcome pop-ups, then makes sure the Game Menu is not left open."""
    if scene.menu_open(words):
        if st.menu_close_tries >= MAX_MENU_CLOSE:
            raise StepFailed("The Game Menu would not close.")
        st.menu_close_tries += 1
        st.menu_seen = True
        _press_escape(bot, hwnd)
        return

    popup = _find_popup_x(bot, rect) if st.popups_closed < MAX_POPUPS else None
    if popup:
        winutil.activate(hwnd)
        bot.sleep(random.uniform(0.15, 0.3))
        inputs.click_rect(bot, hwnd, popup)
        st.popups_closed += 1
        bot.log(f"Pop-up closed with its X button (#{st.popups_closed}).")
        bot.sleep(random.uniform(0.8, 1.2))
        st.menu_seen = False
        return

    if st.menu_seen:
        # The menu was opened and closed again and nothing else is on screen: the world is clear.
        st.ready = True
        bot.log(f"The game world is ready ({scene.in_game_detail(words)}).", "OK")
        return

    # Escape closes whatever is on top. When nothing is left to close it opens the Game Menu,
    # which is the sign that the world is clear.
    st.menu_esc += 1
    if st.menu_esc > MAX_MENU_ESC:
        raise StepFailed("The Game Menu never opened. Something is blocking the game world.")
    _press_escape(bot, hwnd)
    bot.sleep(0.8)  # the menu slides in, read it only once it has settled


def advance(bot, hwnd, st):
    """Looks at the screen once and performs the next step towards the game world."""
    if winutil.is_minimized(hwnd):
        winutil.restore(hwnd)
        bot.sleep(0.5)
    rect, words = scene.read(bot, hwnd)

    button = _continue_button(words)
    if button:
        st.unknown_count = 0
        return _character_select(bot, hwnd, rect, words, button, st)

    if scene.has(words, "quit the game"):
        st.unknown_count = 0
        _click_phrase(bot, hwnd, words, "cancel")
        bot.sleep(random.uniform(0.6, 1.0))
        return

    if scene.has(words, "tap the screen"):
        st.unknown_count = 0
        _click_phrase(bot, hwnd, words, "tap the screen")
        bot.log("Title screen: tapped the screen.")
        bot.sleep(random.uniform(1.2, 1.8))
        return

     # The Game Menu covers the HUD markers, so it has to be checked before the HUD itself.
    if scene.menu_open(words) or scene.in_game(words):
        st.unknown_count = 0
        return _game_world(bot, hwnd, rect, words, st)

    # Right after the Game Menu was used, an unreadable screen is the menu sliding away.
    # Pressing Esc now would open it again, so just wait and read again.
    if st.menu_seen and not st.ready and st.unknown_count < 10:
        st.unknown_count += 1
        bot.sleep(1.0)
        return

    # Loading or unknown screen.
    loading = (st.continue_clicked_at is not None and
               time.monotonic() - st.continue_clicked_at < LOAD_TIMEOUT)
    if loading:
        bot.sleep(2.0)
        return
    st.unknown_count += 1
    if st.unknown_count > MAX_ESC_UNKNOWN:
        raise StepFailed("The game screen could not be recognised.")
    seen = " ".join(w.text for w in words)[:90]
    bot.log(f"Screen not recognised yet ({st.unknown_count}/{MAX_ESC_UNKNOWN}). Pressing Esc. Text read: {seen}", "WARN")
    _press_escape(bot, hwnd)  # from most screens, Esc leads to the exit dialog and back to the title screen