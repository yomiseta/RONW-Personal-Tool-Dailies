"""Keeps the lines shown in the console and saves them to a text file when a run ends."""
from datetime import datetime
from pathlib import Path

FOLDER = Path(__file__).parent / "Logs"


class LogFile:
    def __init__(self):
        self.lines = []

    def add(self, message):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.lines.append(f"[{stamp}] {message}")

    def save(self):
        """Writes the lines to Logs/yyyy_mm_dd_hhmm.txt and returns the path.
        If a file with that name exists (two runs in the same minute), _2, _3... is added."""
        if not self.lines:
            return None
        FOLDER.mkdir(exist_ok=True)
        base = datetime.now().strftime("%Y_%m_%d_%H%M")
        path = FOLDER / f"{base}.txt"
        number = 2
        while path.exists():
            path = FOLDER / f"{base}_{number}.txt"
            number += 1
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        return path