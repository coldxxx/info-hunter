"""Build/test a temporary copy without touching running frontend artifacts."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    repository = Path(__file__).resolve().parent.parent
    source = repository / 'ai-finance-radar'
    with tempfile.TemporaryDirectory(prefix='info-hunter-web-') as temporary:
        target = Path(temporary)
        names = subprocess.check_output(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', 'ai-finance-radar/'],
            cwd=repository).decode().split('\0')
        for name in set(filter(None, names)):
            original = repository / name
            if not original.is_file():
                continue
            destination = target / original.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
        modules = target / 'node_modules'
        modules.mkdir()
        for dependency in (source / 'node_modules').iterdir():
            (modules / dependency.name).symlink_to(dependency, target_is_directory=dependency.is_dir())
        commands = [['npm', 'run', 'build:container'], ['npm', 'run', 'build']]
        for command in commands:
            print('Temporary frontend check:', ' '.join(command), flush=True)
            result = subprocess.call(command, cwd=target)
            if result:
                return result
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
