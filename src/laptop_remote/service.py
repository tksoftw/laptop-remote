"""Start and stop the verified listener; never depend on a saved PID file."""
from contextlib import contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

import psutil
import win32event

from .pairing_keys import load_token, rotate_token
from .settings import PORT, PYTHON, ROOT, STATE_DIR

ADDRESS = f'http://127.0.0.1:{PORT}'
SERVER_ARGS = ['-u', '-m', 'laptop_remote.server']
INSTANCE_NAME = 'Local\\LaptopRemote-' + hashlib.sha256(str(ROOT).encode()).hexdigest()[:16]
LOG = logging.getLogger('laptop_remote.service')


@contextmanager
def operation_lock():
    handle = win32event.CreateMutex(None, False, INSTANCE_NAME + '-operations')
    acquired = False
    try:
        result = win32event.WaitForSingleObject(handle, 30000)
        acquired = result in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED)
        if result == win32event.WAIT_ABANDONED:
            raise RuntimeError('A previous remote action was interrupted. Try the action again to check the current server.')
        if not acquired:
            raise RuntimeError('Another remote action is still running. Try again shortly.')
        yield
    finally:
        if acquired:
            win32event.ReleaseMutex(handle)
        handle.Close()


def verify_server(process):
    interpreters = {PYTHON, Path(sys._base_executable).with_name('python.exe')}
    command = process.cmdline()
    if Path(process.exe()) not in interpreters:
        raise RuntimeError(f'Port {PORT} is occupied by a different program. It was left untouched.')
    if command[1:] != SERVER_ARGS or Path(process.cwd()).resolve() != ROOT:
        raise RuntimeError(f'Port {PORT} is occupied by a different Python program. It was left untouched.')
    return process


def running_server():
    connections = [c for c in psutil.net_connections(kind='tcp4') if c.status == psutil.CONN_LISTEN and c.laddr.port == PORT]
    if not connections:
        return None
    pids = {c.pid for c in connections}
    if None in pids or len(pids) != 1:
        raise RuntimeError(f'Cannot identify one owner of port {PORT}. No process was changed.')
    return verify_server(psutil.Process(pids.pop()))


def check_health():
    try:
        with urllib.request.urlopen(ADDRESS + '/health', timeout=3) as response:
            result = json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError(f'Laptop Remote is listening but did not respond correctly. See {STATE_DIR / "server.log"}.') from exc
    if result != {'app': 'laptop-remote', 'ready': True}:
        raise RuntimeError(f'Port {PORT} returned an unexpected service response.')


def terminate_started_process(process):
    if process.poll() is not None:
        return
    parent = psutil.Process(process.pid)
    children = parent.children(recursive=True)
    console_host = Path(os.environ['SystemRoot']) / 'System32' / 'conhost.exe'
    for child in children:
        if Path(child.exe()) != console_host:
            verify_server(child)
    for child in reversed(children):
        child.terminate()
    if parent.is_running():
        parent.terminate()
    _, alive = psutil.wait_procs(children + [parent], timeout=5)
    if alive:
        raise RuntimeError('The failed startup left a process running. Check the startup log.')


def _start_server():
    existing = running_server()
    if existing is not None:
        check_health()
        LOG.info('Reusing verified server PID %s', existing.pid)
        return existing
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with (STATE_DIR / 'startup.log').open('a', encoding='utf-8') as errors:
        process = subprocess.Popen(
            [str(PYTHON), *SERVER_ARGS],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors,
            text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        try:
            try:
                ready = lines.get(timeout=25)
            except queue.Empty as exc:
                raise RuntimeError(f'Server startup timed out. See {STATE_DIR / "startup.log"}.') from exc
            if ready.strip() != 'READY':
                raise RuntimeError(f'Server startup failed. See {STATE_DIR / "startup.log"}.')
            server = running_server()
            if server is None:
                raise RuntimeError('The server exited before it was ready.')
            check_health()
        except Exception:
            terminate_started_process(process)
            raise
        finally:
            process.stdout.close()
    LOG.info('Started verified server PID %s', server.pid)
    return server


def _stop_server():
    process = running_server()
    if process is None:
        LOG.info('Remote is already stopped')
        return
    prepare_shutdown()
    process.terminate()
    try:
        process.wait(timeout=5)
    except psutil.TimeoutExpired as exc:
        raise RuntimeError('The remote did not stop within five seconds.') from exc
    if running_server() is not None:
        raise RuntimeError('A remote server is still listening after Stop.')
    LOG.info('Stopped verified server PID %s', process.pid)


def prepare_shutdown():
    request = urllib.request.Request(ADDRESS + '/api/shutdown', data=b'', headers={
        'X-Remote-Request': '1', 'Cookie': 'laptop_remote_session=' + load_token(),
    })
    with urllib.request.urlopen(request, timeout=5) as response:
        if json.load(response) != {'stopping': True}:
            raise RuntimeError('The remote could not release its held input. It was not stopped.')


def start_server():
    with operation_lock():
        return _start_server()


def stop_server():
    with operation_lock():
        _stop_server()


def pair_phone():
    process = start_server()
    if not webbrowser.open(ADDRESS + '/pair'):
        raise RuntimeError(f'The browser could not open. Open {ADDRESS}/pair on this laptop.')
    return process


def unpair_all():
    with operation_lock():
        _stop_server()
        rotate_token()
        LOG.info('Revoked all paired devices')
        return _start_server()
