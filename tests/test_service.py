from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from laptop_remote import service


class ServiceTests(unittest.TestCase):
    def test_wrong_program_is_never_stopped(self):
        process = Mock()
        process.exe.return_value = str(service.PYTHON)
        process.cmdline.return_value = [process.exe(), str(service.ROOT / 'other_server.py')]
        connection = SimpleNamespace(status=service.psutil.CONN_LISTEN, laddr=SimpleNamespace(port=service.PORT), pid=123)
        with patch('laptop_remote.service.psutil.net_connections', return_value=[connection]), patch('laptop_remote.service.psutil.Process', return_value=process):
            with self.assertRaisesRegex(RuntimeError, 'different Python program'):
                service._stop_server()
        process.terminate.assert_not_called()

    def test_failed_input_release_does_not_kill_server(self):
        process = Mock()
        with patch('laptop_remote.service.running_server', return_value=process), patch('laptop_remote.service.prepare_shutdown', side_effect=RuntimeError('Release failed')):
            with self.assertRaisesRegex(RuntimeError, 'Release failed'):
                service.stop_server()
        process.terminate.assert_not_called()

    def test_unpair_requires_stop_before_key_rotation_and_restart(self):
        actions = Mock()
        with patch('laptop_remote.service._stop_server', actions.stop), patch('laptop_remote.service.rotate_token', actions.rotate), patch('laptop_remote.service._start_server', actions.start):
            service.unpair_all()
            self.assertEqual([call[0] for call in actions.mock_calls], ['stop', 'rotate', 'start'])
            actions.reset_mock()
            actions.stop.side_effect = RuntimeError('Stop failed')
            with self.assertRaisesRegex(RuntimeError, 'Stop failed'):
                service.unpair_all()
            actions.rotate.assert_not_called()
            actions.start.assert_not_called()
