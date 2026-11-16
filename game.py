"""Waiting for the game window and fitting it next to the console."""
import os

import winutil
from errors import StepFailed

GAME_TIMEOUT = 240      # seconds to wait for the game to open
GAME_ASPECT = 16 / 9    # the game renders a fixed 16:9 picture and crops the view if the window has another shape
FILL_AREA = True       # True: use the whole free area and let the game crop its view; False: keep the full 16:9 picture


def wait_for_window(bot):
    hwnd = bot.wait_until(lambda: winutil.find_game_window(os.getpid()), GAME_TIMEOUT, 0.7)
    if not hwnd:
        raise StepFailed("The game did not open in time. The login may have failed.")
    bot.log(f"Main game window detected: {winutil.describe(hwnd)}")
    return hwnd


def _target_size(hwnd, area_w, area_h):
    """Largest window (outer size) with a 16:9 drawing area that fits inside the given area.
    The title bar and borders are measured from the live window instead of being hard-coded."""
    if FILL_AREA:
        return area_w, area_h
    _, _, frame_w, frame_h = winutil.get_rect(hwnd)
    client_w, client_h = winutil.client_size(hwnd)
    border_w, border_h = frame_w - client_w, frame_h - client_h
    view_w = min(area_w - border_w, (area_h - border_h) * GAME_ASPECT)
    view_h = view_w / GAME_ASPECT
    return int(view_w + border_w), int(view_h + border_h)


def arrange(bot, quiet=False):
    """Makes sure the game runs windowed and fits it into the area right of the console,
    keeping the game's own proportions so nothing is cropped."""
    # The game can briefly recreate its window while loading, so allow a few seconds to find it again.
    hwnd = bot.wait_until(lambda: winutil.find_game_window(os.getpid()), 10, 0.5)
    if not hwnd:
        raise StepFailed("The game window disappeared. Visible windows: " + winutil.describe_windows())
    if winutil.is_minimized(hwnd) or winutil.is_maximized(hwnd):
        winutil.restore(hwnd)
        bot.sleep(0.4)
    if not winutil.has_caption(hwnd):
        bot.log("The game does not look windowed (no title bar). "
                "Switch it to windowed mode in the game settings.", "WARN")
        return False

    x, y, area_w, area_h = bot.area
    width, height = _target_size(hwnd, area_w, area_h)
    fx, fy, fw, fh = winutil.fit_window(hwnd, x, y, width, height)
    if not quiet:
        view_w, view_h = winutil.client_size(hwnd)
        bot.log(f"Game window placed at x={fx} y={fy} size={fw}x{fh} (game view {view_w}x{view_h}).", "OK")
    return True


def prepare(bot):
    """Waits for the game, then arranges it twice a few seconds apart, because the window settles after opening."""
    wait_for_window(bot)
    bot.sleep(2.5)
    arrange(bot, quiet=True)
    bot.sleep(3.0)
    arrange(bot)
    bot.log("Game window is ready.", "OK")