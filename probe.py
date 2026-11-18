import asyncio

from pycaw.pycaw import AudioUtilities
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager


async def main():
    manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
    print('Media sessions:', len(manager.get_sessions()))
    for session in manager.get_sessions():
        info = session.get_playback_info()
        print('Player:', session.source_app_user_model_id, 'status:', info.playback_status.name)
    device = AudioUtilities.GetSpeakers()
    if device is None:
        raise RuntimeError('Windows has no default audio output device.')
    print('Audio:', device.FriendlyName, 'volume:', round(device.EndpointVolume.GetMasterVolumeLevelScalar() * 100), 'muted:', bool(device.EndpointVolume.GetMute()))


if __name__ == '__main__':
    asyncio.run(main())
