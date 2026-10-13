#!/usr/bin/env python3
"""Retry failed recipe jobs, retaining successes and all raw attempt folders."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
from benchmark import ROOT, read_json, export_reports, summary, write_json

def retry_jobs(run_dir, rounds=5, workers=6, timeout=120):
    manifest = read_json(run_dir / 'manifest.json')
    rows = [json.loads(line) for line in (run_dir / 'results.jsonl').read_text().splitlines() if line.strip()]
    if len(rows) != manifest['requests_planned'] or manifest['repeats'] != 1 or manifest.get('dry_run'):
        raise ValueError('Retry requires a completed live single-repeat run')
    original = run_dir / 'initial-results.jsonl'
    if not original.exists():
        original.write_text((run_dir / 'results.jsonl').read_text())
    current = {(r['model'], r['profile_id']): r for r in rows}
    for number in range(1, rounds + 1):
        pending = [key for key,r in current.items() if r['status'] != 'ok']
        if not pending:
            break
        print(f'Retry round {number}/{rounds}: {len(pending)} failed jobs', flush=True)
        def run(key):
            model, profile = key
            folder = run_dir / 'retries' / f'round-{number}' / f'job-{pending.index(key)}'
            folder.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run([sys.executable,str(ROOT/'scripts/benchmark.py'),'--method','practical',
                '--models',model,'--profile',profile,'--repeats','1','--workers','1','--retries','0',
                '--timeout',str(timeout),'--out',str(folder)],capture_output=True,text=True)
            if result.returncode not in (0,1) or not (folder/'results.jsonl').exists():
                raise ValueError('Retry subprocess did not produce a complete result')
            attempted = read_json(folder/'manifest.json')
            for field in ('ingredient_catalog','preparation','prompt_version','unit_ml'):
                if attempted[field] != manifest[field]:
                    raise ValueError('Retry config differs from original run')
            records = [json.loads(line) for line in (folder/'results.jsonl').read_text().splitlines() if line.strip()]
            if len(records) != 1:
                raise ValueError('Retry did not produce exactly one job')
            return key, records[0]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(run,key) for key in pending]):
                key, record = future.result()
                record['recipe_retry_round'] = number
                current[key] = record
                print(f'{key[0]} / {key[1]}: {record["status"]}',flush=True)
        rows = list(current.values())
        (run_dir/'results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in rows))
        write_json(run_dir/'summary.json',summary(rows));export_reports(run_dir,rows)
    return sum(r['status'] != 'ok' for r in current.values())

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--rounds',type=int,default=5)
    p.add_argument('--workers',type=int,default=6);p.add_argument('--timeout',type=float,default=120)
    args=p.parse_args()
    if args.rounds<1 or args.workers<1 or args.timeout<=0:p.error('rounds, workers and timeout must be positive')
    remaining=retry_jobs(args.run_dir,args.rounds,args.workers,args.timeout)
    print(f'Retries finished; {remaining} jobs still unsuccessful')
