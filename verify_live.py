"""Exercise the real API and restore the initial Windows controls."""

import asyncio
import time

import aiohttp
from pycaw.pycaw import AudioUtilities

from server import COOKIE_NAME
from pairing_keys import load_token
from settings import PORT


async def main():
    address = f'http://127.0.0.1:{PORT}'
    volume = AudioUtilities.GetSpeakers().EndpointVolume
    original_volume = volume.GetMasterVolumeLevelScalar() * 100
    original_mute = bool(volume.GetMute())
    async with aiohttp.ClientSession(headers={'X-Remote-Request': '1'}, cookies={COOKIE_NAME: load_token()}) as client:
        async def state():
            async with client.get(address + '/api/state') as response:
                response.raise_for_status()
                return await response.json()

        async def command(action, value=None):
            body = {'action': action}
            if value is not None:
                body['value'] = value
            async with client.post(address + '/api/command', json=body) as response:
                result = await response.json()
                if response.status != 200:
                    raise RuntimeError(result)

        async def wait_status(expected):
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                current = await state()
                if current['media'] and current['media']['status'] == expected:
                    return
            raise AssertionError('Player did not report ' + expected)

        initial = await state()
        playback_attempted = False
        original_status = initial['media']['status'] if initial['media'] else None
        restore_action = 'play' if original_status == 'playing' else 'pause'
        try:
            target = max(0, round(original_volume) - 1)
            await command('volume', target)
            assert (await state())['volume'] == target
            print('PASS: actual Windows volume changed and read back')
            await command('mute', not original_mute)
            assert (await state())['muted'] is not original_mute
            print('PASS: actual Windows mute changed and read back')
            media = initial['media']
            if not media or original_status not in {'playing', 'paused'}:
                raise RuntimeError('Cannot complete live playback check: a playing or paused session is required.')
            action = 'pause' if original_status == 'playing' else 'play'
            if not media['can_' + action]:
                raise RuntimeError('The current player does not support ' + action)
            playback_attempted = True
            await command(action)
            await wait_status('paused' if action == 'pause' else 'playing')
            print('PASS: ' + action + ' changed the actual player state')
            await command(restore_action)
            await wait_status(original_status)
            playback_attempted = False
            print('PASS: ' + restore_action + ' restored the actual player state')
        finally:
            # Restore even after an assertion/timeout, without changing source media.
            volume.SetMasterVolumeLevelScalar(original_volume / 100, None)
            volume.SetMute(int(original_mute), None)
            if playback_attempted:
                await command(restore_action)
                await wait_status(original_status)
            assert abs(volume.GetMasterVolumeLevelScalar() * 100 - original_volume) < 0.001
            assert bool(volume.GetMute()) == original_mute
            print('PASS: original Windows volume, mute and playback restored')


if __name__ == '__main__':
    asyncio.run(main())
