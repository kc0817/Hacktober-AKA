"""Grab the currently focused window (e.g. Altium) as a PNG."""
import hashlib
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


def _foreground_window():
    """Return (title, (left, top, right, bottom), pid) of the focused window, or None."""
    if sys.platform != "win32":
        return None
    import win32gui
    import win32process

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd or win32gui.IsIconic(hwnd):
        return None
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return win32gui.GetWindowText(hwnd), win32gui.GetWindowRect(hwnd), pid


class WindowCapturer:
    def __init__(self):
        self._last_hash = None

    def capture(self) -> Screenshot | None:
        """Screenshot the active window. Returns None if there's nothing new to save."""
        fg = _foreground_window()
        with mss.mss() as sct:
            if fg is None:
                # Non-Windows dev fallback: primary monitor.
                title, region = "", sct.monitors[1]
            else:
                title, (left, top, right, bottom), pid = fg
                # Don't screenshot ourselves while the user is typing a question.
                if pid == os.getpid():
                    return None
                if right - left < 50 or bottom - top < 50:
                    return None
                region = {"left": left, "top": top, "width": right - left, "height": bottom - top}
            raw = sct.grab(region)

        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        img.thumbnail((CONFIG.max_image_edge, CONFIG.max_image_edge))

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        png = buf.getvalue()

        # Skip identical frames (user idle) to save storage and tokens.
        digest = hashlib.sha1(png).hexdigest()
        if digest == self._last_hash:
            return None
        self._last_hash = digest

        return Screenshot(png, datetime.now(timezone.utc), title, img.width, img.height)
