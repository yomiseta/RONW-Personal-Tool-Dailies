"""Getting from the game's title screen into the game world.

Each call to advance() looks at the screen once, works out where the game is and performs
the single action that moves it forward. Nothing relies on the previous call having worked,
so the goal loop can simply call it again until the game world is ready.

Screens, in the order they are recognised:
  Recent News       "Recent News" window                     -> close it with its X button
  title screen      "Tap" below the logo                     -> tap the screen
  reward window     "Congrats" / "Tap blank area to close"   -> click it
  character select  "Continue Adventure" is visible          -> pick the first character, continue
  game world        HUD markers (Base / Job / Auto) or the Game Menu -> close pop-ups, clear the menu
  anything else     loading or unknown                       -> wait (no key is pressed)

The Recent News window and the title screen are found with two small, quick reads instead of a
full read of the window, so they are handled as soon as they appear.

Once the character screen or the game world has been seen, the screen is followed with a quick
read of its bottom strip only. The full window is read again when that shows nothing familiar.
"""
import random
import re
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

CONGRATS_AREA = (0.2, 0.15, 0.8, 0.65)   # middle of the window, as fractions of its size
LEVEL_AREA = (0.04, 0.24, 0.30, 0.40)    # where the first character's "Lv." sits, as fractions of the window
CONTINUE_POINT = (0.883, 0.828)          # Continue Adventure never moves, so it is clicked by position

NEWS_AREA = (0.444, 0.184, 0.613, 0.235)   # title of the "Recent News" window
NEWS_CLOSE = (0.890, 0.210)                # its close button
TAP_AREA = (0.406, 0.677, 0.587, 0.727)    # the "Tap the screen" text of the title screen
TAP_POINT = (0.501, 0.704)                 # where the screen is tapped
TAP_POLL = 0.5                             # seconds between looks for "Tap" after the news is closed
TAP_POLLS = 10                             # looks before the normal flow takes over

LEVEL_POLL = 0.5                # seconds between looks for the "Lv." text
LEVEL_POLLS = 12                # looks per attempt
SAME_SPOT = 3                   # pixels the "Lv." may differ between two looks and still count as still
CONTINUE_DELAY = 0.7            # seconds between selecting the character and pressing Continue
CONTINUE_RETRY_AFTER = 6        # seconds before Continue Adventure is pressed again
LOAD_TIMEOUT = 150              # seconds the world may take to load after Continue Adventure
WORLD_RECHECK = 0.5             # seconds to look again before acting in the game world
FAST_MISS_LIMIT = 4             # quick reads in a row that may find nothing before a full read is done
MAX_RESIZES = 4
MAX_MISFITS = 6                 # times in a row the window may need re-fitting before giving up
MAX_UNKNOWN = 60                # unrecognised looks (about a second apart) before the bot gives up
MAX_POPUPS = 12
MAX_MENU_ESC = 20
MAX_MENU_CLOSE = 3


class CharacterState:
    """What the stages have already done. The screen itself stays the source of truth."""

    def __init__(self):
        self.use_strip = False        # the quick bottom-strip read is used once the game has got past the title
        self.fast_misses = 0
        self.resizes = 0
        self.misfits = 0
        self.character_selected = False   # the first character was clicked; retries only press Continue
        self.continue_clicked_at = None
        self.unknown_count = 0
        self.popups_closed = 0
        self.world_stable = False     # the world markers were seen once and are being checked a second time
        self.menu_esc = 0
        self.menu_seen = False        # the Game Menu was opened by us and still has to be closed
        self.menu_close_tries = 0
        self.ready = False


def _rect_of(word):
    return word.x, word.y, word.x + word.w, word.y + word.h


def _same_spot(a, b, tolerance=SAME_SPOT):
    """True when two rectangles (left, top, right, bottom) sit at the same place, give or take a few pixels."""
    return all(abs(p - q) <= tolerance for p, q in zip(a, b))


def _continue_button(words):
    """Rectangle of the "Continue Adventure" text, which OCR reads as two lines. Only used to
    recognise the character screen; the button itself is pressed by its fixed position."""
    hits = vision.find_phrases(words, "continue adventure")
    if hits:
        return hits[0]
    first, second = vision.find_phrases(words, "continue"), vision.find_phrases(words, "adventure")
    if first and second:
        a, b = first[0], second[0]
        return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])
    return None


