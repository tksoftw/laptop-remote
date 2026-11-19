"""Windows-protected pairing credentials, independent of server/UI lifetimes."""
import os
import secrets

import win32crypt

from .settings import STATE_DIR

TOKEN_FILE = STATE_DIR / 'pairing-key.dpapi'


def encrypted_token(token):
    return win32crypt.CryptProtectData(token.encode('ascii'), 'Laptop Remote pairing key', None, None, None, 0)


def load_token():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        token = win32crypt.CryptUnprotectData(TOKEN_FILE.read_bytes(), None, None, None, 0)[1].decode('ascii')
        if len(token) != 43 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in token):
            raise RuntimeError('The saved pairing key is invalid. Use Unpair all devices to replace it.')
        return token
    token = secrets.token_urlsafe(32)
    with TOKEN_FILE.open('xb') as file:
        file.write(encrypted_token(token))
    return token


def rotate_token():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    temporary = TOKEN_FILE.with_name('pairing-key-' + secrets.token_hex(8) + '.tmp')
    with temporary.open('xb') as file:
        file.write(encrypted_token(token))
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, TOKEN_FILE)
