"""Explicit paid judging stage for saved local/API answers (never auto-started).
Same relevance prompt/probes as Kaggle. Input must be frozen before invoking.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'kaggle_task'))
from cefr_bench.relevance_api import RelevanceClient
from cefr_bench.relevance import relevance_prompt,relevance_probes
import cefr_scorer_embedded as embedded


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs',type=Path,nargs='+',required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--judge-model',required=True)
    ap.add_argument('--judge-provider',required=True,help='Pin one route; no fallbacks')
    ap.add_argument('--max-cost-usd',type=float,required=True,help='Explicit approved budget; no default paid calls')
    args = ap.parse_args()
    if args.max_cost_usd<=0:
        raise SystemExit('Positive explicit budget required before any judge calls')
    key = os.getenv('OPENROUTER_API_KEY')
    if not key:
        raise SystemExit('OPENROUTER_API_KEY missing; no calls made')
    source_hashes,rows = {},[]
    for path in args.inputs:
        source_hashes[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if not row.get('reply') or not row.get('item_text'):
                raise SystemExit('Input must carry real nonempty reply and original item_text; generation failures are separate')
            rows.append(row)
    catalog = json.load(urllib.request.urlopen('https://openrouter.ai/api/v1/models',timeout=30))
    model = next(x for x in catalog['data'] if x['id']==args.judge_model)
    pin,pout = float(model['pricing']['prompt']),float(model['pricing']['completion'])
    prompts = [relevance_prompt(q,r) for _,q,r in relevance_probes()]
    prompts += [relevance_prompt(r['item_text'],r['reply']) for r in rows]
    # UTF-8 bytes plus framing is a deliberately conservative token envelope,
    # rather than pretending the local model tokenizer matches the API judge.
    ceiling = sum((len(p.encode())+512)*pin + 512*pout for p in prompts)
    if ceiling > args.max_cost_usd:
        raise SystemExit(f'Conservative judge cost ${ceiling:.3f} exceeds approved ${args.max_cost_usd:.3f}; no paid calls')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    if args.out.exists():
        raise SystemExit('Output exists; preserve it and use a new path. Never duplicate/relabel judge results.')
    client = RelevanceClient(key,args.judge_model,args.judge_provider)
    validation = client.validate()
    manifest = {'inputs':source_hashes,'judge_model':args.judge_model,'judge_provider':args.judge_provider,
                'pricing':model['pricing'],'approved_cap_usd':args.max_cost_usd,
                'conservative_envelope_usd':ceiling,'preflight':validation,
                'shared_protocol_sha256':hashlib.sha256((ROOT/'src/cefr_bench/relevance.py').read_bytes()).hexdigest(),
                'scorer_sha256':hashlib.sha256((ROOT/'kaggle_task/cefr_scorer_embedded.py').read_bytes()).hexdigest()}
    args.out.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with args.out.open('x') as out:
        for row in rows:
            result = dict(row)
            try:
                passed = client.assess(row['item_text'],row['reply'])
                score = embedded.score_reply(row['reply'],row['level'],relevant=passed)
                result.update(relevance=passed,score=score,final_score=score['combined'],
                              status='scored',judge_report=client.reports[-1])
            except Exception as error:
                result.update(relevance=None,score=None,final_score=None,status='unscored_judge_error',
                              judge_error=type(error).__name__)
            out.write(json.dumps(result,ensure_ascii=False)+'\n')
            out.flush()
            os.fsync(out.fileno())
    print(f'JUDGING_FINISHED {len(rows)} rows; errors are unscored, not passes')

if __name__=='__main__':
    main()
