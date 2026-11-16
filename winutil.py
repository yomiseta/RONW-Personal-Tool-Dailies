import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

# Declare argument types so window handles are safe on 64-bit Windows.
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

SW_MINIMIZE, SW_RESTORE = 6, 9
SWP_SHOWWINDOW = 0x0040
GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x80
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def _title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _pid(hwnd):
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _exe_name(pid):
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


def minimize_all(skip_pid=None):
    """Minimizes every normal application window except the autoboss. Returns how many."""
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
    """Finds the biggest visible window of a program (matched by exe name, or by class+title)."""
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
                continue  # skip tiny helper windows
            area = (r.right - r.left) * (r.bottom - r.top)
        if area > best_area:
            best, best_area = hwnd, area
    return best


def fit_window(hwnd, x, y, w, h):
    """Moves/resizes so the VISIBLE window fills (x, y, w, h). Returns the final visible rect."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, 0, x, y, w, h, SWP_SHOWWINDOW)

    # Windows 10/11 add an invisible border (~7 px). Measure it and compensate once.
    win, frame = wintypes.RECT(), wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(win))
    ok = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                      ctypes.byref(frame), ctypes.sizeof(frame)) == 0
    if ok:
        dl, dt = frame.left - win.left, frame.top - win.top
        dr, db = win.right - frame.right, win.bottom - frame.bottom
        if dl or dt or dr or db:
            user32.SetWindowPos(hwnd, 0, x - dl, y - dt, w + dl + dr, h + dt + db, SWP_SHOWWINDOW)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                     ctypes.byref(frame), ctypes.sizeof(frame))
        return frame.left, frame.top, frame.right - frame.left, frame.bottom - frame.top
    user32.GetWindowRect(hwnd, ctypes.byref(win))
    return win.left, win.top, win.right - win.left, win.bottom - win.top