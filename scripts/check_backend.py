"""Run collector unittest checks with private state isolated before imports."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    collector = Path(__file__).resolve().parent.parent / 'ai-finance-collector'
    with tempfile.TemporaryDirectory(prefix='info-hunter-tests-') as temporary:
        root = Path(temporary)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                   RADAR_DATA_DIR=str(root / 'data'), RADAR_BACKUP_DIR=str(root / 'backups'),
                   RADAR_CONNECTIONS_FILE=str(root / 'connections.local.json'),
                   RADAR_NATIVE_DATA=str(root / 'native'), HF_HUB_OFFLINE='1')
        args = sys.argv[1:] or ['discover', '-p', 'test_*.py']
        return subprocess.call([sys.executable, '-B', '-m', 'unittest', *args], cwd=collector, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
