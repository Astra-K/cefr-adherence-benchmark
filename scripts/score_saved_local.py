"""Score frozen local answers using the exact generated Kaggle scorer.
No model or network calls. Unknown relevance is always labelled provisional.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'kaggle_task'))
import cefr_scorer_embedded as embedded


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs(paths):
    items = json.loads((ROOT/'data/items.json').read_text())
    expected = {f"{i['id']}:{level}:{condition}" for i in items
                for level in ('A1','B1','C1') for condition in ('bare','informed')}
    texts = {i['id']:i['text'] for i in items}
    rows, hashes = [], {}
    for path in paths:
        hashes[str(path.resolve())] = sha(path)
        manifest = json.loads(path.with_suffix('.manifest.json').read_text())
        if manifest['identity']['dataset_sha256'] != sha(ROOT/'data/items.json'):
            raise ValueError('Dataset differs from generation manifest')
        group = [json.loads(line) for line in path.read_text().splitlines()]
        if len(group) != len(expected) or {r['key'] for r in group} != expected:
            raise ValueError('Incomplete or duplicate answer set')
        for row in group:
            if row['run_fingerprint'] != manifest['run_fingerprint'] or row['item_text'] != texts[row['item_id']]:
                raise ValueError('Answer provenance differs from frozen input')
            if not row['reply'].strip():
                raise ValueError('Empty answer')
        rows.extend(group)
    if len({(r['model'], r['key']) for r in rows}) != len(rows):
        raise ValueError('Duplicate model/key across inputs')
    return rows, hashes


def summarize(rows):
    summaries = []
    for model in sorted({r['model'] for r in rows}):
        for level in ('A1','B1','C1'):
            for condition in ('bare','informed'):
                group = [r for r in rows if (r['model'],r['level'],r['condition']) == (model,level,condition)]
                scored = [r for r in group if r.get('score') is not None]
                summaries.append({'model':model,'level':level,'condition':condition,'n':len(group),
                    'scored':len(scored),'unscored':len(group)-len(scored),
                    'mean_score':round(statistics.mean(r['score']['combined'] for r in scored),4) if scored else None,
                    'cefr_adherent_count':sum(r['score']['adherent'] for r in scored),
                    'relevant_adherent_count':sum(r['score']['adherent'] and r['relevance'] is True for r in scored),
                    'relevance_pass':sum(r['relevance'] is True for r in group),
                    'relevance_fail':sum(r['relevance'] is False for r in group),
                    'gate_fail_count':sum('gate_fail' in r['score']['flags'] for r in scored),
                    'truncated':sum(r['finish_reason']=='length' for r in group),
                    'mean_output_tokens':round(statistics.mean(r['completion_tokens'] for r in group),1)})
    return summaries


def write_summary(path, rows):
    summary = summarize(rows)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs', type=Path, nargs='+', required=True)
    ap.add_argument('--out-dir', type=Path, required=True)
    args = ap.parse_args()
    rows, hashes = load_inputs(args.inputs)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir/'mechanical.jsonl'
    with path.open('x') as handle:
        scored = []
        for row in rows:
            diagnostic = embedded.score_reply(row['reply'],row['level'],relevant=True)
            result = {k:row[k] for k in ('model','key','item_id','level','condition','reply','item_text','finish_reason','completion_tokens')}
            result.update(relevance=None, final_score=None, score=diagnostic,
                          status='provisional_assuming_relevance',
                          original_diagnostic=row['mechanical_diagnostics_assuming_relevance'])
            scored.append(result)
            handle.write(json.dumps(result,ensure_ascii=False)+'\n')
    summary = write_summary(args.out_dir/'mechanical_summary.csv',scored)
    manifest = {'status':'provisional_assuming_relevance','inputs':hashes,'n':len(scored),
                'scorer_sha256':sha(ROOT/'kaggle_task/cefr_scorer_embedded.py'),
                'changed_scores':sum(r['score']!=r['original_diagnostic'] for r in scored),
                'final_results':False,'summary':summary}
    (args.out_dir/'mechanical.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for source, digest in hashes.items():
        assert sha(Path(source)) == digest, 'Raw acquisition changed during scoring'
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    main()
