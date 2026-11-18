"""On-demand primary-display frames; images remain in memory only."""
import asyncio
import ctypes
import io
import math
import threading

from PIL import Image, ImageDraw, ImageGrab
import win32gui

from errors import ControlError


def parse_view(query):
    if set(query) != {'x', 'y', 'zoom'} or len(query) != 3:
        raise ControlError('Screen view requires x, y and zoom.')
    try:
        x, y, zoom = (float(query[name]) for name in ('x', 'y', 'zoom'))
    except (ValueError, TypeError) as exc:
        raise ControlError('Screen view must use numeric coordinates and zoom.') from exc
    if not all(math.isfinite(value) for value in (x, y, zoom)) or not (0 <= x <= 1 and 0 <= y <= 1 and 1 <= zoom <= 6):
        raise ControlError('Screen view coordinates must be 0–1 and zoom must be 1–6.')
    return x, y, zoom


def encode_frame(image, view):
    x, y, zoom = view
    width, height = image.size
    crop_width, crop_height = max(1, round(width / zoom)), max(1, round(height / zoom))
    left = max(0, min(width - crop_width, round(x * width - crop_width / 2)))
    top = max(0, min(height - crop_height, round(y * height - crop_height / 2)))
    with image.crop((left, top, left + crop_width, top + crop_height)) as cropped:
        cropped.thumbnail((1280, 800), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        cropped.save(output, format='JPEG', quality=82, subsampling=0)
        return output.getvalue(), width, height


class WindowsScreen:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.capture_lock = threading.Lock()

    async def frame(self, view):
        async with self.lock:
            return await asyncio.to_thread(self.capture, view)

    def capture(self, view):
        # GetCursorInfo must use the same physical coordinates as ImageGrab.
        set_dpi = ctypes.WinDLL('user32', use_last_error=True).SetThreadDpiAwarenessContext
        set_dpi.argtypes = [ctypes.c_void_p]
        set_dpi.restype = ctypes.c_void_p
        with self.capture_lock:
            previous = set_dpi(ctypes.c_void_p(-4))
            if not previous:
                raise ControlError('Windows could not prepare screen capture.')
            try:
                with ImageGrab.grab(include_layered_windows=True, all_screens=False) as image:
                    flags, _, (x, y) = win32gui.GetCursorInfo()
                    if flags & 1 and 0 <= x < image.width and 0 <= y < image.height:
                        ImageDraw.Draw(image).polygon([(x, y), (x + 7, y + 23), (x + 11, y + 15), (x + 20, y + 14)], fill='#ffffff', outline='#101513', width=2)
                    return encode_frame(image, view)
            except OSError as exc:
                raise ControlError('Screen capture failed. Unlock your laptop, then try again.') from exc
            finally:
                if not set_dpi(previous):
                    raise ControlError('Windows could not restore the screen capture context.')
