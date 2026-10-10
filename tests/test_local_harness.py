import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

def load_runner():
    spec = importlib.util.spec_from_file_location('local_runner_test', ROOT/'scripts/local_harness.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_plan_full_cross_product():
    mod = load_runner()
    items = json.loads((ROOT/'data/items.json').read_text())
    plan = mod.make_plan(items)
    assert len(plan) == 180
    assert len({x['key'] for x in plan}) == 180
    assert {x['level'] for x in plan} == {'A1','B1','C1'}
    assert {x['condition'] for x in plan} == {'bare','informed'}
    assert all(x['item_text'] in x['prompt'] for x in plan)
    for row in plan:
        assert row['prompt_sha256'] == mod.sha256(row['prompt'].encode())

def test_resume_rejects_wrong_identity_duplicates_and_partial_line(tmp_path):
    mod = load_runner()
    path = tmp_path/'rows.jsonl'
    row = {'key':'e01:A1:bare','run_fingerprint':'a','reply':'Real saved answer.'}
    path.write_text(json.dumps(row)+'\n')
    assert mod.read_completed(path,'a') == {'e01:A1:bare'}
    with pytest.raises(ValueError): mod.read_completed(path,'b')
    path.write_text(json.dumps(row)+'\n'+json.dumps(row)+'\n')
    with pytest.raises(ValueError): mod.read_completed(path,'a')
    path.write_text(json.dumps(row)+'\n{"key":')
    with pytest.raises(ValueError): mod.read_completed(path,'a')

def test_non_thinking_and_prompt_limit_is_fail_closed():
    mod = load_runner()
    class Tokenizer:
        def apply_chat_template(self,messages,**kwargs):
            assert kwargs['enable_thinking'] is False
            assert kwargs['add_generation_prompt'] is True
            return [1,2,3]
    assert mod.render_prompt(Tokenizer(),'Question',3) == [1,2,3]
    with pytest.raises(ValueError): mod.render_prompt(Tokenizer(),'Question',2)

def test_no_c1_design_floor_in_primary_score():
    import sys
    sys.path.insert(0,str(ROOT/'src'))
    from cefr_bench.thresholds import FLOOR_MIN_TOKENS
    assert FLOOR_MIN_TOKENS['C1'] == 0
