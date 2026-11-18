"""Fetch the pinned ZXing browser reader, verifying npm's published SHA-512."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request

URL = 'https://registry.npmjs.org/zxing-wasm/-/zxing-wasm-3.1.7.tgz'
SHA512 = 'LI94ndlOY+xoqlkNcc0EwByrMpUXKrCX171EQ38kGWqpiRq/gcnC+ZrbRipvxI3uV4LaDtNlKo1p9Uayg1sesQ=='
CPP_COMMIT = 'f19f7c6e0509fe0eeb822bf35c41b0f637dec290'
CPP_LICENSE_SHA256 = 'c6596eb7be8581c18be736c846fb9173b69eccf6ef94c5135893ec56bd92ba08'


def main():
    with urllib.request.urlopen(URL, timeout=30) as response:
        archive = response.read()
    if base64.b64encode(hashlib.sha512(archive).digest()).decode() != SHA512:
        raise RuntimeError('The ZXing download does not match its published SHA-512.')
    with urllib.request.urlopen(f'https://raw.githubusercontent.com/zxing-cpp/zxing-cpp/{CPP_COMMIT}/LICENSE', timeout=30) as response:
        license_text = response.read()
    if hashlib.sha256(license_text).hexdigest() != CPP_LICENSE_SHA256:
        raise RuntimeError('The ZXing C++ license does not match its pinned SHA-256.')
    destination = Path(__file__).resolve().parent / 'web' / 'vendor'
    destination.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as package:
        for member, name in [('package/dist/iife/reader/index.js', 'zxing-reader.js'), ('package/dist/reader/zxing_reader.wasm', 'zxing_reader.wasm'), ('package/LICENSE', 'zxing-LICENSE.txt')]:
            file = package.extractfile(member)
            if file is None:
                raise RuntimeError('Missing vendor file: ' + member)
            (destination / name).write_bytes(file.read())
    (destination / 'zxing-cpp-LICENSE.txt').write_bytes(license_text)
    print('Vendored ZXing WASM 3.1.7; SHA-512 verified.')


if __name__ == '__main__':
    main()
