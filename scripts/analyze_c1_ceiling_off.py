"""C1 ceiling-off investigation: corpus windows + frozen LLM replies.
Writes results/c1_ceiling_off_v1/; never modifies frozen scores or corpora.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cefr_bench.c1_ceiling_off import (window_pass, window_syntax_ok, rescore_reply,
                                       load_scored)

WINDOWS = ROOT/'results/calibration_windows_v1.jsonl'
SCORED = ROOT/'results/qwen_local_subscription_v4/scored.jsonl'
# window level -> assessed difficulty relative to the C1 target
BELOW = ('A1', 'A2', 'B1', 'B2')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def corpus_analysis(windows):
    out = []
    by_level = collections.defaultdict(list)
    for w in windows:
        by_level[w['level']].append(w)
    for src_level in ('A1', 'A2', 'B1', 'B2', 'C1', 'C2'):
        group = by_level.get(src_level, [])
        for mode in (False, True):
            verdicts = [window_pass(w, 'C1', ceiling_off=mode) for w in group]
            n = len(group)
            out.append({
                'source_level': src_level, 'n': n, 'ceiling_off': mode,
                'adherent_pass': sum(v['adherent'] for v in verdicts),
                'pass_rate': round(sum(v['adherent'] for v in verdicts)/n, 4) if n else None,
                'vocab_ceiling_pass': sum(v['vocab_ceiling'] for v in verdicts),
                'grammar_ceiling_pass': sum(v['grammar_ceiling'] for v in verdicts),
                'grammar_fail_reason': sum(not v['grammar_ceiling'] for v in verdicts),
                'syntax_band_ok': sum(window_syntax_ok(w, 'C1') for w in group),
            })
    return out


def reply_rescore(scored):
    rows = []
    for r in scored:
        level = r['level']
        new = rescore_reply(r['reply'], level, relevant=(r['relevance'] is True))
        old = r['score']
        old_vocab = old.get('vocab') or {}
        rows.append({
            'model': r['model'], 'key': r['key'], 'level': level,
            'condition': r['condition'], 'relevance': r['relevance'],
            'old_combined': old['combined'], 'new_combined': new['combined'],
            'old_adherent': old['adherent'], 'new_adherent': new['adherent'],
            'old_vocab_ceiling': old_vocab.get('ceiling', old_vocab.get('dim')),
            'new_vocab_ceiling': (new.get('vocab') or {}).get('ceiling'),
            'old_flags': old['flags'], 'new_flags': new['flags'],
            'grammar_above': (new.get('grammar') or {}).get('n_above'),
            'finish_reason': r['finish_reason'],
            'reply': r['reply'],
        })
    return rows


def summarise_replies(rows):
    out = []
    for model in sorted({r['model'] for r in rows}):
        for level in ('A1', 'B1', 'C1'):
            for cond in ('bare', 'informed'):
                g = [r for r in rows if (r['model'], r['level'], r['condition']) == (model, level, cond)]
                if not g:
                    continue
                rel = [r for r in g if r['relevance'] is True]
                out.append({
                    'model': model, 'level': level, 'condition': cond, 'n': len(g),
                    'mean_old': round(statistics.mean(r['old_combined'] for r in g), 4),
                    'mean_new': round(statistics.mean(r['new_combined'] for r in g), 4),
                    'adherent_old': sum(r['old_adherent'] for r in g),
                    'adherent_new': sum(r['new_adherent'] for r in g),
                    'rel_adherent_old': sum(r['old_adherent'] and r['relevance'] for r in g),
                    'rel_adherent_new': sum(r['new_adherent'] and r['relevance'] for r in g),
                    'vocab_ceiling_changed': sum(r['old_vocab_ceiling'] != r['new_vocab_ceiling'] for r in g),
                    'score_changed': sum(abs(r['old_combined']-r['new_combined']) > 1e-9 for r in g),
                })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out-dir', type=Path, default=ROOT/'results/c1_ceiling_off_v1')
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    windows = [json.loads(l) for l in WINDOWS.read_text().splitlines()]
    corpus = corpus_analysis(windows)
    with (args.out_dir/'corpus_windows_c1.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(corpus[0]))
        w.writeheader(); w.writerows(corpus)

    scored = load_scored(SCORED)
    if len(scored) != 360:
        raise ValueError(f'expected 360 scored replies, got {len(scored)}')
    rows = reply_rescore(scored)
    with (args.out_dir/'rescored_replies.jsonl').open('w') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False)+'\n')
    summary = summarise_replies(rows)
    with (args.out_dir/'reply_summary.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0]))
        w.writeheader(); w.writerows(summary)

    manifest = {
        'windows_sha256': sha(WINDOWS), 'scored_sha256': sha(SCORED),
        'n_windows': len(windows), 'n_replies': len(rows),
        'note': 'C1 vocab ceiling removed (grammar ceiling, floors, syntax unchanged); '
                'frozen v4 results untouched; relevance labels reused as-is.',
    }
    (args.out_dir/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))
    print('\nCORPUS (C1 target):')
    for c in corpus:
        print(f"  {c['source_level']:>3} n={c['n']:<4} off={int(c['ceiling_off'])} "
              f"pass={c['adherent_pass']}/{c['n']} rate={c['pass_rate']}")
    print('\nREPLIES (cells):')
    for s in summary:
        print(f"  {s['model']} {s['level']} {s['condition']:<8} mean {s['mean_old']}->{s['mean_new']} "
              f"adherent {s['adherent_old']}->{s['adherent_new']} changed {s['score_changed']}")


if __name__ == '__main__':
    main()
