"""Account login through the launcher.

Flow:
  1. Wait until the launcher shows its Launch Game button, then look for the account icon.
     - Icon present  -> an account is signed in: open it and choose Switch Account.
     - Icon missing  -> click Launch Game, which opens the login window.
  2. Enter the account and password from Accounts.ini and click Log In.
  3. After a switch the launcher does not start the game by itself, so wait for the login
     window to close and click Launch Game.
  4. Wait for the game window and fit it next to the console.
"""
import configparser
import os
import random
from pathlib import Path

from PIL import Image

import actions
import game
import inputs
import vision
import winutil
from errors import StepFailed

BASE = Path(__file__).parent
ACCOUNTS_FILE = BASE / "Accounts.ini"
ACCOUNT_ICON = BASE / "assets" / "account_icon.png"
ICON_REF_WIDTH = 1440      # launcher width at the time the icon picture was captured
ICON_THRESHOLD = 0.8       # the real icon scores about 1.0, look-alike icons only about 0.5
ICON_AREA = (0.45, 0.04, 0.95, 0.17)     # top-right of the launcher, as fractions of its size
LAUNCH_AREA = (0.68, 0.82, 0.99, 0.96)   # where the Launch Game button sits
STEP_TIMEOUT = 20          # seconds to wait for each login-window change
POLL = 0.7                 # seconds between checks


def load_account():
    """Reads the first account (section [1]) from Accounts.ini."""
    cfg = configparser.ConfigParser(interpolation=None)  # no interpolation, passwords may contain '%'
    if not ACCOUNTS_FILE.exists():
        raise StepFailed(f"Accounts.ini not found: {ACCOUNTS_FILE}")
    raw = ACCOUNTS_FILE.read_bytes()
    try:
        # Ini files may be saved as UTF-16 (BOM at the start) or as UTF-8.
        text = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise StepFailed("Accounts.ini could not be read. Save it as UTF-8 or UTF-16.")
    cfg.read_string(text)
    account = cfg.get("1", "Account", fallback="").strip()
    password = cfg.get("1", "Password", fallback="")
    if not account or not password:
        raise StepFailed("Accounts.ini needs an Account and Password in section [1].")
    return account, password


def _check_files():
    """Fails early, with a clear message, when a required resource is missing or unsuitable."""
    for path in (ACCOUNT_ICON, vision.OCR_SCRIPT, vision.IMAGE_SCRIPT):
        if not path.exists():
            raise StepFailed(f"{path.name} not found: {path}")
    with Image.open(ACCOUNT_ICON) as icon:
        if icon.width < 25:
            raise StepFailed(f"account_icon.png is only {icon.width}x{icon.height}. "
                             f"Replace it with the 33x32 crop of the account icon.")


# What the last launcher scan saw. Only used to produce a helpful error message.
_seen = {"found": False, "region": None, "words": []}


def _launcher_words(bot, area=(0.0, 0.0, 1.0, 1.0)):
    """Runs OCR on the launcher, or on a part of it given as fractions.
    Returns (hwnd, rect, words), or None when the launcher is not on screen."""
    hwnd = winutil.find_launcher_window(skip_pid=os.getpid())
    _seen["found"] = bool(hwnd)
    if not hwnd:
        return None
    rect = winutil.get_rect(hwnd)
    box = vision.region(rect, *area)
    words = vision.ocr_words(bot, box)
    _seen["region"], _seen["words"] = box, [w.text for w in words]
    return hwnd, rect, words


def find_launch_button(words):
    """Bounding box of the 'Launch' and 'Game' words as (left, top, right, bottom), or None.
    One of the two words is enough: the button is large, so clicking either lands on it."""
    launch = game_word = None
    for w in words:
        text = w.text.lower()
        if "launch" in text:
            launch = w
        if "game" in text:
            game_word = w
    found = [w for w in (launch, game_word) if w]
    if not found:
        return None
    return (min(w.x for w in found), min(w.y for w in found),
            max(w.x + w.w for w in found), max(w.y + w.h for w in found))


