"""An authenticated phone remote for media, mouse and text entry."""

import argparse
import asyncio
import hmac
import html
import io
import json
import logging
import socket
from urllib.parse import urlsplit

from aiohttp import web
import qrcode
import qrcode.image.svg

from errors import ControlError
from media import WindowsMedia
from desktop import WindowsDesktop
from screen import WindowsScreen, parse_view
from pairing_keys import load_token
from settings import PORT, ROOT, STATE_DIR

STATIC_FILES = {'/': 'index.html', '/app.js': 'app.js', '/desktop.js': 'desktop.js', '/keybinds.js': 'keybinds.js', '/keymap.json': 'keymap.json', '/screen.js': 'screen.js', '/pairing.js': 'pairing.js', '/qr-reader.js': 'qr-reader.js', '/vendor/zxing-reader.js': 'vendor/zxing-reader.js', '/vendor/zxing_reader.wasm': 'vendor/zxing_reader.wasm', '/style.css': 'style.css', '/icon.svg': 'icon.svg', '/manifest.webmanifest': 'manifest.webmanifest'}
LOG = logging.getLogger('laptop_remote')
TOKEN = web.AppKey('token', str)
PHONE_URL = web.AppKey('phone_url', str)
LISTEN_PORT = web.AppKey('port', int)
MEDIA = web.AppKey('media', WindowsMedia)
DESKTOP = web.AppKey('desktop', WindowsDesktop)
SCREEN = web.AppKey('screen', WindowsScreen)
COOKIE_NAME = 'laptop_remote_session'


def local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
        route.connect(('1.1.1.1', 80))
        address = route.getsockname()[0]
    if address.startswith('127.') or address == '0.0.0.0':
        raise RuntimeError('No usable network address. Connect your laptop to Wi-Fi first.')
    return address


