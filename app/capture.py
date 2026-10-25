"""Grab the window the user is working in (e.g. Altium) as a PNG."""
import io
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import mss
from PIL import Image

from .config import CONFIG

PW_RENDERFULLCONTENT = 2  # PrintWindow flag: render the window even if it's covered


@dataclass
class Screenshot:
    png_bytes: bytes
    captured_at: datetime
    window_title: str
    width: int
    height: int


def _window_info(hwnd):
    """(title, (left, top, right, bottom), pid) for a usable window, else None."""
    import win32gui
    import win32process

    if not hwnd or not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
        return None
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    if right - left < 50 or bottom - top < 50:
        return None
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return win32gui.GetWindowText(hwnd), (left, top, right, bottom), pid


def _print_window(hwnd, width, height) -> Image.Image | None:
    """Render a window that is behind ours. Some GPU-drawn views come back black; that's best effort."""
    import win32gui
    import win32ui

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    mem_dc = src_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(src_dc, width, height)
        mem_dc.SelectObject(bitmap)
        import ctypes
        if not ctypes.windll.user32.PrintWindow(hwnd, mem_dc.GetSafeHdc(), PW_RENDERFULLCONTENT):
            return None
        info = bitmap.GetInfo()
        return Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]),
                                bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        mem_dc.DeleteDC()
        src_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)


class WindowCapturer:
    def __init__(self):
        self._last_other_hwnd = None  # last focused window that isn't ours

    def capture(self) -> Screenshot | None:
        """Screenshot the window the user is working in. None only if there's no usable window."""
        captured_at = datetime.now(timezone.utc)
        if sys.platform != "win32":
            # Non-Windows dev fallback: primary monitor.
            with mss.mss() as sct:
                raw = sct.grab(sct.monitors[1])
            return self._encode(Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX"), "", captured_at)

        import win32gui

        hwnd = win32gui.GetForegroundWindow()
        info = _window_info(hwnd)
        if info and info[2] != os.getpid():
            # Normal case: grab the focused window's pixels straight off the screen.
            self._last_other_hwnd = hwnd
            title, (left, top, right, bottom), _ = info
            with mss.mss() as sct:
                raw = sct.grab({"left": left, "top": top, "width": right - left, "height": bottom - top})
            return self._encode(Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX"), title, captured_at)

        # Our own window is focused (e.g. the user is typing a question): keep capturing the window
        # they were working in, rendered directly since ours may be covering it.
        info = _window_info(self._last_other_hwnd)
        if not info:
            return None
        title, (left, top, right, bottom), _ = info
        img = _print_window(self._last_other_hwnd, right - left, bottom - top)
        return self._encode(img, title, captured_at) if img else None

    @staticmethod
    def _encode(img: Image.Image, title: str, captured_at: datetime) -> Screenshot:
        img.thumbnail((CONFIG.max_image_edge, CONFIG.max_image_edge))
        buf = io.BytesIO()
        img.save(buf, format="PNG", compress_level=3)  # fast enough to stay well inside a 3 s tick
        return Screenshot(buf.getvalue(), captured_at, title, img.width, img.height)
