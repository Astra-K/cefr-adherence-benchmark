import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_cleaned_dataset_contract():
    items = json.loads((ROOT / 'data/items.json').read_text())
    assert len(items) == 30
    assert len({x['question_id'] for x in items}) == 30
    assert 299751 not in {x['question_id'] for x in items}
    for item in items:
        assert item['text'] == item['title'] + '\n\n' + item['body_text']
        assert item['author']['name']
        assert item['license'] in ('CC BY-SA 3.0', 'CC BY-SA 4.0')
        assert item['source_snapshot_sha256']
        assert item['category_validated'] is False
        assert 'img' not in item['source_media_types']


def test_preparation_is_deterministic_and_preserves_human_text():
    source = ROOT / 'data/raw/items_original_v1.json'
    if not source.exists():
        pytest.skip('requires intentionally excluded source snapshot')
    path = ROOT / 'scripts/prepare_items.py'
    spec = importlib.util.spec_from_file_location('prepare_items_test', path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    items, audit = mod.prepare(ROOT)
    items2, audit2 = mod.prepare(ROOT)
    assert items == items2
    assert audit == audit2
    assert items == json.loads((ROOT / 'data/items.json').read_text())
    assert len(audit['excluded']) == 4
    assert len(audit['replacements']) == 4


def test_embedded_items_match_frozen_dataset():
    import sys
    sys.path.insert(0, str(ROOT / 'kaggle_task'))
    import cefr_scorer_embedded as emb
    assert emb.ITEMS == json.loads((ROOT / 'data/items.json').read_text())
