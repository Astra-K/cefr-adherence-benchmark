"""Independent coverage, evidence, input-preservation and route checks for C1 pilot.
Verifies diagnostic execution, NOT construct validity or expert agreement.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cefr_bench.c1_descriptor import parse_reports, validation_metrics


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args(); out=args.out_dir
    manifest=json.loads((out/'manifest.json').read_text())
    if manifest['state'] not in ('complete','blocked_validation','validation_passed'):
        raise ValueError('Diagnostic is still running or interrupted')
    for path,digest in manifest['inputs'].items():
        if sha(path)!=digest:
            raise ValueError('Input/code hash drift: '+path)
    control_path=next(Path(p) for p in manifest['inputs'] if Path(p).name.startswith('c1_descriptor_controls'))
    controls=json.loads(control_path.read_text())
    expected={r['id']:r for r in controls['cases']}
    validation=load_jsonl(out/'validation.jsonl')
    if len(validation)!=len(expected) or {r['id'] for r in validation}!=set(expected):
        raise ValueError('Validation coverage or uniqueness failure')
    corpus=json.loads((ROOT/controls['provenance']['corpus_path']).read_text())
    if sha(ROOT/controls['provenance']['corpus_path'])!=controls['provenance']['corpus_sha256']:
        raise ValueError('Corpus bytes changed')
    for r in validation:
        if r['input']!=expected[r['id']]:
            raise ValueError('Validation input changed')
        if r['input']['kind']=='labelled_corpus':
            original=corpus[r['input']['source_index']]
            if (original['text'],original['cefr_level'],original['title'])!=(r['input']['text'],r['input']['gold'],r['input']['source_title']):
                raise ValueError('Invented/transformed corpus text or label')
        report=parse_reports(json.dumps({'assessments':[r['report']]}),{r['id']:r['input']['text']})[r['id']]
        if report!=r['report']:
            raise ValueError('Invalid saved descriptor verdict')
    metrics=validation_metrics([{'gold':r['input']['gold'],'band':r['report']['band']} for r in validation if r['input']['kind']=='labelled_corpus'])
    stored=json.loads((out/'validation_metrics.json').read_text())
    for key,value in metrics.items():
        if stored[key]!=value:
            raise ValueError('Validation metrics drift: '+key)
    negatives=[r for r in validation if r['input']['kind']=='authored_negative_control']
    fp=sum(r['report']['c1_status']=='demonstrated' for r in negatives)
    if stored['authored_negative_false_positive']!=fp or stored['combined_pilot_gate_passed']!=(metrics['pilot_gate_passed'] and bool(negatives) and fp==0):
        raise ValueError('Pilot gate drift')
    with (out/'validation_confusion.csv').open('w',newline='') as handle:
        writer=csv.writer(handle); writer.writerow(['gold','predicted','count'])
        writer.writerows((gold,band,count) for gold,counts in metrics['confusion_by_gold_level'].items() for band,count in counts.items())
    db=sqlite3.connect('file:'+str(Path.home()/'.hermes/state.db')+'?mode=ro',uri=True)
    sessions=[]
    for path in (out/'requests').glob('*.stderr.txt'):
        ids=re.findall(r'^session_id:\s*(\S+)',path.read_text(),re.M)
        if len(ids)!=1:
            raise ValueError('Missing session identity')
        sid=ids[0]
        if db.execute('SELECT model,billing_provider FROM sessions WHERE id=?',(sid,)).fetchone()!=('gpt-6.1-sol','openai-codex'):
            raise ValueError('Unexpected provider/model route')
        count=db.execute("SELECT COUNT(*) FROM messages WHERE session_id=? AND (role='tool' OR (tool_calls IS NOT NULL AND tool_calls NOT IN ('[]','null')))",(sid,)).fetchone()[0]
        if count:
            raise ValueError('Unexpected tool calls')
        sessions.append(sid)
    db.close()
    assessed=[]
    if manifest['state']=='complete':
        scored_path=next(Path(p) for p in manifest['inputs'] if Path(p).name=='scored.jsonl')
        original=load_jsonl(scored_path)
        source={(r['model'],r['key']):r for r in original}
        assessed=load_jsonl(out/'saved_answers.jsonl')
        keys={(r['input']['model'],r['input']['key']) for r in assessed}
        if len(assessed)!=360 or len(keys)!=360 or keys!=set(source):
            raise ValueError('Saved-answer coverage failure')
        for row in assessed:
            raw=source[(row['input']['model'],row['input']['key'])]
            for target,original_key in (('text','reply'),('context','item_text'),('level','level'),('condition','condition'),('relevance','relevance'),('finish_reason','finish_reason')):
                if row['input'][target]!=raw[original_key]:
                    raise ValueError('Frozen reply changed: '+target)
            parsed=parse_reports(json.dumps({'assessments':[row['report']]}),{row['id']:row['input']['text']})[row['id']]
            if parsed!=row['report']:
                raise ValueError('Saved evidence/verdict mismatch')
        with (out/'summary.csv').open() as handle:
            summaries=list(csv.DictReader(handle))
        if len(summaries)!=12:
            raise ValueError('Expected 12 model/target/arm cells')
        for cell in summaries:
            sub=[r for r in assessed if (r['input']['model'],r['input']['level'],r['input']['condition'])==(cell['model'],cell['requested_level'],cell['condition'])]
            if len(sub)!=30 or int(cell['n'])!=30:
                raise ValueError('Wrong cell coverage')
            for band in ('below_B2','B2','C1','C2','insufficient_evidence'):
                if int(cell[band])!=sum(r['report']['band']==band for r in sub):
                    raise ValueError('Summary count drift')
    else:
        if (out/'saved_answers.jsonl').exists() and (out/'saved_answers.jsonl').stat().st_size:
            raise ValueError('Sweep started without passing validation')
        notes=controls['provenance']['limitations']
        text=['# C1 evaluator validation — saved-answer sweep blocked','',
              'The frozen original benchmark results are unchanged.','',
              '## Labelled control outcomes','',
              '| Source label | Below B2 | B2 | C1 | C2 | Insufficient evidence |',
              '|---|---:|---:|---:|---:|---:|']
        for gold,counts in metrics['confusion_by_gold_level'].items():
            text.append('| '+gold+' | '+' | '.join(str(counts[b]) for b in ('below_B2','B2','C1','C2','insufficient_evidence'))+' |')
        text+=['',f"A1 authored negative-control C1 false positives: {fp}/{len(negatives)}.",
               '',f"Sensitivity: {metrics['sensitivity']}; specificity: {metrics['specificity']}; abstention: {metrics['abstention_rate']}.",
               'Pilot gate passed: '+str(stored['combined_pilot_gate_passed'])+'.',
               '', 'The rubric was not tuned after observing these outcomes. Passing authored negative controls alone is insufficient.',
               '', '## Limitations']+['- '+note for note in notes]
        (out/'REPORT.md').write_text('\n'.join(text)+'\n')
    receipt={'execution_verified':True,'construct_validity_certified':False,'state':manifest['state'],
             'validation_n':len(validation),'saved_answers_n':len(assessed),'original_scores_preserved':True,
             'source_label_and_text_checks':True,'exact_quote_checks':True,'subscription_sessions_verified':sessions,
             'inputs':manifest['inputs'],'validation_metrics':stored,
             'full_validation_ready':controls['provenance']['full_validation_ready']}
    (out/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'execution_verified':True,'state':manifest['state'],'validation_n':len(validation),
                      'saved_answers_n':len(assessed),'metrics':stored,'full_validation_ready':False},indent=2))


if __name__=='__main__':
    main()