@web.middleware
async def guard(request, handler):
    if request.path.startswith('/api/'):
        if request.headers.get('X-Remote-Request') != '1':
            return web.json_response({'error': 'The remote request header is required.'}, status=403)
        origin = request.headers.get('Origin')
        if origin and origin != f'{request.scheme}://{request.host}':
            return web.json_response({'error': 'The request came from a different website.'}, status=403)
        provided = request.cookies.get(COOKIE_NAME, '')
        if request.path != '/api/pair' and not hmac.compare_digest(provided.encode('utf-8'), request.app[TOKEN].encode('ascii')):
            return web.json_response({'error': 'Pair this app to continue. Tap Scan QR code.'}, status=401, headers={'Cache-Control': 'no-store'})
    try:
        response = await handler(request)
    except ControlError as exc:
        response = web.json_response({'error': str(exc)}, status=422)
    except (asyncio.TimeoutError, TimeoutError):
        response = web.json_response({'error': 'Windows did not respond in time. Check the player before trying again.'}, status=504)
    except web.HTTPException as exc:
        response = web.json_response({'error': exc.reason}, status=exc.status)
    except Exception:
        LOG.exception('Request failed: %s %s', request.method, request.path)
        response = web.json_response({'error': 'Laptop Remote encountered an error. Open its log on the laptop.'}, status=500)
    response.headers.update({
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'no-referrer',
        'X-Frame-Options': 'DENY',
        'Content-Security-Policy': "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    })
    return response


async def state(request):
    async with request.app[MEDIA].lock:
        async with asyncio.timeout(8):
            result = await request.app[MEDIA].state()
    return web.json_response(result)


async def json_body(request):
    if request.content_type != 'application/json':
        raise web.HTTPUnsupportedMediaType(reason='Commands require application/json.')
    try:
        return await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise web.HTTPBadRequest(reason='The command is not valid JSON.')


async def pair_session(request):
    data = await json_body(request)
    if not isinstance(data, dict) or set(data) != {'key'} or not isinstance(data['key'], str):
        raise ControlError('A pairing request must contain a key.')
    if not hmac.compare_digest(data['key'].encode('utf-8'), request.app[TOKEN].encode('ascii')):
        raise web.HTTPUnauthorized(reason='The pairing key is invalid. Click Pair in Laptop Remote on your laptop.')
    response = web.json_response({'paired': True})
    response.set_cookie(COOKIE_NAME, request.app[TOKEN], max_age=365 * 24 * 60 * 60, httponly=True, samesite='Strict', secure=request.secure, path='/')
    return response


async def command(request):
    data = await json_body(request)
    async with request.app[MEDIA].lock:
        async with asyncio.timeout(8):
            await request.app[MEDIA].command(data)
            # Command acceptance and later state reads are separate. A state-read
            # failure must not imply the preceding command failed or should retry.
    return web.json_response({'accepted': True})


async def desktop_command(request):
    data = await json_body(request)
    async with request.app[DESKTOP].lock:
        await request.app[DESKTOP].command(data)
    return web.json_response({'accepted': True})


async def shutdown_input(request):
    require_local(request)
    await request.app[DESKTOP].shutdown()
    return web.json_response({'stopping': True})


async def cleanup_input(app):
    await app[DESKTOP].shutdown()


async def static(request):
    return web.FileResponse(ROOT / 'web' / STATIC_FILES[request.path])


async def screen_frame(request):
    view = parse_view(request.query)
    async with asyncio.timeout(8):
        data, width, height = await request.app[SCREEN].frame(view)
    return web.Response(body=data, content_type='image/jpeg', headers={
        'X-Screen-Width': str(width), 'X-Screen-Height': str(height),
    })


def require_local(request):
    local_hosts = {f'127.0.0.1:{request.app[LISTEN_PORT]}', f'localhost:{request.app[LISTEN_PORT]}'}
    forwarded = any(name.lower() in {'forwarded', 'x-forwarded-for', 'x-forwarded-host', 'cf-connecting-ip'} for name in request.headers)
    if request.remote not in {'127.0.0.1', '::1'} or request.host not in local_hosts or forwarded:
        raise web.HTTPForbidden(reason='Pairing codes are only available directly on the laptop.')


async def open_remote(request):
    require_local(request)
    return web.Response(status=302, headers={'Location': '/#key=' + request.app[TOKEN]})


async def pair(request):
    require_local(request)
    url = request.app[PHONE_URL] + '/#key=' + request.app[TOKEN]
    qr = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=4)
    buffer = io.BytesIO()
    qr.save(buffer)
    svg = buffer.getvalue().decode('utf-8')
    page = (ROOT / 'web' / 'pair.html').read_text(encoding='utf-8')
    page = page.replace('{{QR}}', svg).replace('{{PHONE_URL}}', html.escape(url, quote=True)).replace('{{ADDRESS}}', html.escape(request.app[PHONE_URL]))
    return web.Response(text=page, content_type='text/html')


async def health(request):
    return web.json_response({'app': 'laptop-remote', 'ready': True})


async def create_app(token, phone_url, port, media=None, desktop=None, screen=None):
    app = web.Application(middlewares=[guard], client_max_size=8192)
    app[TOKEN] = token
    app[PHONE_URL] = phone_url
    app[LISTEN_PORT] = port
    app[MEDIA] = media if media is not None else await WindowsMedia.create()
    app[DESKTOP] = desktop if desktop is not None else WindowsDesktop()
    app[SCREEN] = screen if screen is not None else WindowsScreen()
    for path in STATIC_FILES:
        app.router.add_get(path, static)
    app.router.add_get('/pair', pair)
    app.router.add_get('/open', open_remote)
    app.router.add_get('/health', health)
    app.router.add_get('/api/state', state)
    app.router.add_get('/api/screen', screen_frame)
    app.router.add_post('/api/pair', pair_session)
    app.router.add_post('/api/command', command)
    app.router.add_post('/api/input', desktop_command)
    app.router.add_post('/api/shutdown', shutdown_input)
    app.on_cleanup.append(cleanup_input)
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--phone-url', help='Explicit URL for pairing, if using a tunnel.')
    args = parser.parse_args()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=STATE_DIR / 'server.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    phone_url = args.phone_url or f'http://{local_ip()}:{args.port}'
    parsed = urlsplit(phone_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('--phone-url must be an http(s) origin without a path or credentials.')
    LOG.info('Starting remote on %s:%s', args.bind, args.port)
    web.run_app(create_app(load_token(), phone_url, args.port), host=args.bind, port=args.port, access_log=None, print=lambda _: print('READY', flush=True))


if __name__ == '__main__':
    main()
