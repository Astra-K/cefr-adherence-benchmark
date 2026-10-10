"""Resumable, resource-guarded local CEFR answer acquisition (no paid calls).
Final relevance-gated scores are deliberately deferred; raw answers are durable.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'scripts'))
from cefr_bench.prompts import bare_prompt, informed_prompt
from cefr_bench.wordlists import get_lists


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def make_plan(items):
    rows = []
    for item in items:
        for level in ('A1','B1','C1'):
            for condition in ('bare','informed'):
                prompt = (bare_prompt(item['text'], level) if condition == 'bare'
                          else informed_prompt(item['text'], level, get_lists()))
                rows.append({'key':f"{item['id']}:{level}:{condition}", 'item_id':item['id'],
                             'question_id':item['question_id'], 'item_text':item['text'],
                             'level':level, 'condition':condition, 'prompt':prompt,
                             'prompt_sha256':sha256(prompt.encode())})
    return rows


def read_completed(path, fingerprint):
    if not path.exists():
        return set()
    done = set()
    with path.open() as handle:
        for n,line in enumerate(handle,1):
            if not line.endswith('\n'):
                raise ValueError(f'Incomplete row {n}; preserve and explicitly repair the tail before resuming')
            row = json.loads(line)
            if row.get('run_fingerprint') != fingerprint:
                raise ValueError('Resume identity mismatch; use a new output directory')
            if row['key'] in done:
                raise ValueError('Duplicate saved key')
            done.add(row['key'])
    return done


def render_prompt(tokenizer, prompt, max_prompt_tokens):
    tokens = tokenizer.apply_chat_template([{'role':'user','content':prompt}],
                                          tokenize=True, add_generation_prompt=True,
                                          enable_thinking=False)
    if len(tokens) > max_prompt_tokens:
        raise ValueError(f'Prompt {len(tokens)} exceeds explicit ceiling {max_prompt_tokens}; never truncate word lists')
    return tokens


def atomic_json(path,data):
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    os.replace(temp,path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size',choices=['2B','9B'],required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=None,help='Smoke-test prefix; full run resumes these same rows')
    parser.add_argument('--max-tokens',type=int,default=512)
    parser.add_argument('--max-prompt-tokens',type=int,default=32768)
    parser.add_argument('--duration-s',type=int,default=14400)
    parser.add_argument('--temperature',type=float,default=0.7)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True,exist_ok=True)
    record = json.loads((ROOT/'configs/local_models_verified.json').read_text())[args.size]
    model_path = Path(record['path'])
    for entry in record['files']:
        if (model_path/entry['name']).stat().st_size != entry['bytes']:
            raise ValueError('Model file size changed after acquisition')
    items = json.loads((ROOT/'data/items.json').read_text())
    plan = make_plan(items)
    runtime = {k:importlib.metadata.version(k) for k in ('mlx-lm','mlx','transformers','huggingface-hub')}
    identity = {'dataset_sha256':sha256((ROOT/'data/items.json').read_bytes()),
                'model':record,'runtime':runtime,'seed':42,'enable_thinking':False,
                'sampling':{'temperature':args.temperature,'top_p':0.8,'top_k':20},
                'max_tokens':args.max_tokens,'max_prompt_tokens':args.max_prompt_tokens,
                'prefill_step_size':256,'condition_prompts':[r['prompt_sha256'] for r in plan],
                'runner_sha256':sha256(Path(__file__).read_bytes()),
                'guard_sha256':sha256((ROOT/'scripts/local_safety.py').read_bytes()),
                'embedded_scorer_sha256':sha256((ROOT/'kaggle_task/cefr_scorer_embedded.py').read_bytes()),
                'status_note':'generation only; relevance and final scores pending'}
    fingerprint = sha256(json.dumps(identity,sort_keys=True).encode())
    path = args.out_dir/f'qwen3.5-{args.size.lower()}.jsonl'
    manifest = args.out_dir/f'qwen3.5-{args.size.lower()}.manifest.json'
    status_path = args.out_dir/f'qwen3.5-{args.size.lower()}.status.json'
    done = read_completed(path,fingerprint)
    if not done <= {x['key'] for x in plan}:
        raise ValueError('Saved keys outside frozen plan')
    if manifest.exists() and json.loads(manifest.read_text())['run_fingerprint'] != fingerprint:
        raise ValueError('Existing manifest identity mismatch')
    atomic_json(manifest,{'run_fingerprint':fingerprint,'identity':identity,'expected_rows':len(plan)})
    selected = plan if args.limit is None else plan[:args.limit]
    pending = [x for x in selected if x['key'] not in done]
    if not pending:
        print(f'ALREADY_COMPLETE {args.size} {len(done)}/{len(plan)}',flush=True)
        return
    from local_safety import MLXGuard
    memory_gb = 5 if args.size == '2B' else 10
    start = time.time()
    base_status = {'model':record['repo'],'expected':len(plan),'run_fingerprint':fingerprint,
                   'output':str(path),'started_epoch':start,'pid':os.getpid()}
    atomic_json(status_path,{**base_status,'state':'preflight','completed':len(done)})
    try:
        with MLXGuard(memory_gb=memory_gb,cache_gb=0.25,duration_s=args.duration_s,
                      allow_over_30min=True,allow_over_8gb=True,
                      lock_path=ROOT/'.local/mlx_job.lock',
                      log_path=args.out_dir/f'qwen3.5-{args.size.lower()}.resources.jsonl') as guard:
            from mlx_lm import load,stream_generate
            from mlx_lm.sample_utils import make_sampler
            print(f'LOAD {args.size} ceiling={memory_gb}GiB watchdog={guard.watchdog_pid}',flush=True)
            model,tokenizer = load(str(model_path))
            # Validate all complete chat templates before generation, without truncation.
            prepared = [(row,render_prompt(tokenizer,row['prompt'],args.max_prompt_tokens)) for row in pending]
            print(f'PROMPTS_VERIFIED max={max(len(tokens) for _,tokens in prepared)} tokens',flush=True)
            atomic_json(status_path,{**base_status,'state':'running','completed':len(done),
                                    'max_prompt_tokens_observed':max(len(t) for _,t in prepared)})
            sys.path.insert(0,str(ROOT/'kaggle_task'))
            import cefr_scorer_embedded as embedded
            with path.open('a') as out:
                for row,tokens in prepared:
                    row_start = time.time()
                    guard.mx.random.seed(42+plan.index(row))
                    segments,last = [],None
                    for segment in stream_generate(model,tokenizer,tokens,max_tokens=args.max_tokens,
                        sampler=make_sampler(temp=args.temperature,top_p=0.8,top_k=20),prefill_step_size=256):
                        segments.append(segment.text)
                        last = segment
                    reply = ''.join(segments)
                    if last is None or not reply.strip():
                        raise RuntimeError(f'Empty generation for {row["key"]}; abort instead of inventing a response')
                    if '<think>' in reply or '</think>' in reply:
                        raise RuntimeError('Non-thinking configuration leaked reasoning; stop pilot')
                    diagnostic = embedded.score_reply(reply,row['level'],relevant=True)
                    saved = {**row,'run_fingerprint':fingerprint,'model':record['repo'],
                             'reply':reply,'finish_reason':last.finish_reason,'latency_s':round(time.time()-row_start,3),
                             'prompt_tokens':last.prompt_tokens,'completion_tokens':last.generation_tokens,
                             'generation_tps':last.generation_tps,'peak_memory_gb':last.peak_memory,
                             'relevance':None,'final_score':None,'status':'generated_relevance_pending',
                             'mechanical_diagnostics_assuming_relevance':diagnostic,
                             'c1_one_token_design_diagnostic':None,
                             'generated_epoch':time.time()}
                    if row['level'] == 'C1':
                        count = sum(embedded.level_of(token, embedded.FORM_LEVELS) in ('B2','C1')
                                    for token in embedded.tokens(reply) if len(token) > 1 and not embedded.is_number(token))
                        saved['c1_one_token_design_diagnostic'] = {'count':count,'met':count>=1,'affects_score':False}
                    out.write(json.dumps(saved,ensure_ascii=False)+'\n')
                    out.flush()
                    os.fsync(out.fileno())
                    done.add(row['key'])
                    guard.step(label=row['key'])
                    elapsed = time.time()-start
                    eta = elapsed/max(1,len(done))*(len(plan)-len(done))
                    atomic_json(status_path,{**base_status,'state':'running','completed':len(done),
                                'last_key':row['key'],'last_finish_reason':last.finish_reason,
                                'elapsed_s':round(elapsed,1),'rough_eta_s':round(eta,1)})
                    print(f'PROGRESS {args.size} {len(done)}/{len(plan)} {row["key"]} '+
                          f'tokens={last.generation_tokens} finish={last.finish_reason} '+
                          f'latency={saved["latency_s"]:.2f}s peak={last.peak_memory:.2f}GB',flush=True)
                    guard.mx.clear_cache()
        complete = len(done) == len(plan)
        atomic_json(status_path,{**base_status,'state':'generation_complete' if complete else 'smoke_complete',
                                'completed':len(done),'elapsed_s':round(time.time()-start,1)})
        print(f'{"GENERATION_COMPLETE" if complete else "SMOKE_COMPLETE"} {args.size} {len(done)}/{len(plan)}',flush=True)
    except BaseException as error:
        atomic_json(status_path,{**base_status,'state':'stopped_error','completed':len(done),
                                'error':f'{type(error).__name__}: {error}'})
        raise

if __name__ == '__main__':
    main()