def _find_level(bot, hwnd):
    """Looks for the "Lv." text of the first character, and only in the small area where it sits.
    Reading just that area is quick, and nothing else on the screen can be mistaken for it."""
    rect = winutil.get_rect(hwnd)
    words = vision.ocr_words(bot, vision.region(rect, *LEVEL_AREA), "both")
    found = [w for w in words if re.fullmatch(r"lv\w{0,3}", vision.norm(w.text))]
    return min(found, key=lambda w: w.y) if found else None


def _level_center(word):
    """The middle of the "Lv." letters themselves. OCR may read "Lv.94" as one word, and the
    middle of that whole word would land on the number."""
    text = word.text.strip()
    share = min(3, len(text)) / max(len(text), 1)
    return int(word.x + word.w * share / 2), int(word.y + word.h / 2)


def _press_escape(bot, hwnd):
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.1, 0.2))
    inputs.press_escape(bot)
    bot.sleep(random.uniform(0.4, 0.6))


def _click_phrase(bot, hwnd, words, phrase):
    hits = vision.find_phrases(words, phrase)
    if not hits:
        return False
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.1, 0.2))
    inputs.click_rect(bot, hwnd, hits[0])
    return True


def _find_popup_x(bot, rect):
    hits, _ = vision.find_image(bot, vision.region(rect, *CLOSE_X_AREA), CLOSE_X_ICON,
                                CLOSE_X_THRESHOLD, rect[2] / CLOSE_X_REF_WIDTH)
    return hits[0] if hits else None


def _reward_popup(words, rect):
    """The full-width "Congrats" reward window (shown after being offline, for example).
    Escape cannot close it, only a click can. Returns where to click, or None when it is not showing.
    The "Tap blank area to close" text is the backup marker when OCR misses the title."""
    x, y, w, h = rect
    left, top = x + w * CONGRATS_AREA[0], y + h * CONGRATS_AREA[1]
    right, bottom = x + w * CONGRATS_AREA[2], y + h * CONGRATS_AREA[3]
    for hit in vision.find_phrases(words, "congrats"):
        if left <= (hit[0] + hit[2]) / 2 <= right and top <= (hit[1] + hit[3]) / 2 <= bottom:
            return hit
    if scene.has(words, "tap blank area"):
        cx, cy = int(x + w * 0.5), int(y + h * 0.36)
        return cx - 40, cy - 15, cx + 40, cy + 15
    return None


def _close_reward_popup(bot, hwnd, rect, words, st):
    """Clicks the reward window away. Returns True when it was showing."""
    popup = _reward_popup(words, rect)
    if not popup:
        return False
    st.unknown_count = 0
    st.fast_misses = 0
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.1, 0.2))
    inputs.click_rect(bot, hwnd, popup, jitter=0.15)
    bot.log("Reward window (Congrats) closed with a click.")
    bot.sleep(random.uniform(0.6, 0.9))
    return True


# ----- Recent News and the title screen -----
def _read_area(bot, hwnd, area):
    """OCR of one small part of the game window. This is much quicker than reading the whole window."""
    return vision.ocr_words(bot, vision.region(winutil.get_rect(hwnd), *area), "both")


def _news_showing(words):
    return scene.has(words, "recent news") or any(vision.norm(w.text) in ("news", "recentnews") for w in words)


def _tap_showing(words):
    return any(vision.norm(w.text).startswith("tap") for w in words)


def _click_fraction(bot, hwnd, point):
    """Clicks a fixed point of the game window, exactly. Returns the screen position."""
    left, top, width, height = winutil.get_rect(hwnd)
    x, y = left + round(width * point[0]), top + round(height * point[1])
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.1, 0.2))
    inputs.click_point(bot, hwnd, x, y)
    return x, y


def _tap_screen(bot, hwnd):
    x, y = _click_fraction(bot, hwnd, TAP_POINT)
    bot.log(f"Title screen: tapped the screen at x={x}, y={y}.")
    bot.sleep(random.uniform(0.8, 1.2))


