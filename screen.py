"""Screen helpers: DPI awareness and the usable desktop area."""
import ctypes
from ctypes import wintypes


def enable_dpi_awareness():
    """Makes this process DPI aware so every coordinate is a real screen pixel.
    It has to run before the first Tk window is created."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def get_work_area():
    """Returns the desktop area without the taskbar as (left, top, right, bottom)."""
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom