"""Sequential local pilot controller. No paid calls, one GPU model at a time."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/qwen_local_pilot_v2'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    state = {'project':'cefr-adherence-benchmark','pid':os.getpid(),
             'started_epoch':time.time(),'state':'running','model':None}
    status = OUT/'controller.status.json'
    for size in ('2B','9B'):
        state['model'] = size
        status.write_text(json.dumps(state,indent=2)+'\n')
        command = [sys.executable,'-u',str(ROOT/'scripts/local_harness.py'),
                   '--size',size,'--out-dir',str(OUT),'--duration-s','14400']
        print('START_MODEL',size,flush=True)
        with (OUT/f'qwen3.5-{size.lower()}.run.log').open('a') as log:
            result = subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                                    timeout=14700,check=False)
        saved = json.loads((OUT/f'qwen3.5-{size.lower()}.status.json').read_text())
        rows_path = OUT/f'qwen3.5-{size.lower()}.jsonl'
        rows = [json.loads(line) for line in rows_path.read_text().splitlines()] if rows_path.exists() else []
        if result.returncode or saved['state'] != 'generation_complete' or len(rows)!=180 or len({r['key'] for r in rows})!=180:
            state.update(state='stopped_error',exit_code=result.returncode,model_status=saved)
            status.write_text(json.dumps(state,indent=2)+'\n')
            raise SystemExit(f'{size} stopped; preserving outputs. See {OUT}')
        print('VERIFIED_MODEL_GENERATION_COMPLETE',size,len(rows),flush=True)
    state.update(state='generation_complete',finished_epoch=time.time(),
                 note='360 real answers acquired; shared relevance judging and final scores pending')
    status.write_text(json.dumps(state,indent=2)+'\n')
    print('LOCAL_GENERATION_COMPLETE 360 answers; final relevance-scored evaluation still pending',flush=True)

if __name__=='__main__':
    main()
