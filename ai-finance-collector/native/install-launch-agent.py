#!/usr/bin/env python3
"""Install this project's native companion in the current macOS login session."""
import os
from pathlib import Path
import plistlib
import subprocess
import sys

if sys.platform != 'darwin':
    raise SystemExit('This installer requires macOS.')
base = Path(__file__).resolve().parent
data = base.parent / 'data' / 'native'
data.mkdir(parents=True, exist_ok=True)
data.chmod(0o700)
label = 'com.herman.signal-radar.native'
folder = Path.home() / 'Library' / 'LaunchAgents'
folder.mkdir(parents=True, exist_ok=True)
target = folder / (label + '.plist')
domain = 'gui/' + str(os.getuid())
config = {
    'Label': label,
    'ProgramArguments': ['/bin/sh', str(base / 'start.sh')],
    'WorkingDirectory': str(base),
    'RunAtLoad': True,
    'KeepAlive': True,
    'ThrottleInterval': 15,
    'StandardOutPath': str(data / 'service.log'),
    'StandardErrorPath': str(data / 'service.log'),
    'EnvironmentVariables': {'RADAR_NATIVE_DATA': str(data)},
}
for log in (data / 'service.log',):
    log.touch(mode=0o600, exist_ok=True)
    log.chmod(0o600)
subprocess.run(['launchctl', 'bootout', domain + '/' + label], capture_output=True)
temporary = target.with_suffix('.tmp')
temporary.write_bytes(plistlib.dumps(config))
temporary.chmod(0o600)
temporary.replace(target)
subprocess.run(['launchctl', 'bootstrap', domain, str(target)], check=True)
print('Installed:', target)
print('Native API: http://127.0.0.1:43202 (local token required)')
