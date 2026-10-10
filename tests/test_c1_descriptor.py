"""Fail-closed descriptor diagnostic: evidence, blinding and status semantics."""
import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cefr_bench.c1_descriptor import build_prompt, parse_reports, DIMENSIONS, validation_metrics

TEXT = 'Although the plan is workable, its benefits depend on sustained cooperation. That distinction matters.'


def report(band='C1'):
    return {'id':'x','band':band,'dimensions':{d:band for d in DIMENSIONS},
            'evidence':['Although the plan is workable, its benefits depend on sustained cooperation.'],
            'reason':'A qualified argument with controlled subordination.',
            'confidence':90}


def test_prompt_blinds_labels_and_preserves_literal_input():
    prompt = build_prompt([{'id':'x','text':TEXT,'context':'Explain this plan.',
                           'model':'MODEL_SECRET','level':'LABEL_SECRET'}])
    assert 'MODEL_SECRET' not in prompt and 'LABEL_SECRET' not in prompt
    data = json.loads(prompt.split('\nDATA_JSON=')[1])
    assert data == [{'id':'x','text':TEXT,'context':'Explain this plan.'}]
    assert 'insufficient_evidence' in prompt
    assert 'Do not reward length' in prompt


def test_valid_report_has_separate_c1_status():
    result = parse_reports(json.dumps({'assessments':[report()]}),{'x':TEXT})
    assert result['x']['c1_status']=='demonstrated'
    assert 'final_score' not in result['x']


@pytest.mark.parametrize('band,status',[('below_B2','not_demonstrated'),('B2','not_demonstrated'),
                                       ('C2','demonstrated'),('insufficient_evidence','insufficient_evidence')])
def test_band_semantics(band,status):
    r=report(band)
    assert parse_reports(json.dumps({'assessments':[r]}),{'x':TEXT})['x']['c1_status']==status


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(band='C3'),
    lambda r:r.update(confidence=True),
    lambda r:r.update(confidence=101),
    lambda r:r.update(evidence=['fabricated quotation']),
    lambda r:r.update(evidence=[]),
    lambda r:r.update(dimensions={}),
    lambda r:r.update(reason=''),
    lambda r:r.update(id='other'),
    lambda r:r.update(dimensions={**r['dimensions'],'grammar_range':'C3'}),
])
def test_invalid_or_ungrounded_report_rejected(mutation):
    r=report(); mutation(r)
    with pytest.raises(ValueError): parse_reports(json.dumps({'assessments':[r]}),{'x':TEXT})


def test_duplicates_omissions_and_ambiguous_objects_rejected():
    for text in (json.dumps({'assessments':[report(),report()]}),json.dumps({'assessments':[]}),
                 json.dumps({'assessments':[report()]})+'\n'+json.dumps({'assessments':[report()]})):
        with pytest.raises(ValueError): parse_reports(text,{'x':TEXT})


def test_abstention_is_not_dropped_from_validation_denominator():
    pairs=[{'gold':'B2','band':'C1'},{'gold':'B2','band':'B2'},
           {'gold':'C1','band':'C1'},{'gold':'C1','band':'insufficient_evidence'}]
    metrics=validation_metrics(pairs)
    assert metrics['specificity']==0.5
    assert metrics['sensitivity']==0.5
    assert metrics['abstention_rate']==0.25
    assert not metrics['pilot_gate_passed']


def test_missing_positive_or_negative_controls_never_pass_gate():
    assert not validation_metrics([{'gold':'C1','band':'C1'}])['pilot_gate_passed']
