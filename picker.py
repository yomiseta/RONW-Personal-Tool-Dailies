"""Coordinate picker: Shift+M reads a point, Shift+R reads a rectangle, Shift+C reads a colour.

Each key opens a see-through layer over the whole screen. The click or drag lands on that layer,
so the game never receives it, and the result is written to the log in screen pixels and as
fractions of the game window, which is the form the screen-reading code uses.

For the colour, the screen is captured before the layer opens, so the value is the real colour
of the game and not the colour darkened by the layer.
"""
import ctypes
import os
import tkinter as tk

from PIL import Image, ImageGrab

import winutil

user32 = ctypes.windll.user32
VK_SHIFT, VK_M, VK_R, VK_C = 0x10, 0x4D, 0x52, 0x43
POLL_MS = 40
MIN_DRAG = 4                 # pixels; a smaller drag is treated as a stray click
AVERAGE_RADIUS = 2           # the colour is also averaged over (2 * radius + 1) squared pixels
OUTLINE = "#00ff99"
TEXT_BOXES = ("Entry", "TEntry", "Text", "Spinbox", "TSpinbox")


def _down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _virtual_screen():
    """(left, top, width, height) of the whole desktop, including every monitor."""
    return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
            user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))


class Picker:
    def __init__(self, root, log, is_busy):
        self.root = root
        self.log = log              # callable: log(message, level)
        self.is_busy = is_busy      # callable: True while the automation is running
        self._was_down = {VK_M: False, VK_R: False, VK_C: False}
        self._overlay = None
        self._shot = None

    def start(self):
        self.log("Picker ready: Shift+M reads a point, Shift+R a rectangle, Shift+C a colour (Esc cancels).")
        self.root.after(POLL_MS, self._poll)

    # ----- hotkeys -----
    def _typing(self):
        """True while a text box has the keyboard or a dialog is open, so typing a capital
        letter there does not trigger the picker."""
        try:
            if self.root.grab_current() is not None:
                return True
            widget = self.root.focus_get()
        except (KeyError, tk.TclError):
            return False
        if widget is None or widget.winfo_class() not in TEXT_BOXES:
            return False
        try:
            return str(widget.cget("state")) != "disabled"   # the read-only log does not count
        except tk.TclError:
            return True

    def _poll(self):
        try:
            for vk, mode in ((VK_M, "point"), (VK_R, "rect"), (VK_C, "color")):
                pressed = _down(VK_SHIFT) and _down(vk)
                if pressed and not self._was_down[vk] and self._overlay is None and not self._typing():
                    if self.is_busy():
                        self.log("The picker is off while the automation runs. Press STOP first.", "WARN")
                    else:
                        self._open(mode)
                self._was_down[vk] = pressed
        finally:
            self.root.after(POLL_MS, self._poll)

    # ----- the see-through layer -----
    def _open(self, mode):
        left, top, width, height = _virtual_screen()
        self._shot = None
        if mode == "color":
            # Captured now, before the layer appears, so the colours are not tinted by it.
            try:
                self._shot = ImageGrab.grab(all_screens=True).convert("RGB")
            except Exception as err:
                self.log(f"The screen could not be captured: {type(err).__name__}.", "ERROR")
                return
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.3)
        win.geometry(f"{width}x{height}+{left}+{top}")
        canvas = tk.Canvas(win, bg="black", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        self._overlay = win
        self._origin = (left, top)
        self._start = None
        self._shape = None
        self._label = None

        if mode == "point":
            self.log("Click the point you want...")
            canvas.bind("<ButtonRelease-1>", self._finish_point)
        elif mode == "color":
            self.log("Click the point whose colour you want...")
            canvas.bind("<ButtonRelease-1>", self._finish_color)
        else:
            self.log("Drag the rectangle you want...")
            canvas.bind("<ButtonPress-1>", self._begin_drag)
            canvas.bind("<B1-Motion>", self._drag)
            canvas.bind("<ButtonRelease-1>", self._finish_rect)
        win.bind("<Escape>", lambda e: self._close("Picker cancelled."))
        win.focus_force()
        self._canvas = canvas

    def _close(self, message=None):
        if self._overlay is not None:
            self._overlay.destroy()
            self._overlay = None
        if message:
            self._shot = None
            self.log(message)

    # ----- point -----
    def _finish_point(self, event):
        x, y = event.x_root, event.y_root
        self._close()
        self.log(f"Point: x={x} y={y}", "OK")
        self._describe_point(x, y)

    # ----- colour -----
    def _finish_color(self, event):
        x, y = event.x_root, event.y_root
        shot, self._shot = self._shot, None
        ox, oy = self._origin
        self._close()
        px, py = x - ox, y - oy
        if shot is None or not (0 <= px < shot.width and 0 <= py < shot.height):
            self.log("That point is outside the captured screen. Press Shift+C and try again.", "WARN")
            return
        r, g, b = shot.getpixel((px, py))
        self.log(f"Colour at x={x} y={y}: RGB ({r}, {g}, {b})  hex #{r:02X}{g:02X}{b:02X}", "OK")

        # Average of the pixels around it, which is steadier on gradients and soft edges.
        box = (max(px - AVERAGE_RADIUS, 0), max(py - AVERAGE_RADIUS, 0),
               min(px + AVERAGE_RADIUS + 1, shot.width), min(py + AVERAGE_RADIUS + 1, shot.height))
        ar, ag, ab = shot.crop(box).resize((1, 1), Image.BOX).getpixel((0, 0))
        size = 2 * AVERAGE_RADIUS + 1
        self.log(f"  Average of {size}x{size} around it: RGB ({ar}, {ag}, {ab})  hex #{ar:02X}{ag:02X}{ab:02X}")
        self._describe_point(x, y)

    # ----- rectangle -----
    def _begin_drag(self, event):
        self._start = (event.x, event.y)

    def _drag(self, event):
        if self._start is None:
            return
        x1, y1 = self._start
        c = self._canvas
        if self._shape is None:
            self._shape = c.create_rectangle(x1, y1, event.x, event.y, outline=OUTLINE, width=2,
                                             fill="white", stipple="gray25")
            self._label = c.create_text(0, 0, fill=OUTLINE, anchor="sw", font=("Consolas", 10, "bold"))
        c.coords(self._shape, x1, y1, event.x, event.y)
        w, h = abs(event.x - x1), abs(event.y - y1)
        c.coords(self._label, min(x1, event.x), min(y1, event.y) - 4)
        c.itemconfigure(self._label, text=f"{w} x {h}")

    def _finish_rect(self, event):
        if self._start is None:
            return
        ox, oy = self._origin
        x1, y1 = self._start[0] + ox, self._start[1] + oy
        x2, y2 = event.x_root, event.y_root
        self._close()
        if abs(x2 - x1) < MIN_DRAG or abs(y2 - y1) < MIN_DRAG:
            self.log("That drag was too small. Press Shift+R and try again.", "WARN")
            return
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        self.log(f"Rectangle: start ({x1}, {y1}) end ({x2}, {y2}) size {right - left}x{bottom - top}", "OK")
        self._describe_rect(left, top, right, bottom)

    # ----- relative to the game window -----
    def _window(self):
        pid = os.getpid()
        hwnd = winutil.find_game_window(pid)
        if hwnd is not None and hwnd == winutil.find_launcher_window(pid):
            hwnd = None
        if hwnd is None:
            return None
        return winutil.get_rect(hwnd)

    def _describe_point(self, x, y):
        rect = self._window()
        if rect is None:
            self.log("No game window found, so only screen coordinates are shown.", "WARN")
            return
        wx, wy, ww, wh = rect
        self.log(f"  In the game window: +{x - wx}, +{y - wy} pixels = "
                 f"({(x - wx) / ww:.3f}, {(y - wy) / wh:.3f}) of its size")

    def _describe_rect(self, left, top, right, bottom):
        rect = self._window()
        if rect is None:
            self.log("No game window found, so only screen coordinates are shown.", "WARN")
            return
        wx, wy, ww, wh = rect
        fl, ft, fr, fb = (left - wx) / ww, (top - wy) / wh, (right - wx) / ww, (bottom - wy) / wh
        self.log(f"  In the game window: ({fl:.3f}, {ft:.3f}, {fr:.3f}, {fb:.3f})")