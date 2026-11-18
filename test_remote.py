import asyncio
import unittest
from unittest.mock import AsyncMock

from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from errors import ControlError
from media import WindowsMedia
from server import COOKIE_NAME, create_app


class FakeMedia:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.commands = []

    async def state(self):
        return {'volume': 40, 'muted': False, 'media': None}

    async def command(self, data):
        self.commands.append(data)

    async def shutdown(self):
        pass


class RemoteTests(AioHTTPTestCase):
    async def get_application(self):
        self.media = FakeMedia()
        self.desktop = FakeMedia()
        self.screen = AsyncMock()
        self.screen.frame.return_value = (b'jpeg-frame', 1920, 1080)
        self.headers = {'X-Remote-Request': '1', 'Cookie': COOKIE_NAME + '=test-key'}
        return await create_app('test-key', 'http://192.168.1.10:8765', 8765, self.media, self.desktop, self.screen)

    async def test_screen_requires_pairing_header_and_same_origin(self):
        for headers, status in [({}, 403), ({'X-Remote-Request': '1'}, 401),
                                ({'Cookie': COOKIE_NAME + '=test-key'}, 403),
                                ({**self.headers, 'Origin': 'https://unrelated.example'}, 403)]:
            response = await self.client.get('/api/screen?x=0.5&y=0.5&zoom=1', headers=headers)
            self.assertEqual(response.status, status)
        self.screen.frame.assert_not_awaited()

    async def test_screen_returns_uncached_image_only_when_requested(self):
        await self.client.get('/api/state', headers=self.headers)
        self.screen.frame.assert_not_awaited()
        response = await self.client.get('/api/screen?x=0.25&y=0.75&zoom=3', headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, 'image/jpeg')
        self.assertEqual(await response.read(), b'jpeg-frame')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Screen-Width'], '1920')
        self.screen.frame.assert_awaited_once_with((0.25, 0.75, 3))

    async def test_invalid_screen_view_never_captures(self):
        for query in ['', 'x=0.5&y=0.5&zoom=nan', 'x=0&y=0&zoom=7', 'x=-1&y=0&zoom=1',
                      'x=0&y=0&zoom=1&zoom=2', 'x=hi&y=0&zoom=1']:
            response = await self.client.get('/api/screen?' + query, headers=self.headers)
            self.assertEqual(response.status, 422)
        self.screen.frame.assert_not_awaited()

    async def test_screen_capture_failure_is_explicit(self):
        self.screen.frame.side_effect = ControlError('Screen capture failed.')
        response = await self.client.get('/api/screen?x=0.5&y=0.5&zoom=1', headers=self.headers)
        self.assertEqual(response.status, 422)
        self.assertEqual((await response.json())['error'], 'Screen capture failed.')

    async def test_shutdown_is_laptop_only(self):
        response = await self.client.post('/api/shutdown', headers={**self.headers, 'Host': '192.168.1.10:8765'})
        self.assertEqual(response.status, 403)
        response = await self.client.post('/api/shutdown', headers={**self.headers, 'Host': '127.0.0.1:8765'})
        self.assertEqual(response.status, 200)

    async def test_commands_require_key(self):
        for endpoint in ['/api/command', '/api/input']:
            for headers in [{'X-Remote-Request': '1'}, {'X-Remote-Request': '1', 'Cookie': COOKIE_NAME + '=wrong'}, {'X-Remote-Request': '1', 'Authorization': 'Bearer test-key'}]:
                response = await self.client.post(endpoint, json={'action': 'pause'}, headers=headers)
                self.assertEqual(response.status, 401)
        self.assertEqual(self.media.commands, [])
        self.assertEqual(self.desktop.commands, [])

    async def test_state_requires_key(self):
        self.assertEqual((await self.client.get('/api/state', headers={'X-Remote-Request': '1'})).status, 401)
        response = await self.client.get('/api/state', headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())['volume'], 40)

    async def test_cross_origin_command_rejected(self):
        response = await self.client.post('/api/command', json={'action': 'pause'}, headers={**self.headers, 'Origin': 'https://unrelated.example'})
        self.assertEqual(response.status, 403)
        self.assertEqual(self.media.commands, [])

    async def test_command_once(self):
        response = await self.client.post('/api/command', json={'action': 'pause'}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(self.media.commands, [{'action': 'pause'}])

    async def test_bad_json_and_content_type(self):
        response = await self.client.post('/api/command', data='{}', headers=self.headers)
        self.assertEqual(response.status, 415)
        response = await self.client.post('/api/command', data='{bad', headers={**self.headers, 'Content-Type': 'application/json'})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.media.commands, [])

    async def test_pairing_cannot_leak_through_proxy_or_lan_host(self):
        for headers in [{'Host': '192.168.1.10:8765'}, {'Host': '127.0.0.1:8765', 'CF-Connecting-IP': '1.2.3.4'}, {'Host': '127.0.0.1:8765', 'X-Forwarded-For': '1.2.3.4'}]:
            for path in ['/pair', '/open']:
                response = await self.client.get(path, headers=headers, allow_redirects=False)
                self.assertEqual(response.status, 403)
                self.assertNotIn('test-key', await response.text())

    async def test_laptop_opens_directly_without_qr(self):
        response = await self.client.get('/open', headers={'Host': '127.0.0.1:8765'}, allow_redirects=False)
        self.assertEqual(response.status, 302)
        self.assertEqual(response.headers['Location'], '/#key=test-key')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    async def test_no_arbitrary_files_or_shell_endpoint(self):
        for path in ['/server.py', '/pairing-key.dpapi', '/api/shell']:
            response = await self.client.get(path, headers=self.headers)
            self.assertEqual(response.status, 404)

    async def test_pairing_sets_cookie_that_authenticates_without_browser_storage(self):
        response = await self.client.post('/api/pair', json={'key': 'test-key'}, headers={'X-Remote-Request': '1'})
        self.assertEqual(response.status, 200)
        cookie = response.cookies[COOKIE_NAME]
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Strict')
        self.assertEqual(cookie['max-age'], str(365 * 24 * 60 * 60))
        self.assertEqual(cookie['path'], '/')
        # This request carries only the installed app's cookie and request header,
        # with no local storage, URL key or Authorization header.
        response = await self.client.get('/api/state', headers={'X-Remote-Request': '1', 'Cookie': COOKIE_NAME + '=' + cookie.value})
        self.assertEqual(response.status, 200)

    async def test_invalid_pairing_and_cross_site_requests_cannot_set_session(self):
        for headers, key, status in [({'X-Remote-Request': '1'}, 'wrong', 401), ({}, 'test-key', 403), ({'X-Remote-Request': '1', 'Origin': 'https://unrelated.example'}, 'test-key', 403)]:
            response = await self.client.post('/api/pair', json={'key': key}, headers=headers)
            self.assertEqual(response.status, status)
            self.assertNotIn(COOKIE_NAME, response.cookies)

    async def test_desktop_input_uses_its_own_controller_once(self):
        command = {'action': 'text', 'text': 'Test'}
        response = await self.client.post('/api/input', json=command, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(self.desktop.commands, [command])
        self.assertEqual(self.media.commands, [])

    async def test_cookie_alone_cannot_authorize_a_cross_site_form(self):
        response = await self.client.post('/api/input', json={'action': 'click', 'button': 'left'}, headers={'Cookie': COOKIE_NAME + '=test-key'})
        self.assertEqual(response.status, 403)
        self.assertEqual(self.desktop.commands, [])

    async def test_restarted_server_rejects_old_device_after_key_rotation(self):
        app = await create_app('new-key', 'http://192.168.1.10:8765', 8765, FakeMedia(), FakeMedia())
        async with TestClient(TestServer(app)) as client:
            response = await client.get('/api/state', headers=self.headers)
            self.assertEqual(response.status, 401)
            response = await client.post('/api/pair', json={'key': 'test-key'}, headers={'X-Remote-Request': '1'})
            self.assertEqual(response.status, 401)
            response = await client.post('/api/pair', json={'key': 'new-key'}, headers={'X-Remote-Request': '1'})
            self.assertEqual(response.status, 200)


class ValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_reject_invalid_commands_before_hardware_access(self):
        media = WindowsMedia(None)
        for command in [None, [], {}, {'action': 'shell'}, {'action': 'play', 'value': 1}, {'action': 'volume', 'value': -1}, {'action': 'volume', 'value': 101}, {'action': 'volume', 'value': True}, {'action': 'volume', 'value': float('nan')}, {'action': 'mute', 'value': 1}]:
            with self.subTest(command=command), self.assertRaises(ControlError):
                await media.command(command)


if __name__ == '__main__':
    unittest.main()
