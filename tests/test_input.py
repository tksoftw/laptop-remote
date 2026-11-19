import ctypes
import asyncio
import unittest
from unittest.mock import patch

from laptop_remote.desktop import INPUT, WindowsDesktop, mouse_event, send_input
from laptop_remote.errors import ControlError


class DesktopTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_inputs_never_reach_windows(self):
        invalid = [None, {}, {'action': 'shell'}, {'action': 'move', 'dx': 61, 'dy': 0}, {'action': 'move', 'dx': True, 'dy': 0}, {'action': 'click', 'button': 'middle'}, {'action': 'scroll', 'steps': 0}, {'action': 'scroll', 'steps': 4}, {'action': 'key', 'key': 'win'}, {'action': 'key', 'key': []}, {'action': 'text', 'text': ''}, {'action': 'text', 'text': 'a' * 501}, {'action': 'text', 'text': 'line\nbreak'}, {'action': 'text', 'text': '\ud800'}, {'action': 'text', 'text': 'hello', 'extra': 1}]
        invalid.extend({'action': 'key', 'key': key, 'modifiers': modifiers} for key, modifiers in [
            ('delete', ['ctrl', 'alt']), ('enter', ['ctrl', 'ctrl']), ('bad', []), ('c', ['bad']), ('c', 'ctrl'),
        ])
        with patch('laptop_remote.desktop.send_input') as emit:
            for data in invalid:
                with self.subTest(data=data), self.assertRaises(ControlError):
                    await WindowsDesktop().command(data)
            emit.assert_not_called()

    async def test_drag_can_move_between_down_and_up(self):
        with patch('laptop_remote.desktop.send_input') as emit:
            desktop = WindowsDesktop()
            hold = {'action': 'button', 'button': 'left', 'hold': 'a' * 32}
            await desktop.command({**hold, 'state': 'down'})
            await desktop.command({'action': 'move', 'dx': 4, 'dy': 2})
            await desktop.command({**hold, 'state': 'renew'})
            await desktop.command({**hold, 'state': 'up'})
            self.assertEqual([call.args[0][0].mi.dwFlags for call in emit.call_args_list], [2, 1, 4])
            self.assertEqual(desktop.holds, {})

    async def test_lost_phone_releases_hold(self):
        released = asyncio.Event()
        def emit(events):
            if events[0].mi.dwFlags == 4:
                released.set()
        with patch('laptop_remote.desktop.send_input', side_effect=emit), patch('laptop_remote.desktop.HOLD_SECONDS', 0):
            desktop = WindowsDesktop()
            await desktop.command({'action': 'button', 'button': 'left', 'state': 'down', 'hold': 'a' * 32})
            await asyncio.wait_for(released.wait(), 1)
            self.assertEqual(desktop.holds, {})

    async def test_another_touch_cannot_release_held_button(self):
        with patch('laptop_remote.desktop.send_input') as emit:
            desktop = WindowsDesktop()
            await desktop.command({'action': 'button', 'button': 'left', 'state': 'down', 'hold': 'a' * 32})
            with self.assertRaisesRegex(ControlError, 'another touch'):
                await desktop.command({'action': 'button', 'button': 'left', 'state': 'up', 'hold': 'b' * 32})
            self.assertEqual(emit.call_count, 1)
            await desktop.shutdown()
            self.assertEqual(emit.call_args.args[0][0].mi.dwFlags, 4)
            with self.assertRaisesRegex(ControlError, 'stopping'):
                await desktop.command({'action': 'move', 'dx': 1, 'dy': 1})

    async def test_shortcut_modifiers_and_extended_key_release(self):
        with patch('laptop_remote.desktop.send_input') as emit, patch('laptop_remote.desktop.USER32.GetAsyncKeyState', return_value=0):
            await WindowsDesktop().command({'action': 'key', 'key': 'left', 'modifiers': ['shift', 'ctrl']})
            events = emit.call_args.args[0]
            self.assertEqual([event.ki.wVk for event in events], [17, 16, 37, 37, 16, 17])
            self.assertEqual([event.ki.dwFlags for event in events], [0, 0, 1, 3, 2, 2])

    async def test_held_modifier_blocks_text(self):
        with patch('laptop_remote.desktop.send_input') as emit, patch('laptop_remote.desktop.USER32.GetAsyncKeyState', return_value=-32768):
            with self.assertRaisesRegex(ControlError, 'Release Shift'):
                await WindowsDesktop().command({'action': 'text', 'text': 'abc'})
            emit.assert_not_called()

    def test_windows_input_layout_and_partial_failure(self):
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        with patch('laptop_remote.desktop.USER32.SendInput', return_value=0):
            with self.assertRaisesRegex(ControlError, 'Windows accepted 0 of 1'):
                send_input([mouse_event(1, 1, 0)])
