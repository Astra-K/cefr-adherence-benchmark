"""Conservative parent-document holdout audit of the old ceiling calibration.
Reconstruct selection with both legacy and corrected sentence splitters; exclude
all parent texts used by either. No scorer thresholds or existing results edited.
"""
import collections
import hashlib
import json
from pathlib import Path
import random
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cefr_bench import calibrate as calibration
from cefr_bench.wordlists import get_lists
from cefr_bench.tokenise import split_sentences


def legacy_split(text):
    regex=re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z])|(?<=[.!?])\s*$|\n+")
    parts=[p.strip() for p in regex.split(text or '') if p and p.strip()]
    merged=[]
    for p in parts:
        if merged and not re.search(r'[.!?]$',merged[-1]) and not re.match(r'^[-*\d]+[.)]',p):
            merged[-1]+=' '+p
        else:
            merged.append(p)
    return merged


def norm(text):
    return ' '.join(text.split())


def main():
    source=calibration.load_texts()
    legacy=[]; corrected=[]
    seed=json.loads((ROOT/'results/calibration_v1.json').read_text())['seed']
    calibration.split_sentences=legacy_split
    legacy=calibration.make_windows(random.Random(seed),source,max_windows_per_level=400)
    calibration.split_sentences=split_sentences
    corrected=calibration.make_windows(random.Random(seed),source,max_windows_per_level=400)
    measured=calibration.measure_windows(legacy,get_lists())
    original=[json.loads(line) for line in (ROOT/'results/calibration_windows_v1.jsonl').read_text().splitlines()]
    fields=('level','source','license','n_content','n_unlisted','rate_one_above','rate_two_plus')
    reproduced=(len(measured)==len(original) and all(all(a[k]==b[k] for k in fields) for a,b in zip(measured,original)))
    all_windows=[(r['source'],norm(r['text'])) for r in legacy+corrected]
    files={}
    for name in calibration.FILES:
        path=ROOT/'data/raw/universalcefr'/name
        raw=json.loads(path.read_text())
        used=[]; remaining=[]
        for index,row in enumerate(raw):
            text=norm(row['text'])
            # Sentence-pool joins may cross documents; exclude short-pool parents
            # conservatively rather than pretend reconstructed chunks establish purity.
            short=(len(legacy_split(row['text']))<6 or len(split_sentences(row['text']))<6)
            matched=any(s==row['source_name'] and (window in text or text in window) for s,window in all_windows)
            if short or matched:
                used.append(index)
            else:
                remaining.append(index)
        files[name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'excluded_parent_indices':used,
                     'remaining_indices':remaining,'remaining_by_level':dict(collections.Counter(raw[i]['cefr_level'] for i in remaining)),
                     'participant_ids_available':False}
    audit={'legacy_selection_matches_saved_calibration_on_checked_fields':reproduced,
           'checked_fields':fields,'seed':seed,'legacy_windows':len(legacy),'corrected_windows':len(corrected),
           'files':files,'limitations':['Legacy selection is reconstructed, not an original input-ID receipt.',
           'Parent-text disjointness is not source-disjointness. Participant metadata is absent in converted corpus rows.',
           'Short sentence-pool parents excluded conservatively.']}
    out=ROOT/'results/c1_calibration_holdout_audit.json'
    out.write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps({'legacy_matches_saved':reproduced,'legacy_n':len(legacy),'corrected_n':len(corrected),
                      'remaining':{k:v['remaining_by_level'] for k,v in files.items()}},indent=2))


if __name__=='__main__':
    main()
