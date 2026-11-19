from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web

from laptop_remote import pairing_keys
from laptop_remote.server import COOKIE_NAME, LISTEN_PORT, TOKEN, guard, pair_session, require_local


class SecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_requires_pairing_header_and_same_origin(self):
        for path in ['/api/state', '/api/input', '/api/command', '/api/screen', '/api/shutdown']:
            request = SimpleNamespace(path=path, app={TOKEN: 'test-key'}, scheme='http', host='laptop:8765')
            for headers, cookies, status in [
                ({}, {COOKIE_NAME: 'test-key'}, 403),
                ({'X-Remote-Request': '1'}, {}, 401),
                ({'X-Remote-Request': '1'}, {COOKIE_NAME: 'old-key'}, 401),
                ({'X-Remote-Request': '1', 'Origin': 'https://unrelated.example'}, {COOKIE_NAME: 'test-key'}, 403),
                ({'X-Remote-Request': '1', 'Origin': 'http://laptop:8765'}, {COOKIE_NAME: 'test-key'}, 200),
            ]:
                with self.subTest(path=path, status=status):
                    request.headers, request.cookies = headers, cookies
                    handler = AsyncMock(return_value=web.Response())
                    response = await guard(request, handler)
                    self.assertEqual(response.status, status)
                    if status == 200:
                        handler.assert_awaited_once_with(request)
                        self.assertEqual(response.headers['Cache-Control'], 'no-store')
                    else:
                        handler.assert_not_awaited()

    async def test_pairing_cookie_requires_the_current_key(self):
        request = SimpleNamespace(app={TOKEN: 'test-key'}, content_type='application/json', secure=False)
        request.json = AsyncMock(return_value={'key': 'old-key'})
        with self.assertRaises(web.HTTPUnauthorized):
            await pair_session(request)
        request.json.return_value = {'key': 'test-key'}
        response = await pair_session(request)
        cookie = response.cookies[COOKIE_NAME]
        self.assertEqual(cookie.value, 'test-key')
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Strict')

    def test_local_actions_reject_lan_and_forwarded_requests(self):
        request = SimpleNamespace(app={LISTEN_PORT: 8765})
        for remote, host, headers in [
            ('192.168.1.10', '127.0.0.1:8765', {}),
            ('127.0.0.1', '192.168.1.10:8765', {}),
            ('127.0.0.1', '127.0.0.1:8765', {'X-Forwarded-For': '192.168.1.10'}),
            ('127.0.0.1', '127.0.0.1:8765', {'CF-Connecting-IP': '192.168.1.10'}),
        ]:
            request.remote, request.host, request.headers = remote, host, headers
            with self.subTest(remote=remote, host=host, headers=headers), self.assertRaises(web.HTTPForbidden):
                require_local(request)
        request.remote, request.host, request.headers = '127.0.0.1', '127.0.0.1:8765', {}
        require_local(request)

    def test_pairing_key_is_encrypted_and_rotation_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch('laptop_remote.pairing_keys.STATE_DIR', folder), patch('laptop_remote.pairing_keys.TOKEN_FILE', folder / 'key.dpapi'):
                original = pairing_keys.load_token()
                pairing_keys.rotate_token()
                changed = pairing_keys.load_token()
                self.assertNotEqual(original, changed)
                self.assertEqual(changed, pairing_keys.load_token())
                self.assertNotIn(changed.encode(), (folder / 'key.dpapi').read_bytes())
