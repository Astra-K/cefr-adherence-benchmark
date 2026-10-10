"""Independent saved-output verification and concise local benchmark report."""
import argparse
import json
from pathlib import Path
import sqlite3
import statistics
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'src'),str(ROOT/'kaggle_task')]
from score_saved_local import load_inputs, sha, write_summary
from cefr_bench.relevance import parse_relevance_json
import cefr_scorer_embedded as embedded


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out-dir',type=Path,required=True)
    args = ap.parse_args()
    root = args.out_dir
    manifest = json.loads((root/'subscription.manifest.json').read_text())
    if manifest['state'] != 'complete':
        raise ValueError('Judging is not complete; no final report')
    raw, hashes = load_inputs([Path(p) for p in manifest['inputs']])
    if hashes != manifest['inputs']:
        raise ValueError('Original answer hashes changed')
    rows = [json.loads(x) for x in (root/'scored.jsonl').read_text().splitlines()]
    source = {(r['model'],r['key']):r for r in raw}
    if len(rows) != 360 or len({(r['model'],r['key']) for r in rows}) != 360:
        raise ValueError('Expected exactly 360 unique scored answers')
    for row in rows:
        original = source[(row['model'],row['key'])]
        for field in ('reply','item_text','finish_reason','completion_tokens','condition','level'):
            assert row[field] == original[field], f'Answer was modified: {field}'
        assert type(row['relevance']) is bool
        assert parse_relevance_json(row['judge_report']) == row['relevance']
        assert embedded.score_reply(row['reply'],row['level'],relevant=row['relevance']) == row['score']
        assert row['final_score'] == row['score']['combined']
        assert row['judge_model'] == 'gpt-6.1-sol' and row['judge_provider'] == 'openai-codex'
    assert manifest['scorer_sha256'] == sha(ROOT/'kaggle_task/cefr_scorer_embedded.py')
    assert manifest['protocol_sha256'] == sha(ROOT/'src/cefr_bench/relevance.py')
    assert manifest['preflight']['agreement'] == manifest['preflight']['total'] == 8
    # Independently verify every CLI invocation used subscription routing and no tools.
    db = Path.home()/'.hermes/state.db'
    connection = sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
    sessions = []
    for stderr in sorted((root/'requests').glob('*.stderr.txt')):
        lines = [line.strip().split(':',1)[1].strip() for line in stderr.read_text().splitlines()
                 if line.strip().startswith('session_id:')]
        assert len(lines) == 1, 'Missing subscription session identity'
        sid = lines[0]
        route = connection.execute('SELECT model,billing_provider FROM sessions WHERE id=?',(sid,)).fetchone()
        assert route == ('gpt-6.1-sol','openai-codex'), 'Judge route drift'
        calls = connection.execute("SELECT COUNT(*) FROM messages WHERE session_id=? AND (role='tool' OR (tool_calls IS NOT NULL AND tool_calls NOT IN ('[]','null')))",(sid,)).fetchone()[0]
        assert calls == 0, 'Judge used tools'
        sessions.append(sid)
    audit = json.loads((root/'agent_audit.json').read_text())
    lookup = {(r['model'],r['key']):r for r in rows}
    assert audit['reviewed'] == len(audit['cases']) == 12
    assert sum(case['review_relevance'] == lookup[(case['model'],case['key'])]['relevance']
               for case in audit['cases']) == audit['agreement'] == 12
    summary = write_summary(root/'summary.csv',rows)
    totals = []
    for model in sorted({r['model'] for r in rows}):
        group = [r for r in rows if r['model']==model]
        assert len(group)==180
        totals.append({'model':model,'n':180,'mean_score':round(statistics.mean(r['final_score'] for r in group),4),
                       'relevant':sum(r['relevance'] for r in group),
                       'relevant_adherent':sum(r['relevance'] and r['score']['adherent'] for r in group),
                       'truncated':sum(r['finish_reason']=='length' for r in group)})
    receipt = {'verified':True,'n':len(rows),'totals':totals,'summary':summary,
               'inputs':hashes,'scored_sha256':sha(root/'scored.jsonl'),
               'scorer_sha256':manifest['scorer_sha256'],'subscription_sessions_verified':sessions,
               'limitations':['30 questions; one generation per arm; no confidence intervals yet',
                    'C1 score is primarily a ceiling check, not proof of C1 proficiency',
                    'Relevance is not factual correctness',
                    'Batched subscription relevance protocol differs from singleton Kaggle judging',
                    'Informed prompts also change length instructions, not only vocabulary guidance',
                    'Agent audit is not a blinded human-labelled validation dataset']}
    (root/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    lines = ['# Local CEFR benchmark results','',
             'All 360 preserved answers re-scored with the generated Kaggle scorer after the quoted-sentence fix.',
             'Relevance: GPT-6.1-sol via ChatGPT/Codex subscription; 8/8 preflight checks; blinded six-answer batches.',
             'No metered API route; subscription quota is consumed.','',
             '| Model | Target | Bare score | Informed score | Bare relevant + adherent | Informed relevant + adherent |',
             '|---|---|---:|---:|---:|---:|']
    for model in sorted({r['model'] for r in rows}):
        for level in ('A1','B1','C1'):
            bare = next(s for s in summary if (s['model'],s['level'],s['condition'])==(model,level,'bare'))
            informed = next(s for s in summary if (s['model'],s['level'],s['condition'])==(model,level,'informed'))
            assert bare['n']==informed['n']==30 and bare['unscored']==informed['unscored']==0
            lines.append(f"| {model.split('/')[-1]} | {level} | {bare['mean_score']:.3f} | {informed['mean_score']:.3f} | {bare['relevant_adherent_count']}/30 | {informed['relevant_adherent_count']}/30 |")
    lines += ['', 'Scores range 0–1; irrelevance scores zero. Adherence is the vocab/grammar cap/floor flag, not overall teaching quality.',
              '', '## Overall', ''] + [f"- {t['model']}: mean {t['mean_score']:.3f}; {t['relevant']}/180 relevant; {t['relevant_adherent']}/180 relevant + adherent; {t['truncated']} replies hit the output cap." for t in totals]
    lines += ['', '## Limitations', ''] + ['- '+note for note in receipt['limitations']]
    lines += ['', 'Data: `scored.jsonl`; per-slice data: `summary.csv`; hashes and checks: `verification.json`.']
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'verified':True,'answers':360,'totals':totals,'summary':summary},indent=2))


if __name__=='__main__':
    main()
