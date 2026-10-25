"""Grab the window the user is working in (e.g. Altium) as a PNG."""
import io
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import mss
from PIL import Image

from .config import CONFIG


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


def own_window_in_front() -> bool:
    """True when one of this app's own windows is the foreground window (Windows only)."""
    if sys.platform != "win32":
        return False
    import win32gui
    import win32process

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return False
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return pid == os.getpid()


class WindowCapturer:
    def capture(self) -> Screenshot | None:
        """Screenshot the focused window. None if it's this app's own window or there's no usable window."""
        captured_at = datetime.now(timezone.utc)
        if sys.platform != "win32":
            # Non-Windows dev fallback: primary monitor.
            with mss.mss() as sct:
                raw = sct.grab(sct.monitors[1])
            return self._encode(Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX"), "", captured_at)

        import win32gui

        info = _window_info(win32gui.GetForegroundWindow())
        if not info or info[2] == os.getpid():
            return None
        title, (left, top, right, bottom), _ = info
        with mss.mss() as sct:
            raw = sct.grab({"left": left, "top": top, "width": right - left, "height": bottom - top})
        return self._encode(Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX"), title, captured_at)

    @staticmethod
    def _encode(img: Image.Image, title: str, captured_at: datetime) -> Screenshot:
        img.thumbnail((CONFIG.max_image_edge, CONFIG.max_image_edge))
        buf = io.BytesIO()
        img.save(buf, format="PNG", compress_level=3)  # fast enough to stay well inside a 3 s tick
        return Screenshot(buf.getvalue(), captured_at, title, img.width, img.height)
