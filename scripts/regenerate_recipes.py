#!/usr/bin/env python3
"""CI recipe generation: publish usable complete runs, retaining API failures."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from benchmark import ROOT, read_json


def validate_run(run_dir):
    manifest = read_json(run_dir / 'manifest.json')
    records = [json.loads(line) for line in (run_dir / 'results.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    if manifest.get('dry_run') or len(records) != manifest['requests_planned']:
        raise ValueError('Benchmark did not finish; existing site recipes will be preserved')
    valid = sum(r['status'] == 'ok' for r in records)
    if not valid:
        raise ValueError('Benchmark produced no usable recipes; existing site recipes will be preserved')
    return valid, len(records) - valid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5 or not 1 <= args.workers <= 8:
        parser.error('repeats must be 1–5 and workers must be 1–8')
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/benchmark.py'), '--method', 'practical',
                             '--out', str(args.out), '--repeats', str(args.repeats), '--workers', str(args.workers), '--retries', '0'])
    if result.returncode not in (0, 1):
        return result.returncode
    try:
        valid, failed = validate_run(args.out)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(f'Completed benchmark: {valid} usable recipes, {failed} failed or empty jobs', flush=True)
    if failed:
        print('::warning::Some recipe jobs failed; inspect the benchmark-results artifact for errors.')
    return subprocess.run([sys.executable, str(ROOT / 'scripts/refresh_site.py'), '--run-dir', str(args.out)]).returncode


if __name__ == '__main__':
    sys.exit(main())
