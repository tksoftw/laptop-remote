from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pairing_keys
import service


class ServiceTests(unittest.TestCase):
    def test_running_server_identifies_socket_owner_without_pid_file(self):
        process = Mock()
        process.exe.return_value = str(service.ROOT / '.venv' / 'Scripts' / 'python.exe')
        process.cmdline.return_value = [process.exe(), '-u', str(service.ROOT / 'server.py')]
        connection = SimpleNamespace(status=service.psutil.CONN_LISTEN, laddr=SimpleNamespace(port=service.PORT), pid=123)
        with patch('service.psutil.net_connections', return_value=[connection]), patch('service.psutil.Process', return_value=process):
            self.assertIs(service.running_server(), process)

    def test_wrong_program_is_never_stopped(self):
        process = Mock()
        process.exe.return_value = str(service.ROOT / '.venv' / 'Scripts' / 'python.exe')
        process.cmdline.return_value = [process.exe(), str(service.ROOT / 'other_server.py')]
        connection = SimpleNamespace(status=service.psutil.CONN_LISTEN, laddr=SimpleNamespace(port=service.PORT), pid=123)
        with patch('service.psutil.net_connections', return_value=[connection]), patch('service.psutil.Process', return_value=process):
            with self.assertRaisesRegex(RuntimeError, 'different Python program'):
                service._stop_server()
        process.terminate.assert_not_called()

    def test_open_reuses_running_server(self):
        process = Mock()
        with patch('service.running_server', return_value=process), patch('service.check_health') as health, patch('service.subprocess.Popen') as spawn:
            self.assertIs(service.start_server(), process)
            health.assert_called_once()
            spawn.assert_not_called()

    def test_stop_of_stopped_service_is_successful(self):
        with patch('service.running_server', return_value=None):
            service.stop_server()

    def test_stop_targets_actual_listener_and_waits(self):
        process = Mock()
        with patch('service.running_server', side_effect=[process, None]), patch('service.prepare_shutdown') as release:
            service.stop_server()
            release.assert_called_once()
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)

    def test_failed_input_release_does_not_kill_server(self):
        process = Mock()
        with patch('service.running_server', return_value=process), patch('service.prepare_shutdown', side_effect=RuntimeError('Release failed')):
            with self.assertRaisesRegex(RuntimeError, 'Release failed'):
                service.stop_server()
        process.terminate.assert_not_called()

    def test_unpair_stops_then_rotates_then_restarts(self):
        actions = Mock()
        with patch('service._stop_server', actions.stop), patch('service.rotate_token', actions.rotate), patch('service._start_server', actions.start):
            service.unpair_all()
        self.assertEqual([call[0] for call in actions.mock_calls], ['stop', 'rotate', 'start'])

    def test_failed_stop_does_not_rotate_key(self):
        with patch('service._stop_server', side_effect=RuntimeError('Stop failed')), patch('service.rotate_token') as rotate, patch('service._start_server') as start:
            with self.assertRaisesRegex(RuntimeError, 'Stop failed'):
                service.unpair_all()
            rotate.assert_not_called()
            start.assert_not_called()

    def test_rotation_is_persistent_and_changes_key(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch('pairing_keys.STATE_DIR', folder), patch('pairing_keys.TOKEN_FILE', folder / 'key.dpapi'):
                original = pairing_keys.load_token()
                pairing_keys.rotate_token()
                changed = pairing_keys.load_token()
                self.assertNotEqual(original, changed)
                self.assertEqual(changed, pairing_keys.load_token())
                self.assertNotIn(changed.encode(), (folder / 'key.dpapi').read_bytes())


if __name__ == '__main__':
    unittest.main()
