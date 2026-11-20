"""Separate bundled resources from persistent user data."""
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, 'frozen', False))
ROOT = Path(os.environ.get('HIGHSC_ROOT') or (getattr(sys, '_MEIPASS', '') if FROZEN else Path(__file__).resolve().parents[1])).resolve()


def data_path():
    if os.environ.get('HIGHSC_DATA_DIR'):
        return Path(os.environ['HIGHSC_DATA_DIR']).expanduser().resolve()
    if FROZEN:
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local') / 'High_SC'
    return ROOT / 'data'


DATA = data_path().resolve()