def _title_screens(bot, hwnd, st):
    """Closes the Recent News window and taps the title screen. Returns True when it did something."""
    if _news_showing(_read_area(bot, hwnd, NEWS_AREA)):
        x, y = _click_fraction(bot, hwnd, NEWS_CLOSE)
        bot.log(f"Recent News closed with its X button at x={x}, y={y}.")
        st.unknown_count = 0
        for _ in range(TAP_POLLS):
            bot.sleep(TAP_POLL)
            if _tap_showing(_read_area(bot, hwnd, TAP_AREA)):
                _tap_screen(bot, hwnd)
                break
        return True
    if _tap_showing(_read_area(bot, hwnd, TAP_AREA)):
        st.unknown_count = 0
        _tap_screen(bot, hwnd)
        return True
    return False


# ----- character select -----
def _select_first_character(bot, hwnd, st):
    """Finds the first character's "Lv." and clicks its centre once it has held still.
    It looks every half second. The text must be found at the same place twice in a row, so a
    moving or animated screen never causes a click on the wrong spot. If it cannot be seen after
    two looks, the game window is probably not fitted (the game can switch itself to full screen
    while loading), so the window is fitted again and the search carries on."""
    winutil.activate(hwnd)
    previous, missing, refitted = None, 0, False
    for _ in range(LEVEL_POLLS):
        word = _find_level(bot, hwnd)
        if word is None:
            previous = None
            missing += 1
            if missing == 2 and not refitted:
                refitted = True
                st.resizes += 1
                if st.resizes > MAX_RESIZES:
                    raise StepFailed("The character list is still not visible after fitting the window.")
                bot.log(f"Continue Adventure is visible but Lv. is not. Fitting the game window again "
                        f"({st.resizes}/{MAX_RESIZES})...", "WARN")
                game.arrange(bot)
        else:
            if previous is not None and _same_spot(_rect_of(word), _rect_of(previous)):
                x, y = _level_center(word)
                inputs.click_point(bot, hwnd, x, y)
                st.character_selected = True
                st.resizes = 0
                bot.log(f"First character selected: Lv. at x={x}, y={y}.")
                return True
            previous = word
        bot.sleep(LEVEL_POLL)
    return False


def _character_select(bot, hwnd, st):
    if st.continue_clicked_at is not None and time.monotonic() - st.continue_clicked_at < CONTINUE_RETRY_AFTER:
        bot.sleep(1.0)  # the button was just pressed, give the game time to react
        return

    if not st.character_selected:
        if not _select_first_character(bot, hwnd, st):
            return  # not found this time, the next pass starts again
        bot.sleep(CONTINUE_DELAY)

    # Continue Adventure always sits at the same place, so it is clicked by position.
    left, top, width, height = winutil.get_rect(hwnd)
    x, y = left + round(width * CONTINUE_POINT[0]), top + round(height * CONTINUE_POINT[1])
    winutil.activate(hwnd)
    inputs.click_point(bot, hwnd, x, y, hover_ms=150)
    st.continue_clicked_at = time.monotonic()
    bot.log(f"Continue Adventure clicked at x={x}, y={y}. Waiting for the game world...")


# ----- game world -----
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
        bot.sleep(random.uniform(0.1, 0.2))
        inputs.click_rect(bot, hwnd, popup)
        st.popups_closed += 1
        bot.log(f"Pop-up closed with its X button (#{st.popups_closed}).")
        bot.sleep(random.uniform(0.5, 0.8))
        st.menu_seen = False
        st.world_stable = False
        return

    if not st.world_stable:
        # The world markers are showing and no X button is in sight. Look once more half a second
        # later before acting, in case a pop-up is still sliding in.
        st.world_stable = True
        bot.sleep(WORLD_RECHECK)
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
    bot.sleep(0.2)  # the menu slides in, it is read on the next look


def _misfitted(bot, hwnd):
    """True when the game window is not inside the area reserved for it, for example after the
    game switched itself to full screen and now covers the console."""
    left, top, width, height = winutil.get_rect(hwnd)
    ax, ay, aw, ah = bot.area
    return (winutil.is_maximized(hwnd) or left < ax - 8 or top < ay - 8
            or left + width > ax + aw + 8 or top + height > ay + ah + 8)


