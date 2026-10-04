"""Run synthetic boundary checks against real local models, using an isolated DB."""
import argparse
import json
import tempfile
import time
from pathlib import Path
import radar
import semantic

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='verification/qwen-smoke.json')
    args = parser.parse_args()
    cases = json.loads((radar.ROOT / 'fixtures/semantic-smoke.json').read_text())
    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        radar.DB = Path(tmp) / 'verification.sqlite3'
        radar.init()
        with radar.connect() as c:
            config = semantic.settings(c)
            report = semantic.evaluate(c, config, cases)
    result = dict(config=config, synthetic=True, elapsed_seconds=round(time.time()-started, 2), report=report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k,v in report.items() if k != 'predictions'}, ensure_ascii=False))
    for case, prediction in zip(cases, report['predictions']):
        print(case['expected'], '=>', prediction['decision']['relation'], case['left']['title'])
    print('Saved:', output)

if __name__ == '__main__':main()
