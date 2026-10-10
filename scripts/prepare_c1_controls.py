"""Freeze a provisional ICLE500 labelled pilot plus existing A1 negative controls.
No new learner questions, synthetic positives, model generation or score edits.
"""
import hashlib
import json
from pathlib import Path
import random
ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    corpus=ROOT/'data/raw/universalcefr/icle500.json'
    rows=json.loads(corpus.read_text())
    audit_path=ROOT/'results/c1_calibration_holdout_audit.json'
    audit=json.loads(audit_path.read_text())
    entry=audit['files']['icle500.json']
    if sha(corpus)!=entry['sha256']:
        raise ValueError('Corpus changed after overlap audit')
    cases=[]
    counts={}
    for level in ('B2','C1','C2'):
        # No sample tuning based on either old score or new judge outcome.
        pool=[i for i in entry['remaining_indices'] if rows[i]['cefr_level']==level
              and 80<=len(rows[i]['text'].split())<=800]
        random.Random(42).shuffle(pool)
        if len(pool)<12:
            raise ValueError('Not enough eligible ICLE pilot records at '+level)
        selected=pool[:12]
        for index in selected:
            row=rows[index]
            if row['license']!='CC0 1.0 (Public Domain)' or row['category']!='learner':
                raise ValueError('Unexpected license or category')
            cases.append({'id':'v'+str(len(cases)).zfill(3),'text':row['text'],'context':'',
                          'gold':level,'kind':'labelled_corpus','source':'icle500',
                          'source_index':index,'source_title':row['title'],'license':row['license'],
                          'text_sha256':hashlib.sha256(row['text'].encode()).hexdigest(),
                          'selection':'seed42; exact level; reconstructed unused parent; whole text 80..800 words'})
        counts[level]=len(selected)
    golden=ROOT/'data/golden.json'
    negatives=[g for g in json.loads(golden.read_text()) if g['level']=='A1' and g['expect_adherent']]
    for i,g in enumerate(negatives):
        cases.append({'id':f'n{i}','text':g['text'],'context':'','gold':'A1',
                      'kind':'authored_negative_control','source':'existing_golden_fixture_not_independent_expert_label'})
    if len({r['text'] for r in cases})!=len(cases):
        raise ValueError('Duplicate pilot text')
    provenance={'corpus_path':str(corpus.relative_to(ROOT)),'corpus_sha256':sha(corpus),
                'overlap_audit_sha256':sha(audit_path),'negative_controls_sha256':sha(golden),
                'n_by_level':counts,'source':'UniversalCEFR ICLE500 conversion',
                'source_documentation':'https://universalcefr.github.io/',
                'primary_study':'https://doi.org/10.1093/applin/amae048',
                'annotator_evidence':'UniversalCEFR directory reports manual CEFR labels, 28 expert annotators, Rasch kappa -0.02.',
                'license':'CC0 1.0 (Public Domain) according to every converted record and UniversalCEFR directory',
                'holdout_status':'provisional_reconstructed_document_holdout_not_proven_source_or_participant_independence',
                'full_validation_ready':False,
                'limitations':['ICLE500 source was also used in old ceiling calibration; this is NOT source-disjoint validation.',
                'Legacy calibration selection could not be reproduced on saved lexical measurements. Excluded parents are reconstructed; original parent-ID/hash receipts are absent.',
                'Participant IDs are absent from converted records; participant independence is unverified.',
                'Directory reports very low annotator agreement (Rasch kappa -0.02); labels are noisy, not unquestionable gold.',
                'Whole learner essays differ from short tutor replies; expert whole-text labels do not transfer automatically to fragments.',
                'The diagnostic rubric was not trained/tuned on these controls; judge pretraining contamination is unknown.',
                'Twelve texts per exact B2/C1/C2 band are a small nonrepresentative pilot; no label or result-based sample cherry-picking.']}
    path=ROOT/'data/c1_descriptor_controls_v1.json'
    if path.exists():
        raise ValueError('Frozen controls already exist; preserve and audit rather than overwrite')
    path.write_text(json.dumps({'provenance':provenance,'cases':cases},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'path':str(path),'n':len(cases),'levels':counts,'full_validation_ready':False},indent=2))


if __name__=='__main__':
    main()
