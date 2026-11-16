import ctypes
from ctypes import wintypes


def enable_dpi_awareness():
    """Must run BEFORE the tkinter window is created, so pixels are real pixels."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def get_work_area():
    """Screen area without the taskbar: (left, top, right, bottom)."""
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom