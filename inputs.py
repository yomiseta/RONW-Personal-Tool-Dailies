"""Real mouse and keyboard input through the Windows SendInput API.

The pointer jumps straight to its target instead of gliding, and every click lands on a
slightly different point with a slightly different timing.
"""
import ctypes
import random
import time
from ctypes import wintypes

import winutil
from errors import StepFailed

user32 = ctypes.windll.user32
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
VK_CONTROL, VK_A, VK_DELETE, VK_ESCAPE = 0x11, 0x41, 0x2E, 0x1B
VK_W, VK_MENU, VK_RETURN = 0x57, 0x12, 0x0D   # W, Alt, Enter


def _send(inputs):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _mouse(flags):
    return INPUT(INPUT_MOUSE, _INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, flags, 0, 0)))


def _key(vk, up=False):
    return INPUT(INPUT_KEYBOARD, _INPUT_UNION(ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)))


def click_point(bot, hwnd, x, y, clicks=1, hover_ms=0):
    """Moves the pointer to (x, y) and clicks.
    Raises StepFailed if another window is on top of that spot, so we never click the wrong program."""
    bot.checkpoint()
    if winutil.root_window_at(x, y) != hwnd:
        raise StepFailed("Another window covers the click spot. Move it away and press START again.")
    user32.SetCursorPos(int(x), int(y))
    if hover_ms > 0:
        bot.sleep(random.uniform(hover_ms, hover_ms + 80) / 1000)
    else:
        bot.sleep(random.uniform(40, 90) / 1000)
    for i in range(clicks):
        _send([_mouse(MOUSEEVENTF_LEFTDOWN)])
        # A plain sleep on purpose: pausing here must never leave the button held down.
        time.sleep(random.uniform(55, 130) / 1000)
        _send([_mouse(MOUSEEVENTF_LEFTUP)])
        if i < clicks - 1:
            time.sleep(random.uniform(40, 80) / 1000)


def click_rect(bot, hwnd, rect, clicks=1, jitter=0.2, hover_ms=0):
    """Clicks near the middle of rect = (left, top, right, bottom).
    `jitter` is the random offset as a share of the rectangle size."""
    left, top, right, bottom = rect
    w, h = right - left, bottom - top
    x = (left + right) / 2 + random.uniform(-w * jitter, w * jitter)
    y = (top + bottom) / 2 + random.uniform(-h * jitter, h * jitter)
    click_point(bot, hwnd, int(x), int(y), clicks, hover_ms)


def press_ctrl_a(bot):
    _send([_key(VK_CONTROL), _key(VK_A), _key(VK_A, True), _key(VK_CONTROL, True)])


def press_delete(bot):
    _send([_key(VK_DELETE), _key(VK_DELETE, True)])
    

def press_escape(bot):
    """Taps the Escape key, with a short random hold like a real key press."""
    bot.checkpoint()
    _send([_key(VK_ESCAPE)])
    time.sleep(random.uniform(45, 110) / 1000)
    _send([_key(VK_ESCAPE, True)])


def press_key(bot, vk, hold_ms=(45, 110)):
    """Taps a key once, with a short random hold like a real key press."""
    bot.checkpoint()
    _send([_key(vk)])
    time.sleep(random.uniform(*hold_ms) / 1000)
    _send([_key(vk, True)])


def press_alt_enter(bot):
    """Alt+Enter, which switches the game between full screen and windowed mode."""
    bot.checkpoint()
    _send([_key(VK_MENU)])
    time.sleep(random.uniform(60, 120) / 1000)
    _send([_key(VK_RETURN)])
    time.sleep(random.uniform(60, 120) / 1000)
    _send([_key(VK_RETURN, True)])
    time.sleep(random.uniform(40, 90) / 1000)
    _send([_key(VK_MENU, True)])
    

def type_text(bot, text):
    """Types the whole text into the focused field in a single SendInput call.
    Unicode key events are used, so the clipboard is never touched."""
    bot.checkpoint()
    data = text.encode("utf-16-le")
    units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
    events = []
    for unit in units:
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            events.append(INPUT(INPUT_KEYBOARD, _INPUT_UNION(ki=KEYBDINPUT(0, unit, flags, 0, 0))))
    if events:
        _send(events)
    bot.sleep(random.uniform(150, 280) / 1000)