def _launch_button(bot):
    got = _launcher_words(bot, LAUNCH_AREA)
    return find_launch_button(got[2]) if got else None


def click_launch_game(bot):
    hwnd = winutil.find_launcher_window(skip_pid=os.getpid())
    if not hwnd:
        raise StepFailed("Launcher window not found.")
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.25, 0.5))
    got = _launcher_words(bot, LAUNCH_AREA)  # fresh scan, so the click uses the button's current position
    button = find_launch_button(got[2]) if got else None
    if not button:
        raise StepFailed("Launch Game text was not found. Click not sent.")
    inputs.click_rect(bot, got[0], button)


def locate_fields(words, rect):
    """Works out where the account field, the password field and the Log In button are.

    The 'Remember Me' text and the 'Log In' button text are used as anchors. The offsets were
    measured on a launcher about 1180 px wide and are scaled to the actual window size.
    Returns a dict of screen positions, or None if the anchor text is missing."""
    remember = vision.find_phrases(words, "remember")
    if not remember:
        return None
    wx, wy, ww, wh = rect
    r_left, r_top, r_right, r_bottom = remember[0]
    remember_y = (r_top + r_bottom) / 2
    scale = ww / 1180
    login_y = remember_y + 87 * scale

    # Refine the scale from the real Log In text: the nearest match below 'Remember Me' on the left half.
    nearest = 0
    for l, t, r, b in vision.find_phrases(words, "log in"):
        cx, cy = (l + r) / 2, (t + b) / 2
        if cx > wx + ww * 0.45 or cy <= remember_y + 20 * scale:
            continue
        if nearest == 0 or cy < nearest:
            nearest = cy
    if nearest > 0:
        measured = (nearest - remember_y) / 87
        if 0.5 < measured < 2:
            scale, login_y = measured, nearest

    x = int(r_left + 140 * scale)
    return {"account": (x, int(remember_y - 114 * scale)),
            "password": (x, int(remember_y - 52 * scale)),
            "login": (x, int(login_y)),
            "scale": scale}


def _fill_field(bot, hwnd, x, y, text):
    """Double-clicks a field, clears it, and types the new value."""
    inputs.click_point(bot, hwnd, x + random.randint(-40, 40), y + random.randint(-5, 5), clicks=2)
    bot.sleep(random.uniform(0.15, 0.3))
    inputs.press_ctrl_a(bot)
    bot.sleep(random.uniform(0.06, 0.14))
    inputs.press_delete(bot)
    bot.sleep(random.uniform(0.1, 0.2))
    inputs.type_text(bot, text)


def _enter_credentials(bot, got, account, password):
    hwnd, rect, words = got
    pos = locate_fields(words, rect)
    if not pos:
        raise StepFailed("Could not locate the login fields.")
    bot.log(f"Login fields located (scale {pos['scale']:.2f}): "
            f"account {pos['account']}, password {pos['password']}, Log In {pos['login']}.")

    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.15, 0.3))
    _fill_field(bot, hwnd, *pos["account"], account)
    bot.sleep(random.uniform(0.25, 0.5))
    _fill_field(bot, hwnd, *pos["password"], password)
    bot.sleep(random.uniform(0.25, 0.5))
    lx, ly = pos["login"]
    inputs.click_point(bot, hwnd, lx + random.randint(-25, 25), ly + random.randint(-5, 5))


# ---------- individual steps ----------
def _wait_launcher_ready(bot):
    bot.log("Waiting for the launcher to finish loading...")
    if not bot.wait_until(lambda: _launch_button(bot), 60, POLL):
        if not _seen["found"]:
            raise StepFailed("The launcher window was not found (title 'Ragnarok The New World'). "
                             "Is it minimized or hidden?")
        read = " ".join(_seen["words"])[:150] or "(nothing)"
        raise StepFailed(f"The Launch Game button was not read. Scanned area {_seen['region']}; text read: {read}")


