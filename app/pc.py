"""Computer control on Windows using only ctypes: screenshots, mouse, keyboard, windows.

Coordinates given to the model are in *screenshot image pixels*; we map them back to real
screen pixels using the geometry of the last screenshot.
"""
import struct
import sys
import time
import zlib
from pathlib import Path

IS_WIN = sys.platform == "win32"
LAST = {"left": 0, "top": 0, "w": 0, "h": 0, "sw": 0, "sh": 0}

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = (wintypes.HWND,)
    user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
    gdi32.BitBlt.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD)
    gdi32.GetDIBits.argtypes = (wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT)
    gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
    gdi32.DeleteDC.argtypes = (wintypes.HDC,)
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.IsIconic.argtypes = (wintypes.HWND,)
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, KEYEVENTF_EXTENDED = 0x2, 0x4, 0x1
MOUSE = {"left": (0x2, 0x4), "right": (0x8, 0x10), "middle": (0x20, 0x40)}
MOUSEEVENTF_WHEEL = 0x800

VK = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B,
      "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "backspace": 0x08,
      "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "space": 0x20, "up": 0x26, "down": 0x28,
      "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
      "capslock": 0x14, "printscreen": 0x2C, "menu": 0x5D, "apps": 0x5D,
      "volumeup": 0xAF, "volumedown": 0xAE, "mute": 0xAD, "playpause": 0xB3}
VK.update({f"f{i}": 0x6F + i for i in range(1, 13)})
EXTENDED = {0x2E, 0x2D, 0x26, 0x28, 0x25, 0x27, 0x24, 0x23, 0x21, 0x22, 0x5B, 0x5D}


def init_dpi():
    """Make this process DPI-aware so coordinates and captures use real pixels."""
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def _need_win():
    if not IS_WIN:
        raise RuntimeError("التحكم بالجهاز متاح على ويندوز بس")


# ---------------- screenshot ----------------
def _png(width, height, bgra):
    """Encode a top-down BGRA buffer as PNG (stdlib only)."""
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    stride = width * 3
    raw = b"".join(b"\x00" + bytes(rgb[y * stride:(y + 1) * stride]) for y in range(height))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 3)) + chunk(b"IEND", b""))


def capture(out_png: Path, screen="all"):
    """Capture the whole virtual desktop (all monitors) or the primary one. Returns geometry dict."""
    _need_win()
    if screen == "primary":
        left, top = 0, 0
        w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    else:
        left, top = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        w, h = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    hdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        if not gdi32.BitBlt(mdc, 0, 0, w, h, hdc, left, top, 0x00CC0020 | 0x40000000):
            raise RuntimeError("BitBlt فشل")
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = w, -h, 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0):
            raise RuntimeError("GetDIBits فشل")
        data = buf.raw
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(None, hdc)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_png.write_bytes(_png(w, h, data))
    LAST.update(left=left, top=top, w=w, h=h, sw=w, sh=h)
    return dict(LAST)


def set_scaled(sw, sh):
    """Record the size of the image the model actually saw."""
    LAST["sw"], LAST["sh"] = sw, sh


def to_screen(x, y):
    if not LAST["sw"]:
        raise RuntimeError("خذ لقطة شاشة أول عشان أعرف الإحداثيات")
    rx = LAST["left"] + round(float(x) * LAST["w"] / LAST["sw"])
    ry = LAST["top"] + round(float(y) * LAST["h"] / LAST["sh"])
    return rx, ry


# ---------------- input ----------------
def _send(inputs):
    arr = (INPUT * len(inputs))(*inputs)
    n = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if n != len(inputs):
        raise RuntimeError("ويندوز منع الإدخال (ممكن نافذة تشتغل كمسؤول)")


def _mouse(flags, data=0):
    i = INPUT(type=INPUT_MOUSE)
    i.u.mi = MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, 0)
    return i


def _key(vk=0, scan=0, flags=0):
    i = INPUT(type=INPUT_KEYBOARD)
    if vk in EXTENDED:
        flags |= KEYEVENTF_EXTENDED
    i.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


def move(x, y):
    _need_win()
    rx, ry = to_screen(x, y)
    user32.SetCursorPos(rx, ry)
    return rx, ry


def click(x, y, button="left", count=1):
    _need_win()
    rx, ry = move(x, y)
    time.sleep(0.05)
    down, up = MOUSE.get(button, MOUSE["left"])
    for _ in range(max(1, min(3, int(count)))):
        _send([_mouse(down), _mouse(up)])
        time.sleep(0.06)
    return rx, ry


def drag(x1, y1, x2, y2):
    _need_win()
    move(x1, y1)
    time.sleep(0.05)
    _send([_mouse(MOUSE["left"][0])])
    steps = 12
    sx, sy = to_screen(x1, y1)
    ex, ey = to_screen(x2, y2)
    for k in range(1, steps + 1):
        user32.SetCursorPos(sx + (ex - sx) * k // steps, sy + (ey - sy) * k // steps)
        time.sleep(0.02)
    _send([_mouse(MOUSE["left"][1])])


def scroll(x, y, amount):
    _need_win()
    if x is not None and y is not None:
        move(x, y)
    _send([_mouse(MOUSEEVENTF_WHEEL, int(amount) * 120)])


def type_text(text):
    _need_win()
    units = text.encode("utf-16-le")
    seq = []
    for k in range(0, len(units), 2):
        code = units[k] | (units[k + 1] << 8)
        if code == 10:                          # newline -> Enter
            seq += [_key(0x0D), _key(0x0D, flags=KEYEVENTF_KEYUP)]
            continue
        seq += [_key(0, code, KEYEVENTF_UNICODE), _key(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    for k in range(0, len(seq), 40):            # chunks so long texts stay reliable
        _send(seq[k:k + 40])
        time.sleep(0.01)


def press(combo):
    """e.g. 'ctrl+shift+s', 'enter', 'alt+f4', 'win+r'."""
    _need_win()
    keys = [k.strip().lower() for k in combo.replace(" ", "").split("+") if k.strip()]
    vks = []
    for k in keys:
        if k in VK:
            vks.append(VK[k])
        elif len(k) == 1 and k.isalnum():
            vks.append(ord(k.upper()))
        else:
            raise ValueError(f"مفتاح غير معروف: {k}")
    seq = [_key(v) for v in vks] + [_key(v, flags=KEYEVENTF_KEYUP) for v in reversed(vks)]
    _send(seq)


# ---------------- windows ----------------
def list_windows():
    _need_win()
    res = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, b, n + 1)
                if b.value.strip() and b.value not in ("Program Manager",):
                    res.append((hwnd, b.value))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return res


def focus_window(title):
    _need_win()
    t = title.lower()
    for hwnd, name in list_windows():
        if t in name.lower():
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)        # SW_RESTORE
            _send([_key(0x12), _key(0x12, flags=KEYEVENTF_KEYUP)])   # unlocks SetForegroundWindow
            user32.SetForegroundWindow(hwnd)
            return name
    return None
