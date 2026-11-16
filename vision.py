"""Screen reading: OCR (text) and icon search.

Both run in small PowerShell helpers under tools/, which use the OCR engine built into Windows
and a mask-based template matcher. Screen coordinates are in physical pixels throughout.
"""
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from errors import Stopped, StepFailed

BASE = Path(__file__).parent
OCR_SCRIPT = BASE / "tools" / "RONW_OCR.ps1"
IMAGE_SCRIPT = BASE / "tools" / "RONW_FindImage.ps1"
SCRIPT_TIMEOUT = 20  # seconds before a helper is considered stuck


@dataclass
class Word:
    """A word recognised by OCR, with its bounding box in screen pixels."""
    text: str
    x: int
    y: int
    w: int
    h: int


def region(rect, fl, ft, fr, fb):
    """Converts a part of a window, given as fractions, into a screen area (x, y, w, h).
    `rect` is the window as (x, y, w, h)."""
    x, y, w, h = rect
    return (x + int(w * fl), y + int(h * ft), int(w * (fr - fl)), int(h * (fb - ft)))


def _run(script, args, bot):
    """Runs a PowerShell helper without a console window and returns its output.
    The helper is killed immediately if the user presses STOP."""
    if not script.exists():
        raise StepFailed(f"{script.name} not found. Put it in the 'tools' folder: {script}")
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    cmd += [str(a) for a in args]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
    started = time.monotonic()
    while True:
        if bot.stopping():
            proc.kill()
            raise Stopped()
        try:
            out, _ = proc.communicate(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            if time.monotonic() - started > SCRIPT_TIMEOUT:
                proc.kill()
                proc.communicate()
                raise StepFailed(f"{script.name} took too long and was stopped.")
    if "OCRERROR:" in out:
        raise StepFailed(out.strip())
    return out


def ocr_words(bot, area, mode="normal"):
    """Reads the text inside a screen area (x, y, w, h) and returns a list of Word."""
    x, y, w, h = area
    out = _run(OCR_SCRIPT, [x, y, w, h, mode], bot)
    words = []
    for line in out.splitlines():
        p = line.strip().split("|")
        if len(p) >= 6 and p[0] == "W":
            try:
                words.append(Word("|".join(p[1:-4]), int(p[-4]), int(p[-3]), int(p[-2]), int(p[-1])))
            except ValueError:
                pass
    return words


def find_image(bot, area, template, threshold, scale_hint, mask="white", max_matches=1):
    """Searches a screen area for a small template image.
    Returns (matches, best_score), where each match is (left, top, right, bottom)."""
    x, y, w, h = area
    out = _run(IMAGE_SCRIPT, [x, y, w, h, template, threshold, f"{scale_hint:.3f}", mask, max_matches], bot)
    hits, best, answered = [], 0.0, False
    for line in out.splitlines():
        p = line.strip().split("|")
        try:
            if p[0] == "IMG" and len(p) >= 6:
                left, top = int(p[1]), int(p[2])
                hits.append((left, top, left + int(p[3]), top + int(p[4])))
                if len(hits) == 1:
                    best = float(p[5])
                answered = True
            elif p[0] == "IMGNONE" and len(p) >= 2:
                best = float(p[1])
                answered = True
        except ValueError:
            pass
    if not answered:
        raise StepFailed("Icon search gave no answer: " + out.strip()[:200])
    return hits, best


def norm(text):
    """Lower-cases text and strips everything except letters and digits, to make OCR matching forgiving."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def find_phrases(words, phrase):
    """Finds a phrase made of consecutive words on one text line.
    Case and punctuation are ignored, and a multi-word phrase also matches when OCR
    merged it into a single word (for example "Login" for "log in").
    Returns a list of (left, top, right, bottom)."""
    tokens = [norm(t) for t in phrase.lower().split()]
    joined = norm(phrase)
    hits, n = [], len(words)
    for i in range(n):
        match, last = False, i
        if i + len(tokens) <= n:
            match = True
            for k, token in enumerate(tokens):
                if norm(words[i + k].text) != token:
                    match = False
                    break
                if k > 0:
                    # Words of one phrase must sit on the same line.
                    diff = abs((words[i + k].y + words[i + k].h / 2) - (words[i].y + words[i].h / 2))
                    if diff > words[i].h:
                        match = False
                        break
            if match:
                last = i + len(tokens) - 1
        if not match and len(tokens) > 1 and norm(words[i].text) == joined:
            match = True
        if match:
            left, top = words[i].x, words[i].y
            right = words[last].x + words[last].w
            bottom = top + words[i].h
            for m in range(i, last + 1):
                top = min(top, words[m].y)
                bottom = max(bottom, words[m].y + words[m].h)
            hits.append((left, top, right, bottom))
    return hits