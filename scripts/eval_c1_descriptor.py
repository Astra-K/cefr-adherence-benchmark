"""Subscription-only experimental C1 descriptor evaluation of frozen text.
Runs labelled controls first; a failed pilot gate blocks the saved-answer sweep.
Never modifies existing scores or model answers. Uses no metered provider fallback.
"""
import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cefr_bench.c1_descriptor import build_prompt, parse_reports, validation_metrics, RUBRIC_VERSION, PILOT_CRITERIA
MODEL = 'gpt-6.1-sol'
PROVIDER = 'openai-codex'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def call_batch(group, stem):
    executable = shutil.which('hermes')
    if not executable:
        raise RuntimeError('Hermes unavailable; no fallback')
    expected = {r['id']:r['text'] for r in group}
    prompt = build_prompt(group)
    env = {k:v for k,v in os.environ.items() if not k.startswith('HERMES_') and k != 'PYTHONPATH'}
    for name in ('OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'ANTHROPIC_API_KEY'):
        env.pop(name, None)
    argv = [executable,'chat','--safe-mode','--provider',PROVIDER,'--model',MODEL,
            '--toolsets','none','--max-turns','1','--reasoning','low','--source','tool',
            '--quiet','--query',prompt]
    for attempt in range(2):
        target = stem if attempt == 0 else stem.with_name(stem.name+'-retry1')
        write_json(target.with_suffix('.prompt.json'), {'model':MODEL, 'provider':PROVIDER, 'prompt':prompt})
        started = time.monotonic()
        proc = subprocess.run(argv, cwd=ROOT, env=env, text=True, capture_output=True, timeout=300)
        target.with_suffix('.stdout.txt').write_text(proc.stdout)
        target.with_suffix('.stderr.txt').write_text(proc.stderr)
        write_json(target.with_suffix('.request.json'), {'returncode':proc.returncode,
                   'elapsed_s':round(time.monotonic()-started,3),'ids':list(expected),
                   'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                   'model':MODEL,'provider':PROVIDER})
        if proc.returncode:
            raise RuntimeError('Subscription descriptor call failed; no fallback; see '+str(target))
        try:
            return parse_reports(proc.stdout, expected)
        except ValueError:
            if attempt:
                raise
            print('RETRY_INVALID_DESCRIPTOR '+stem.name, flush=True)
    raise RuntimeError('No valid descriptor report')


def evaluate(rows, out_dir, phase, workers=2):
    ordered = list(rows)
    random.Random(42).shuffle(ordered)
    groups = [ordered[i:i+3] for i in range(0,len(ordered),3)]
    path = out_dir/(phase+'.jsonl')
    done = {}
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            rid = row['id']
            if rid in done:
                raise ValueError('Duplicate descriptor record')
            done[rid] = row
    expected = {r['id']:r for r in rows}
    if not set(done) <= set(expected):
        raise ValueError('Unexpected resumed descriptor id')
    for rid, row in done.items():
        if row['input'] != expected[rid]:
            raise ValueError('Resume text/metadata changed')
        parse_reports(json.dumps({'assessments':[row['report']]}),{rid:expected[rid]['text']})
    pending = []
    for index, group in enumerate(groups):
        existing = [r['id'] in done for r in group]
        if all(existing):
            continue
        if any(existing):
            raise ValueError('Partial batch; preserve and repair explicitly')
        pending.append((index,group))
    requests = out_dir/'requests'
    requests.mkdir(exist_ok=True)
    # Bounded small concurrent subscription calls; no GPU or model generation.
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool, path.open('a') as out:
        iterator = iter(pending)
        futures = {}
        def submit_next():
            try:
                index, group = next(iterator)
            except StopIteration:
                return
            futures[pool.submit(call_batch, group, requests/f'{phase}-{index:03d}')] = (index, group)
        for _ in range(workers):
            submit_next()
        while futures:
            completed, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in completed:
                index, group = futures.pop(future)
                try:
                    reports = future.result()
                except Exception:
                    for active in futures:
                        active.cancel()
                    raise
                # The complete batch is parsed before any scored record is accepted.
                for r in group:
                    row = {'id':r['id'],'input':r,'report':reports[r['id']],
                           'judge_model':MODEL,'judge_provider':PROVIDER,'rubric_version':RUBRIC_VERSION,
                           'batch':index,'experimental':True}
                    out.write(json.dumps(row,ensure_ascii=False)+'\n')
                    done[r['id']] = row
                out.flush(); os.fsync(out.fileno())
                print(f'{phase.upper()} {len(done)}/{len(rows)}',flush=True)
                submit_next()
    if set(done) != set(expected):
        raise ValueError('Missing descriptor assessments')
    return [done[r['id']] for r in rows]


def verify_sessions(out_dir):
    sessions = []
    db = sqlite3.connect('file:'+str(Path.home()/'.hermes/state.db')+'?mode=ro',uri=True)
    for stderr in sorted((out_dir/'requests').glob('*.stderr.txt')):
        ids = re.findall(r'^session_id:\s*(\S+)',stderr.read_text(), re.M)
        if len(ids) != 1:
            raise ValueError('Missing exact subscription session id')
        sid = ids[0]
        route = db.execute('SELECT model,billing_provider FROM sessions WHERE id=?',(sid,)).fetchone()
        if route != (MODEL,PROVIDER):
            raise ValueError('Descriptor provider/model drift')
        calls = db.execute("SELECT COUNT(*) FROM messages WHERE session_id=? AND (role='tool' OR (tool_calls IS NOT NULL AND tool_calls NOT IN ('[]','null')))",(sid,)).fetchone()[0]
        if calls:
            raise ValueError('Descriptor judge used tools')
        sessions.append(sid)
    db.close()
    return sessions


def summarise(rows, out_dir):
    summaries=[]
    for model in sorted({r['input']['model'] for r in rows}):
        for level in ('A1','B1','C1'):
            for condition in ('bare','informed'):
                sub=[r for r in rows if (r['input']['model'],r['input']['level'],r['input']['condition'])==(model,level,condition)]
                counts={b:sum(r['report']['band']==b for r in sub) for b in ('below_B2','B2','C1','C2','insufficient_evidence')}
                summaries.append({'model':model,'requested_level':level,'condition':condition,'n':len(sub),**counts,
                                  'c1_or_higher':counts['C1']+counts['C2'],
                                  'relevant_c1_or_higher':sum(r['input']['relevance'] and r['report']['c1_status']=='demonstrated' for r in sub),
                                  'truncated':sum(r['input']['finish_reason']=='length' for r in sub)})
    with (out_dir/'summary.csv').open('w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(summaries[0])); writer.writeheader(); writer.writerows(summaries)
    return summaries


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--controls',type=Path,required=True,help='Frozen manifest with cases and provenance')
    ap.add_argument('--saved-answers',type=Path,required=True,help='Existing relevance-scored frozen JSONL')
    ap.add_argument('--out-dir',type=Path,required=True)
    ap.add_argument('--validation-only',action='store_true')
    args=ap.parse_args()
    args.out_dir.mkdir(parents=True,exist_ok=True)
    controls=json.loads(args.controls.read_text())
    cases=controls['cases']
    if len({c['id'] for c in cases})!=len(cases):
        raise ValueError('Duplicate validation input')
    hashes={str(args.controls.resolve()):sha(args.controls), str(args.saved_answers.resolve()):sha(args.saved_answers),
            str(Path(__file__).resolve()):sha(Path(__file__)),str(ROOT/'src/cefr_bench/c1_descriptor.py'):sha(ROOT/'src/cefr_bench/c1_descriptor.py')}
    manifest_path=args.out_dir/'manifest.json'
    manifest={'inputs':hashes,'rubric_version':RUBRIC_VERSION,'judge_model':MODEL,'judge_provider':PROVIDER,
              'criteria':PILOT_CRITERIA,'batch_size':3,'workers':2,'blind':True,'state':'validation',
              'metered_api_calls':False,'certification':False,'controls_provenance':controls['provenance']}
    if manifest_path.exists():
        prior=json.loads(manifest_path.read_text())
        if prior['inputs']!=hashes:
            raise ValueError('Evaluation identity changed; use fresh directory')
    write_json(manifest_path,manifest)
    assessed=evaluate(cases,args.out_dir,'validation')
    labelled=[{'gold':r['input']['gold'],'band':r['report']['band']} for r in assessed if r['input']['kind']=='labelled_corpus']
    metrics=validation_metrics(labelled)
    negatives=[r for r in assessed if r['input']['kind']=='authored_negative_control']
    negative_fp=sum(r['report']['c1_status']=='demonstrated' for r in negatives)
    metrics.update(authored_negative_n=len(negatives),authored_negative_false_positive=negative_fp)
    passed=metrics['pilot_gate_passed'] and bool(negatives) and negative_fp==0
    metrics['combined_pilot_gate_passed']=passed
    metrics['sessions_verified']=verify_sessions(args.out_dir)
    write_json(args.out_dir/'validation_metrics.json',metrics)
    print('VALIDATION_GATE '+str(passed)+' '+json.dumps(metrics),flush=True)
    if not passed:
        manifest.update(state='blocked_validation',validation=metrics)
        write_json(manifest_path,manifest)
        print('SAVED_ANSWER_SWEEP_NOT_STARTED: failed diagnostic gate',flush=True)
        return
    if args.validation_only:
        manifest.update(state='validation_passed',validation=metrics)
        write_json(manifest_path,manifest)
        return
    source=[json.loads(line) for line in args.saved_answers.read_text().splitlines()]
    if len(source)!=360 or len({(r['model'],r['key']) for r in source})!=360:
        raise ValueError('Expected exactly 360 unique frozen local replies')
    source.sort(key=lambda r:(r['model'],r['key']))
    rows=[{'id':f'r{i:03d}','text':r['reply'],'context':r['item_text'],
           **{k:r[k] for k in ('model','key','level','condition','relevance','finish_reason')}} for i,r in enumerate(source)]
    manifest.update(state='saved_answer_diagnostic',validation=metrics,expected=len(rows))
    write_json(manifest_path,manifest)
    reports=evaluate(rows,args.out_dir,'saved_answers')
    summary=summarise(reports,args.out_dir)
    for path,digest in hashes.items():
        if sha(path)!=digest:
            raise ValueError('Frozen input/code changed during evaluation')
    sessions=verify_sessions(args.out_dir)
    manifest.update(state='complete',completed=len(reports),summary=summary,sessions_verified=sessions,
                    verified=True,limitations=controls['provenance'].get('limitations',[])+[
                    'Small pilot gate is not independent CEFR certification or full judge validity.',
                    'Corpus-to-tutor domain shift; single subscription judge; paired arms are controls, not expert labels.',
                    'Batched judging; one model generation per arm; capped/truncated replies are preserved.',
                    'Teaching correctness is outside this descriptor rubric; original final scores remain unchanged.'])
    write_json(manifest_path,manifest)
    lines=['# Experimental C1 descriptor diagnostic','',
           'Original scores preserved. Text-level demonstrated language, not learner/model proficiency certification.',
           'Subscription judge route and no-tool use verified; exact evidence substrings checked.','',
           '| Model | Requested target | Arm | N | Below B2 | B2 | C1 | C2 | Insufficient evidence |',
           '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for s in summary:
        lines.append(f"| {s['model'].split('/')[-1]} | {s['requested_level']} | {s['condition']} | {s['n']} | {s['below_B2']} | {s['B2']} | {s['C1']} | {s['C2']} | {s['insufficient_evidence']} |")
    lines+=['','## Labelled-control pilot',json.dumps(metrics,indent=2),'','## Limitations']+['- '+note for note in manifest['limitations']]
    (args.out_dir/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print('DESCRIPTOR_DIAGNOSTIC_COMPLETE '+str(len(reports)),flush=True)


if __name__=='__main__':
    main()
