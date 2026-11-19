import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = Path(sys.executable).with_name('python.exe')
STATE_DIR = Path(os.environ['LOCALAPPDATA']) / 'LaptopRemote'
PORT = 48736
