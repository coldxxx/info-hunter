"""Start the installed local Qwen models with the identifiers used by the radar."""
import json
import os
import subprocess
from pathlib import Path
import semantic_models as models

def main():
    cli = Path(os.environ.get('RADAR_LMS_BIN', str(Path.home() / '.lmstudio/bin/lms')))
    if not cli.is_file():
        raise SystemExit('未找到 LM Studio CLI，请先安装 LM Studio 或设置 RADAR_LMS_BIN')
    try:
        models.rpc('', '/models', timeout=5)
    except ValueError:
        subprocess.run([str(cli), 'server', 'start', '--port', '1234', '--bind', '127.0.0.1'], check=True)
    loaded = {r['identifier'] for r in json.loads(subprocess.check_output([str(cli), 'ps', '--json']))}
    for key, alias in (('qwen3.6-27b-mlx', 'radar-semantic-judge'),
                       ('text-embedding-qwen3-embedding-0.6b', 'radar-semantic-embedding')):
        if alias not in loaded:
            command = [str(cli), 'load', key, '--identifier', alias, '--context-length',
                       '32768' if alias.endswith('judge') else '8192', '--gpu', 'max', '--yes']
            if alias.endswith('judge'):
                command += ['--parallel', '1']
            subprocess.run(command, check=True)
    result = models.health(models.DEFAULTS)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['ready']:
        raise SystemExit('模型未就绪，请查看 LM Studio 加载状态')

if __name__ == '__main__':main()
