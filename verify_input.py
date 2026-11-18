"""Exercise real input only while the isolated browser fixture has focus."""

import ctypes
from ctypes import wintypes
import json
import time
import urllib.request

from server import COOKIE_NAME
from pairing_keys import load_token
from settings import PORT

user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]


def cursor():
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError(ctypes.get_last_error())
    return point.x, point.y


def command(data):
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(user32.GetForegroundWindow(), title, len(title))
    if not title.value.startswith('Laptop Remote input test'):
        raise RuntimeError('The isolated input test page must be in the foreground. Nothing was sent.')
    request = urllib.request.Request(
        f'http://127.0.0.1:{PORT}/api/input',
        data=json.dumps(data).encode('utf-8'),
        headers={'X-Remote-Request': '1', 'Cookie': COOKIE_NAME + '=' + load_token(), 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        assert json.load(response) == {'accepted': True}


def main():
    before = cursor()
    command({'action': 'move', 'dx': 6, 'dy': 4})
    deadline = time.monotonic() + 2
    while cursor() == before and time.monotonic() < deadline:
        pass
    if cursor() == before:
        raise AssertionError('Windows did not move the cursor.')
    print('PASS: Windows cursor moved')
    command({'action': 'click', 'button': 'left'})
    command({'action': 'text', 'text': 'Remote test cafÃ© ðŸ˜€Z'})
    command({'action': 'key', 'key': 'backspace', 'modifiers': []})
    command({'action': 'key', 'key': 'enter', 'modifiers': []})
    command({'action': 'click', 'button': 'right'})
    command({'action': 'scroll', 'steps': 1})
    command({'action': 'move', 'dx': -6, 'dy': -4})
    print('Commands accepted; verify the fixture value and mouse events in the browser.')


if __name__ == '__main__':
    main()
