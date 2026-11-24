"""Keeps the lines shown in the console and saves them, with a screenshot of the game, when a run ends."""
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

import winutil

FOLDER = Path(__file__).parent / "Logs"


class LogFile:
    def __init__(self):
        self.lines = []

    def add(self, message):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.lines.append(f"[{stamp}] {message}")

    def _names(self):
        """A file name shared by the log and its screenshot: yyyy_mm_dd_hhmm.
        If a file with that name exists (two runs in the same minute), _2, _3... is added."""
        base = datetime.now().strftime("%Y_%m_%d_%H%M")
        name, number = base, 1
        while (FOLDER / f"{name}.txt").exists() or (FOLDER / f"{name}.png").exists():
            number += 1
            name = f"{base}_{number}"
        return name

    def _screenshot(self, hwnd, path):
        """Saves a picture of the game window only. Returns True when it worked."""
        if hwnd is None:
            self.add("Screenshot: the game window was not open.")
            return False
        try:
            if winutil.is_minimized(hwnd):
                self.add("Screenshot: skipped, the game window is minimized.")
                return False
            left, top, width, height = winutil.get_rect(hwnd)
            ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True).save(path)
            return True
        except Exception as err:
            self.add(f"Screenshot: failed ({type(err).__name__}).")
            return False

    def save(self, game_hwnd=None):
        """Writes the screenshot first, so its file name is part of the log, then the log itself.
        Returns (log path, screenshot path or None), or None when there is nothing to save."""
        if not self.lines:
            return None
        FOLDER.mkdir(exist_ok=True)
        name = self._names()
        shot_path = FOLDER / f"{name}.png"
        if self._screenshot(game_hwnd, shot_path):
            self.add(f"Screenshot saved: {shot_path.name}")
        else:
            shot_path = None
        log_path = FOLDER / f"{name}.txt"
        log_path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        return log_path, shot_path