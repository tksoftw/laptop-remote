import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ['LOCALAPPDATA']) / 'LaptopRemote'
PORT = 48736
