"""Windows media sessions and the default output's master volume."""

import asyncio
import math
import platform

from pycaw.pycaw import AudioUtilities
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
from errors import ControlError


class WindowsMedia:
    def __init__(self, manager):
        self.manager = manager
        self.lock = asyncio.Lock()

    @classmethod
    async def create(cls):
        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        instance = cls(manager)
        instance.audio()
        return instance

    @staticmethod
    def audio():
        device = AudioUtilities.GetSpeakers()
        if device is None:
            raise ControlError('Windows has no default audio output. Connect speakers or headphones.')
        return device

    async def state(self):
        device = self.audio()
        endpoint = device.EndpointVolume
        result = {
            'computer': platform.node(),
            'output': device.FriendlyName,
            'volume': round(endpoint.GetMasterVolumeLevelScalar() * 100),
            'muted': bool(endpoint.GetMute()),
            'media': None,
        }
        session = self.manager.get_current_session()
        if session is not None:
            info = session.get_playback_info()
            properties = await session.try_get_media_properties_async()
            controls = info.controls
            result['media'] = {
                'title': properties.title,
                'artist': properties.artist,
                'app': session.source_app_user_model_id,
                'status': info.playback_status.name.lower(),
                'can_play': controls.is_play_enabled,
                'can_pause': controls.is_pause_enabled,
            }
        return result

    async def command(self, data):
        if not isinstance(data, dict) or not isinstance(data.get('action'), str):
            raise ControlError('A command must contain an action.')
        action = data['action']
        expected_keys = {'action', 'value'} if action in {'volume', 'mute'} else {'action'}
        if set(data) != expected_keys:
            raise ControlError('The command has missing or unexpected fields.')
        if action == 'volume':
            value = data['value']
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
                raise ControlError('Volume must be a number from 0 to 100.')
            self.audio().EndpointVolume.SetMasterVolumeLevelScalar(value / 100, None)
        elif action == 'mute':
            if type(data['value']) is not bool:
                raise ControlError('Mute must be true or false.')
            self.audio().EndpointVolume.SetMute(int(data['value']), None)
        elif action in {'play', 'pause'}:
            session = self.manager.get_current_session()
            if session is None:
                raise ControlError('No player found. Start a video or song on your laptop.')
            controls = session.get_playback_info().controls
            supported = controls.is_play_enabled if action == 'play' else controls.is_pause_enabled
            if not supported:
                raise ControlError('The player does not support this action.')
            method = session.try_play_async if action == 'play' else session.try_pause_async
            if not await method():
                raise ControlError('The player rejected the command. Check the player on your laptop.')
        else:
            raise ControlError('Unknown action. Supported actions: play, pause, volume, mute.')
