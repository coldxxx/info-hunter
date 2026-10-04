"""Run native HTTP checks with the native Python dependency environment."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    native = Path(__file__).resolve().parent.parent / 'ai-finance-collector' / 'native'
    with tempfile.TemporaryDirectory(prefix='info-hunter-native-tests-') as temporary:
        root = Path(temporary)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1',
                   RADAR_NATIVE_DATA=str(root / 'native'), RADAR_DATA_DIR=str(root / 'data'),
                   RADAR_BACKUP_DIR=str(root / 'backups'),
                   RADAR_CONNECTIONS_FILE=str(root / 'connections.local.json'))
        return subprocess.call([sys.executable, '-B', '-m', 'unittest', 'discover',
                                '-s', str(native), '-p', 'test_service.py'], cwd=native, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
