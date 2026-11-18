"""Bounded mouse actions and literal Unicode text through Windows SendInput."""

import asyncio
import ctypes
import json
import re
from ctypes import wintypes

from errors import ControlError
from settings import ROOT

KEYS = {item['key']: item for item in json.loads((ROOT / 'web' / 'keymap.json').read_text(encoding='utf-8'))}
MODIFIERS = {'ctrl': (0x11, 0), 'alt': (0x12, 0), 'shift': (0x10, 0), 'win': (0x5b, 1)}
BUTTON_FLAGS = {'left': (2, 4), 'right': (8, 16)}
HOLD_SECONDS = 2.5


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', wintypes.DWORD), ('data', INPUTUNION)]


USER32 = ctypes.WinDLL('user32', use_last_error=True)
USER32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
USER32.SendInput.restype = wintypes.UINT
USER32.GetAsyncKeyState.argtypes = [ctypes.c_int]
USER32.GetAsyncKeyState.restype = ctypes.c_short


def send_input(events):
    array = (INPUT * len(events))(*events)
    ctypes.set_last_error(0)
    sent = USER32.SendInput(len(events), array, ctypes.sizeof(INPUT))
    if sent != len(events):
        code = ctypes.get_last_error()
        raise ControlError(f'Windows accepted {sent} of {len(events)} input events (error {code}). Unlock your laptop and use an app that is not running as administrator. Check the result before trying again.')


def mouse_event(flags, dx=0, dy=0, data=0):
    return INPUT(type=0, mi=MOUSEINPUT(dx=dx, dy=dy, mouseData=data & 0xffffffff, dwFlags=flags))


def key_events(vk=0, scan=0, flags=0):
    return [INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags)), INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags | 0x0002))]


class WindowsDesktop:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.holds = {}
        self.closing = False

    def release(self, button):
        held = self.holds.get(button)
        if held is None:
            return
        send_input([mouse_event(BUTTON_FLAGS[button][1])])
        held['timer'].cancel()
        del self.holds[button]

    def button(self, data):
        button, state, hold = data['button'], data['state'], data['hold']
        if not isinstance(button, str) or button not in BUTTON_FLAGS or state not in ('down', 'up', 'renew') or not isinstance(hold, str) or not re.fullmatch(r'[a-f0-9]{32}', hold):
            raise ControlError('Invalid mouse hold request.')
        current = self.holds.get(button)
        if current and current['id'] != hold:
            raise ControlError('This mouse button is held by another touch. Release it first.')
        if state == 'up':
            self.release(button)
            return
        if state == 'down':
            if current:
                raise ControlError('This mouse hold is already active.')
            try:
                send_input([mouse_event(BUTTON_FLAGS[button][0])])
            except ControlError:
                send_input([mouse_event(BUTTON_FLAGS[button][1])])
                raise
        elif current is None:
            raise ControlError('The mouse hold expired. Release and press the button again.')
        if current:
            current['timer'].cancel()
        self.holds[button] = {'id': hold, 'timer': asyncio.get_running_loop().call_later(HOLD_SECONDS, self.release, button)}

    async def shutdown(self):
        async with self.lock:
            self.closing = True
            for button in list(self.holds):
                self.release(button)

    async def command(self, data):
        if self.closing:
            raise ControlError('Laptop Remote is stopping.')
        if not isinstance(data, dict) or not isinstance(data.get('action'), str):
            raise ControlError('A command must contain an action.')
        action = data['action']
        fields = {'move': {'dx', 'dy'}, 'click': {'button'}, 'button': {'button', 'state', 'hold'}, 'scroll': {'steps'}, 'text': {'text'}, 'key': {'key', 'modifiers'}}
        if action not in fields or set(data) != fields[action] | {'action'}:
            raise ControlError('Unknown input action, or missing or unexpected fields.')
        if action == 'button':
            self.button(data)
            return
        if action == 'move':
            if any(type(data[k]) is not int or not -60 <= data[k] <= 60 for k in ('dx', 'dy')):
                raise ControlError('Mouse movement must use whole numbers from -60 to 60.')
            events = [mouse_event(0x0001, data['dx'], data['dy'])]
        elif action == 'click':
            if data['button'] not in ('left', 'right'):
                raise ControlError('Choose left or right click.')
            if data['button'] in self.holds:
                raise ControlError('Release the held mouse button before clicking it.')
            down, up = (0x0002, 0x0004) if data['button'] == 'left' else (0x0008, 0x0010)
            events = [mouse_event(down), mouse_event(up)]
        elif action == 'scroll':
            if type(data['steps']) is not int or data['steps'] not in (-3, -2, -1, 1, 2, 3):
                raise ControlError('Scroll must be between one and three steps in either direction.')
            events = [mouse_event(0x0800, data=data['steps'] * 120)]
        elif action == 'key':
            key, modifiers = data['key'], data['modifiers']
            if not isinstance(key, str) or key not in KEYS or not isinstance(modifiers, list) or len(modifiers) > 4 or any(not isinstance(m, str) or m not in MODIFIERS for m in modifiers) or len(set(modifiers)) != len(modifiers):
                raise ControlError('Choose a supported key and distinct Ctrl, Alt, Shift or Win modifiers.')
            if key == 'delete' and {'ctrl', 'alt'} <= set(modifiers):
                raise ControlError('Windows does not allow Ctrl+Alt+Delete through a remote shortcut.')
            sequence = [MODIFIERS[m] for m in MODIFIERS if m in modifiers] + [(KEYS[key]['code'], int(KEYS[key]['extended']))]
            releases = [INPUT(type=1, ki=KEYBDINPUT(wVk=vk, dwFlags=flags | 2)) for vk, flags in reversed(sequence)]
            events = [INPUT(type=1, ki=KEYBDINPUT(wVk=vk, dwFlags=flags)) for vk, flags in sequence] + releases
        else:
            text = data['text']
            if not isinstance(text, str) or not 1 <= len(text) <= 500:
                raise ControlError('Enter between 1 and 500 characters.')
            if any(ord(char) < 32 or ord(char) == 127 for char in text):
                raise ControlError('Send one line of text. Use the Enter and Tab buttons separately.')
            try:
                encoded = text.encode('utf-16-le')
            except UnicodeEncodeError as exc:
                raise ControlError('The text contains an invalid Unicode character.') from exc
            events = []
            for i in range(0, len(encoded), 2):
                unit = int.from_bytes(encoded[i:i + 2], 'little')
                events.extend(key_events(scan=unit, flags=0x0004))
        if action in {'text', 'key'} and any(USER32.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5b, 0x5c)):
            raise ControlError('Release Shift, Ctrl, Alt and Windows keys on your laptop before typing.')
        try:
            send_input(events)
        except ControlError:
            if action == 'key':
                send_input(releases)
            raise
