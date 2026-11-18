"""Local-only browser QA fixture with a dummy key and no hardware controls."""
import asyncio
from pathlib import Path

from aiohttp import web
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
import qrcode

from server import COOKIE_NAME, create_app
from screen import encode_frame

PORT = 48737
HOST = '127.0.0.2'
KEY = 'Q' * 43


class FixtureControls:
    def __init__(self):
        self.lock = asyncio.Lock()

    async def state(self):
        return {'computer': 'Pairing test', 'output': 'Test audio output', 'volume': 40, 'muted': False, 'media': None}

    async def command(self, data):
        raise RuntimeError('This fixture does not control hardware.')

    async def shutdown(self):
        pass


class FixtureDesktop(FixtureControls):
    def __init__(self):
        super().__init__()
        self.events = []

    async def command(self, data):
        self.events.append(data)


class FixtureScreen:
    def __init__(self):
        self.calls = 0

    async def frame(self, view):
        self.calls += 1
        with Image.new('RGB', (1600, 900), '#172338') as image:
            draw = ImageDraw.Draw(image)
            for row in range(3):
                for column in range(4):
                    box = (column * 400 + 8, row * 300 + 8, column * 400 + 392, row * 300 + 292)
                    draw.rectangle(box, fill=['#537f83', '#9b765d', '#69834f', '#6a648d'][(row + column) % 4])
                    draw.text((box[0] + 35, box[1] + 45), f'{column + 1}, {row + 1}', fill='white', font_size=54)
            draw.text((30, 20), f'Preview test — frame {self.calls}', fill='white', font_size=24)
            return encode_frame(image, view)


async def fixture_app():
    folder = Path(__file__).resolve().parent / 'artifacts' / 'pairing-test'
    folder.mkdir(parents=True, exist_ok=True)
    code = qrcode.make(f'http://{HOST}:{PORT}/#key={KEY}').convert('RGB')
    photo = Image.new('RGB', (1600, 1200), '#777777')
    photo.paste(code, ((photo.width - code.width) // 2, (photo.height - code.height) // 2))
    photo.rotate(5, fillcolor='#777777').save(folder / 'valid-photo.jpg', quality=90)
    photo.rotate(23, fillcolor='#777777').filter(ImageFilter.GaussianBlur(.7)).save(folder / 'angled-photo.jpg', quality=75)
    ImageEnhance.Contrast(photo).enhance(.22).save(folder / 'low-contrast.jpg', quality=80)
    distant = Image.new('RGB', (4032, 3024), '#555555')
    small = code.resize((210, 210), Image.Resampling.LANCZOS)
    distant.paste(small, (2200, 1750))
    distant.save(folder / 'distant-photo.jpg', quality=90)
    qrcode.make('https://example.com/unrelated').save(folder / 'wrong-code.png')
    Image.new('RGB', (600, 600), '#ffffff').save(folder / 'no-code.png')
    multiple = Image.new('RGB', (1400, 700), '#777777')
    multiple.paste(code, (20, 60))
    multiple.paste(qrcode.make(f'http://{HOST}:{PORT}/#key={"R" * 43}').convert('RGB'), (750, 60))
    multiple.save(folder / 'multiple-codes.png')
    names = {path.name for path in folder.iterdir() if path.suffix in {'.jpg', '.png'}}
    async def test_photo(request):
        name = request.match_info['name']
        if name not in names:
            raise web.HTTPNotFound()
        return web.FileResponse(folder / name)
    async def reset_session(request):
        response = web.Response(status=303, headers={'Location': '/'})
        response.del_cookie(COOKIE_NAME, path='/')
        return response
    screen = FixtureScreen()
    desktop = FixtureDesktop()
    async def screen_stats(request):
        return web.json_response({'frames': screen.calls})
    async def input_events(request):
        return web.json_response(desktop.events)
    app = await create_app(KEY, f'http://{HOST}:{PORT}', PORT, FixtureControls(), desktop, screen)
    app.router.add_get('/test-images/{name}', test_photo)
    app.router.add_get('/test-reset', reset_session)
    app.router.add_get('/test-screen-stats', screen_stats)
    app.router.add_get('/test-input-events', input_events)
    return app


def main():
    print(f'Pairing fixture: http://{HOST}:{PORT}/', flush=True)
    web.run_app(fixture_app(), host=HOST, port=PORT, access_log=None)


if __name__ == '__main__':
    main()