def _refit_if_needed(bot, hwnd, st):
    """Fits the window again before anything is read or clicked. Returns True when it did."""
    if not _misfitted(bot, hwnd):
        st.misfits = 0
        return False
    st.misfits += 1
    if st.misfits > MAX_MISFITS:
        raise StepFailed("The game window cannot be fitted next to the console.")
    bot.log("The game window is out of place (full screen?). Fitting it again...", "WARN")
    game.arrange(bot)
    bot.sleep(0.5)
    return True


def _cancel_dialog(bot, hwnd, words):
    """Cancels a "Return to login screen?" style confirmation if one is ever open.
    Cancel keeps the game where it is. Returns True when a dialog was cancelled."""
    asking = scene.has(words, "return to login") or (scene.has(words, "cancel") and scene.has(words, "confirm"))
    if asking and _click_phrase(bot, hwnd, words, "cancel"):
        bot.log("A confirmation dialog was open. Cancel clicked.", "WARN")
        bot.sleep(random.uniform(0.5, 0.8))
        return True
    return False


def advance(bot, hwnd, st):
    """Looks at the screen once and performs the next step towards the game world."""
    if winutil.is_minimized(hwnd):
        winutil.restore(hwnd)
        bot.sleep(0.5)

    # The game can switch itself to full screen while loading. Fit it again before reading anything.
    if _refit_if_needed(bot, hwnd, st):
        return

    # Recent News and the title screen come first, before the character screen has been reached.
    if not st.use_strip and _title_screens(bot, hwnd, st):
        return

    # Quick read of the bottom strip, used once the game has got past the title screen.
    if st.use_strip:
        rect, words = scene.read_strip(bot, hwnd)
        if _close_reward_popup(bot, hwnd, rect, words, st):
            return
        if _cancel_dialog(bot, hwnd, words):
            return
        if _continue_button(words):
            st.fast_misses = st.unknown_count = 0
            return _character_select(bot, hwnd, st)
        if scene.menu_open(words) or scene.in_game(words):
            st.fast_misses = st.unknown_count = 0
            return _game_world(bot, hwnd, rect, words, st)
        loading = (st.continue_clicked_at is not None and
                   time.monotonic() - st.continue_clicked_at < LOAD_TIMEOUT)
        if loading and st.fast_misses < FAST_MISS_LIMIT:
            st.fast_misses += 1
            bot.sleep(1.0)   # nothing new yet: look again in one second
            return
        st.fast_misses = 0   # nothing familiar for a while: do one full read below

    # Full read of the whole window.
    rect, words = scene.read(bot, hwnd)

    if _close_reward_popup(bot, hwnd, rect, words, st):
        return

    if _cancel_dialog(bot, hwnd, words):
        return

    if _continue_button(words):
        st.use_strip = True
        st.unknown_count = 0
        return _character_select(bot, hwnd, st)

    if scene.has(words, "tap the screen"):
        st.unknown_count = 0
        _click_phrase(bot, hwnd, words, "tap the screen")
        bot.log("Title screen: tapped the screen.")
        bot.sleep(random.uniform(0.8, 1.2))
        return

    # The Game Menu covers the HUD markers, so it has to be checked before the HUD itself.
    if scene.menu_open(words) or scene.in_game(words):
        st.use_strip = True
        st.unknown_count = 0
        return _game_world(bot, hwnd, rect, words, st)

    # Loading or unknown screen.
    loading = (st.continue_clicked_at is not None and
               time.monotonic() - st.continue_clicked_at < LOAD_TIMEOUT)
    if loading:
        bot.sleep(1.0)
        return
    st.unknown_count += 1
    if st.unknown_count > MAX_UNKNOWN:
        raise StepFailed("The game screen could not be recognised.")
    seen = " ".join(w.text for w in words)[:90]
    # Screens change and animate, so an unknown one is simply waited out. No key is pressed.
    bot.log(f"Screen not recognised yet ({st.unknown_count}). Waiting. Text read: {seen}", "WARN")
    bot.sleep(1.0)