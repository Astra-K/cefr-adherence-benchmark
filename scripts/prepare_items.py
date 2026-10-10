"""Reproducible presentation/attribution cleanup of the original human questions.

No learner text is authored here. Original title and HTML body are joined;
image-dependent or API-license-unreported inputs are deterministically replaced
from the explicitly recorded human-source candidate snapshots.
"""
import hashlib
import html
import json
from pathlib import Path
import random
import re


def clean_body(text):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', text or ''))).strip()


def prepare(root):
    root = Path(root)
    original = json.loads((root / 'data/raw/items_original_v1.json').read_text())
    files = [root / 'data/raw/ell_selected_withbody.json',
             root / 'data/raw/ell_replacements_withbody.json',
             root / 'data/raw/ell_replacement_time_withbody.json']
    sources, hashes = {}, {}
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[str(path.relative_to(root))] = digest
        for entry in json.loads(path.read_text())['items']:
            sources[entry['question_id']] = (entry, str(path.relative_to(root)), digest)
    selected_ids = {x['question_id'] for x in original}
    replacements = sorted(set(sources) - selected_ids)
    random.Random(42).shuffle(replacements)
    audit = {'policy': 'title plus full normalized body; seed 42 replacement ordering',
             'source_hashes': hashes, 'excluded': [], 'replacements': [],
             'category_note': 'Everyday/trap are historical keyword-selection buckets, not validated domains or CEFR labels.'}
    items = []
    for item in original:
        source, path, digest = sources[item['question_id']]
        reason = ('image-dependent' if '<img' in source.get('body', '').lower()
                  else 'API content_license missing' if not source.get('content_license') else None)
        replaced = None
        if reason:
            audit['excluded'].append({'id': item['id'], 'question_id': item['question_id'], 'reason':reason})
            replaced = item['question_id']
            replacement = replacements.pop(0)
            source, path, digest = sources[replacement]
            audit['replacements'].append({'id':item['id'], 'old_question_id':replaced, 'question_id':replacement})
        assert source.get('content_license') in ('CC BY-SA 3.0','CC BY-SA 4.0')
        assert '<img' not in source['body'].lower()
        title, body = html.unescape(source['title']), clean_body(source['body'])
        owner = source.get('owner', {})
        items.append({
            'id':item['id'], 'kind':item['kind'], 'category_validated':False,
            'text':title+'\n\n'+body, 'title':title, 'body_text':body,
            'source':'ell.stackexchange.com', 'question_id':source['question_id'],
            'link':source['link'], 'score':source.get('score'),
            'license':source['content_license'],
            'license_url':'https://creativecommons.org/licenses/by-sa/'+('3.0' if source['content_license'].endswith('3.0') else '4.0')+'/',
            'author':{'name':html.unescape(owner.get('display_name','deleted user')), 'url':owner.get('link')},
            'source_snapshot':path, 'source_snapshot_sha256':digest,
            'source_media_types':[], 'replaces_question_id':replaced,
            'transformations':['HTML tags removed; entities decoded; whitespace normalized', 'Original title prepended to original body; learner errors unchanged'],
        })
    assert len(items) == 30 and len({x['question_id'] for x in items}) == 30
    return items, audit


def main():
    root = Path(__file__).resolve().parents[1]
    items, audit = prepare(root)
    out = root / 'data/items.json'
    out.write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n')
    audit['dataset_sha256'] = hashlib.sha256(out.read_bytes()).hexdigest()
    (root/'data/items_preparation_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps({'items':len(items),'replacements':audit['replacements'],'sha256':audit['dataset_sha256']},indent=2))

if __name__ == '__main__':
    main()