def _find_account_icon(bot):
    """Returns the icon's rectangle when an account is signed in, otherwise None."""
    hwnd = winutil.find_launcher_window(skip_pid=os.getpid())
    if not hwnd:
        raise StepFailed("Launcher window not found.")
    winutil.activate(hwnd)
    bot.sleep(random.uniform(0.25, 0.5))
    rect = winutil.get_rect(hwnd)
    hits, score = vision.find_image(bot, vision.region(rect, *ICON_AREA), ACCOUNT_ICON,
                                    ICON_THRESHOLD, rect[2] / ICON_REF_WIDTH)
    if hits:
        bot.log(f"Account icon found (match {score:.2f}): an account is logged in.")
        return hits[0]
    bot.log(f"No account icon (best match {score:.2f}): no account is logged in.")
    return None


def _open_switch_account(bot, icon_rect):
    hwnd = winutil.find_launcher_window(skip_pid=os.getpid())
    if not hwnd:
        raise StepFailed("Launcher window not found.")
    inputs.click_rect(bot, hwnd, icon_rect)
    bot.log("Account icon clicked. Waiting for the account details...")

    def details():
        got = _launcher_words(bot)
        if not got:
            return None
        hits = vision.find_phrases(got[2], "switch account")
        return (got[0], hits[0]) if hits else None

    found = bot.wait_until(details, STEP_TIMEOUT, POLL)
    if not found:
        raise StepFailed("The account details did not appear.")
    inputs.click_rect(bot, found[0], found[1])
    bot.log("Switch Account clicked. Waiting for the login window...")


def _wait_login_window(bot, switching):
    """Waits for the login window. Returns (hwnd, rect, words), or None when the game
    opened without showing a login window."""
    def check():
        if not switching and winutil.find_game_window(os.getpid()):
            return "GAME"
        got = _launcher_words(bot)
        if not got:
            return None
        words = got[2]
        if switching:
            ok = bool(vision.find_phrases(words, "remember"))
        else:
            ok = bool(vision.find_phrases(words, "enter account")) and \
                 bool(vision.find_phrases(words, "enter password"))
        return got if ok else None

    result = bot.wait_until(check, STEP_TIMEOUT, POLL)
    if result is None:
        raise StepFailed("The login window did not appear.")
    return None if result == "GAME" else result


def _wait_login_closed(bot):
    """After Log In: wait until the login window is gone and the Launch Game button is back."""
    def check():
        got = _launcher_words(bot)
        if not got:
            return None
        if vision.find_phrases(got[2], "remember"):
            return None
        return bool(vision.find_phrases(got[2], "launch game"))

    if not bot.wait_until(check, STEP_TIMEOUT, POLL):
        raise StepFailed("The login window did not close. The login may have failed.")


def run(bot):
    """Runs the complete login flow for the first account in Accounts.ini."""
    account, password = load_account()
    _check_files()
    bot.set_action(actions.logging_in(account))
    bot.log(f"Account to use: {account}")

    _wait_launcher_ready(bot)
    icon_rect = _find_account_icon(bot)
    switching = icon_rect is not None

    if switching:
        _open_switch_account(bot, icon_rect)
    else:
        click_launch_game(bot)
        bot.log("Launch Game clicked. Waiting for the login window...")

    got = _wait_login_window(bot, switching)
    if got is None:
        bot.log("The game opened without a login window. An account was probably already "
                "logged in; check account_icon.png.", "WARN")
    else:
        bot.log("Login window detected.")
        _enter_credentials(bot, got, account, password)
        del password  # the secret is no longer needed once it has been typed
        if switching:
            bot.log("Account and password entered. Log In clicked. Waiting for the login window to close...")
            _wait_login_closed(bot)
            bot.log("Login window closed. Clicking Launch Game...")
            bot.sleep(random.uniform(0.4, 0.8))
            click_launch_game(bot)
            bot.log("Launch Game clicked. Waiting for the game to open...")
        else:
            bot.log("Account and password entered. Log In clicked. Waiting for the game to open...")

    game.prepare(bot)