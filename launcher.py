"""Opening the game launcher and placing it next to the console."""
import os
import subprocess

import winutil
from errors import StepFailed


def is_running():
    """True if the launcher process already exists, so a second copy is never opened."""
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {winutil.LAUNCHER_EXE}", "/NH"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout
    return out.strip() != "" and "no tasks" not in out.lower()


def start(exe_path):
    """Starts the launcher the same way a double-click would."""
    subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))


def open_and_arrange(bot, exe_path):
    """Opens the launcher if needed and fits it into the area to the right of the console."""
    if is_running():
        bot.log("RONW is already running. Not opening a second one.")
    else:
        try:
            start(exe_path)
        except OSError as err:
            raise StepFailed(f"Could not open the launcher: {err}. "
                             f"Delete the \"launcher_path\" line in settings.json to choose it again.")
        bot.log("Launcher opened. Waiting for its window...", "OK")

    hwnd = bot.wait_until(
        lambda: winutil.find_window(winutil.LAUNCHER_EXE, winutil.LAUNCHER_CLASS, "ragnarok"), 60, 0.5)
    if not hwnd:
        raise StepFailed("The launcher window did not appear within 60 seconds.")

    bot.sleep(1.0)  # give the window a moment to finish drawing
    x, y, w, h = bot.area
    fx, fy, fw, fh = winutil.fit_window(hwnd, x, y, w, h)
    bot.log(f"Launcher placed at x={fx} y={fy} size={fw}x{fh}.", "OK")