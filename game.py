"""Waiting for the game window and fitting it next to the console."""
import os

import inputs
import winutil
from errors import StepFailed

GAME_TIMEOUT = 240      # seconds to wait for the game to open
FULLSCREEN_WAIT = 4     # seconds the game gets to leave full screen after a switch


def wait_for_window(bot):
    hwnd = bot.wait_until(lambda: winutil.find_game_window(os.getpid()), GAME_TIMEOUT, 0.7)
    if not hwnd:
        raise StepFailed("The game did not open in time. The login may have failed.")
    bot.log(f"Main game window detected: {winutil.describe(hwnd)}")
    return hwnd


def _game_hwnd():
    return winutil.find_game_window(os.getpid())


def _wait_windowed(bot, seconds):
    """Waits until the game window is not full screen any more. Returns its handle, or None.
    The window is looked up again each time, because a mode switch can recreate it."""
    def check():
        hwnd = _game_hwnd()
        return hwnd if hwnd and not winutil.is_fullscreen(hwnd) else None
    return bot.wait_until(check, seconds, 0.5)


def ensure_windowed(bot, hwnd):
    """Turns a full-screen game into a window and returns the window handle.
    Tries, in order: restoring a maximised window, Alt+Enter, and giving a borderless window its frame back."""
    if winutil.is_minimized(hwnd) or winutil.is_maximized(hwnd):
        winutil.restore(hwnd)
        bot.sleep(0.4)
    if not winutil.is_fullscreen(hwnd):
        return hwnd
    bot.sleep(1.0)   # a window that is still opening can look borderless for a moment
    hwnd = _game_hwnd() or hwnd
    if not winutil.is_fullscreen(hwnd):
        return hwnd

    bot.log("The game is in full screen. Switching it to windowed mode (Alt+Enter)...", "WARN")
    winutil.activate(hwnd)
    bot.sleep(0.4)
    inputs.press_alt_enter(bot)
    found = _wait_windowed(bot, FULLSCREEN_WAIT)
    if found:
        bot.log("The game is windowed now.", "OK")
        return found

    bot.log("Alt+Enter did not switch it. Restoring the window frame directly...", "WARN")
    hwnd = _game_hwnd() or hwnd
    winutil.force_windowed(hwnd)
    found = _wait_windowed(bot, 2.0)
    if found:
        bot.log("The game is windowed now.", "OK")
        return found
    raise StepFailed("The game stays in full screen. Switch it to windowed mode in the game settings.")


def arrange(bot, quiet=False):
    """Makes sure the game runs windowed and fits it to the whole area right of the console.
    Every position and area used by the automation is a fraction of this window size."""
    # The game can briefly recreate its window while loading, so allow a few seconds to find it again.
    hwnd = bot.wait_until(lambda: winutil.find_game_window(os.getpid()), 10, 0.5)
    if not hwnd:
        raise StepFailed("The game window disappeared. Visible windows: " + winutil.describe_windows())
    hwnd = ensure_windowed(bot, hwnd)

    x, y, area_w, area_h = bot.area
    fx, fy, fw, fh = winutil.fit_window(hwnd, x, y, area_w, area_h)
    if not quiet:
        view_w, view_h = winutil.client_size(hwnd)
        bot.log(f"Game window placed at x={fx} y={fy} size={fw}x{fh} (game view {view_w}x{view_h}).", "OK")
    return True


def prepare(bot):
    """Waits for the game, then arranges it twice a few seconds apart, because the window settles after opening."""
    hwnd = wait_for_window(bot)
    ensure_windowed(bot, hwnd)   # a game left in full screen is switched to a window right away
    bot.sleep(1.5)
    arrange(bot, quiet=True)
    bot.sleep(3.0)
    arrange(bot)
    bot.log("Game window is ready.", "OK")