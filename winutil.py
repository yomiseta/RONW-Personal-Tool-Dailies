"""Thin wrappers around the Win32 window API: finding, arranging and inspecting windows."""
import ctypes
import re
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

# Argument types are declared explicitly so window handles stay correct on 64-bit Windows.
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

SW_MINIMIZE, SW_RESTORE = 6, 9
SWP_SHOWWINDOW = 0x0040
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION, WS_EX_TOOLWINDOW = 0xC00000, 0x80
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

# Identifiers used to recognise the launcher and the game window.
LAUNCHER_TITLE = "Ragnarok The New World"
LAUNCHER_CLASS = "Chrome_WidgetWin_0"
LAUNCHER_EXE = "Ragnarok The New World.exe"
GAME_TITLE = "Ragnarok: The New World"
GAME_CLASS = "RiverShellManagedWindowClass"


# ---------- basic window properties ----------
def _title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_class(hwnd):
    return _class(hwnd)


def _pid(hwnd):
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _exe_name(pid):
    """File name of the program that owns a process id, or an empty string if it cannot be read."""
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.replace("/", "\\").split("\\")[-1]
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _cloaked(hwnd):
    """True for windows Windows keeps hidden (for example suspended store apps)."""
    value = wintypes.DWORD(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
    return value.value != 0


def _all_windows():
    found = []

    def callback(hwnd, lparam):
        found.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


# ---------- finding windows ----------
def minimize_all(skip_pid=None):
    """Minimizes every normal application window except the ones owned by `skip_pid`.
    Returns how many windows were minimized."""
    count = 0
    for hwnd in _all_windows():
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            continue
        if not _title(hwnd) or _class(hwnd) in SHELL_CLASSES or _cloaked(hwnd):
            continue
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            continue
        if skip_pid is not None and _pid(hwnd) == skip_pid:
            continue
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        count += 1
    return count


def find_window(exe_name, class_name="", title_part=""):
    """Returns the largest visible window of a program, matched by executable name or by
    class and title. The window may be minimized."""
    best, best_area = None, 0
    for hwnd in _all_windows():
        if not user32.IsWindowVisible(hwnd):
            continue
        by_exe = exe_name and _exe_name(_pid(hwnd)).lower() == exe_name.lower()
        by_class = (class_name and _class(hwnd) == class_name
                    and title_part.lower() in _title(hwnd).lower())
        if not (by_exe or by_class):
            continue
        if user32.IsIconic(hwnd):
            area = 1
        else:
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left < 200 or r.bottom - r.top < 200:
                continue  # ignore tiny helper windows
            area = (r.right - r.left) * (r.bottom - r.top)
        if area > best_area:
            best, best_area = hwnd, area
    return best


def find_launcher_window(skip_pid=None):
    """The launcher window: visible, not minimized, with the exact title.
    Either its window class or its program name has to match as well."""
    for hwnd in _all_windows():
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            continue
        if _title(hwnd).lower() != LAUNCHER_TITLE.lower():
            continue
        pid = _pid(hwnd)
        if skip_pid is not None and pid == skip_pid:
            continue
        if _class(hwnd) != LAUNCHER_CLASS and _exe_name(pid).lower() != LAUNCHER_EXE.lower():
            continue
        return hwnd
    return None


def find_game_window(skip_pid=None):
    """The main game window.
    It is matched by title, or by the game's window class because the title is blank while loading.
    A title without the colon only counts when the window is not the launcher."""
    for hwnd in _all_windows():
        if not user32.IsWindowVisible(hwnd):
            continue
        pid = _pid(hwnd)
        if skip_pid is not None and pid == skip_pid:
            continue
        title, cls = _title(hwnd), _class(hwnd)
        with_colon = GAME_TITLE.lower() in title.lower()
        by_title = with_colon or (_norm(title) == "ragnarokthenewworld" and cls != LAUNCHER_CLASS)
        by_class = cls == GAME_CLASS
        if not (by_title or by_class):
            continue
        if by_class and not by_title and not user32.IsIconic(hwnd):
            _, _, w, h = get_rect(hwnd)
            if w < 400 or h < 300:
                continue  # a small helper window, not the game
        return hwnd
    return None


def root_window_at(x, y):
    """The top-level window under a screen point. Used to confirm that nothing covers a click target."""
    hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    return user32.GetAncestor(hwnd, 2) if hwnd else None  # GA_ROOT


# ---------- diagnostics ----------
def describe(hwnd):
    """One-line summary of a window for log messages."""
    _, _, w, h = get_rect(hwnd)
    return f"title='{_title(hwnd)}' class={_class(hwnd)} program={_exe_name(_pid(hwnd))} size={w}x{h}"


def describe_windows(limit=6):
    """Summary of the largest visible windows, used in error messages."""
    rows = []
    for hwnd in _all_windows():
        if not user32.IsWindowVisible(hwnd) or _cloaked(hwnd):
            continue
        _, _, w, h = get_rect(hwnd)
        if w >= 300 and h >= 200:
            rows.append((w * h, describe(hwnd)))
    rows.sort(reverse=True)
    return " | ".join(text for _, text in rows[:limit]) or "(none)"


# ---------- window state and geometry ----------
def get_rect(hwnd):
    """The visible rectangle (x, y, w, h), excluding the invisible resize border Windows 10/11 adds."""
    frame, win = wintypes.RECT(), wintypes.RECT()
    ok = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                      ctypes.byref(frame), ctypes.sizeof(frame)) == 0
    if ok and frame.right > frame.left:
        return frame.left, frame.top, frame.right - frame.left, frame.bottom - frame.top
    user32.GetWindowRect(hwnd, ctypes.byref(win))
    return win.left, win.top, win.right - win.left, win.bottom - win.top


def client_size(hwnd):
    """Size (w, h) of the drawing area inside the window, without title bar and borders."""
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def is_minimized(hwnd):
    return bool(user32.IsIconic(hwnd))


def is_maximized(hwnd):
    return bool(user32.IsZoomed(hwnd))


def has_caption(hwnd):
    """True when the window has a title bar, which is how a windowed (not fullscreen) game looks."""
    return bool(user32.GetWindowLongW(hwnd, GWL_STYLE) & WS_CAPTION)


def restore(hwnd):
    user32.ShowWindow(hwnd, SW_RESTORE)


def activate(hwnd):
    """Brings a window to the front. A quick Alt tap beforehand lets Windows accept the focus change."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)


def fit_window(hwnd, x, y, w, h):
    """Moves and resizes a window so its VISIBLE frame occupies (x, y, w, h).
    Returns the visible rectangle that actually resulted."""
    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, 0, x, y, w, h, SWP_SHOWWINDOW)

    # Windows 10/11 windows carry an invisible border of about 7 px. Measure it and compensate once.
    win, frame = wintypes.RECT(), wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(win))
    ok = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                      ctypes.byref(frame), ctypes.sizeof(frame)) == 0
    if ok:
        dl, dt = frame.left - win.left, frame.top - win.top
        dr, db = win.right - frame.right, win.bottom - frame.bottom
        if dl or dt or dr or db:
            user32.SetWindowPos(hwnd, 0, x - dl, y - dt, w + dl + dr, h + dt + db, SWP_SHOWWINDOW)
    return get_rect(hwnd)