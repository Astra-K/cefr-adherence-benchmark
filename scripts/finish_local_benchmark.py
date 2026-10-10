"""Bounded completion verifier for an already-running subscription benchmark.
Reads state only while waiting; does not launch inference or signal any process.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[1]


def process_identity(pid):
    proc = subprocess.run(['/bin/ps','-p',str(pid),'-o','lstart=,command='],text=True,capture_output=True)
    return proc.stdout.strip() if proc.returncode==0 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args = parser.parse_args()
    original = process_identity(args.pid)
    if original is not None and 'scripts/judge_subscription.py' not in original:
        raise RuntimeError('PID is not the expected benchmark judge')
    deadline = time.monotonic()+5400
    print('WAITING_FOR_SUBSCRIPTION_BENCHMARK '+str(args.pid),flush=True)
    while time.monotonic() < deadline:
        manifest_path = args.out_dir/'subscription.manifest.json'
        try:
            manifest = json.loads(manifest_path.read_text())
        except (FileNotFoundError,json.JSONDecodeError):
            manifest = {}
        if manifest.get('state') == 'complete':
            result = subprocess.run([sys.executable,str(ROOT/'scripts/verify_local_benchmark.py'),
                                     '--out-dir',str(args.out_dir)],cwd=ROOT)
            if result.returncode:
                raise SystemExit(result.returncode)
            print('VERIFIED_BENCHMARK_REPORT '+str(args.out_dir/'REPORT.md'),flush=True)
            return
        current = process_identity(args.pid)
        if current is None or current != original:
            raise RuntimeError('Judge exited or PID changed before completion; no final result claimed')
        time.sleep(10)
    raise RuntimeError('Completion verification wait exceeded 90 minutes; judge not signalled')


if __name__=='__main__':
    main()
