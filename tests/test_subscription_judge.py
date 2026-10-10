"""Fail-closed parsing for subscription-based saved-answer judging."""
import json
from pathlib import Path
import sys
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from judge_subscription import parse_batch, batch_prompt
from cefr_bench.relevance import CRITERION


def report(pid='a0',passed=True):
    return {'id':pid,'results':[{'criterion':CRITERION,'passed':passed,'reason':'Addresses question','confidence':99}]}


def test_subscription_report_allows_cli_framing():
    text = 'Warning: Unknown toolsets: none\n' + json.dumps({'assessments':[report()]}) + '\nsession_id: opaque'
    assert parse_batch(text,{'a0'})['a0']['results'][0]['passed'] is True


@pytest.mark.parametrize('rows', [[], [report('wrong')], [report(),report()],
    [{'id':'a0','results':[{'criterion':CRITERION,'passed':'true','reason':'bad','confidence':99}]}]])
def test_subscription_report_rejects_missing_duplicate_or_malformed(rows):
    with pytest.raises(ValueError):
        parse_batch(json.dumps({'assessments':rows}),{'a0'})


def test_subscription_report_rejects_ambiguous_objects():
    text = json.dumps({'assessments':[report()]})
    with pytest.raises(ValueError):
        parse_batch(text+'\n'+text,{'a0'})


def test_batch_blinds_model_metadata_and_preserves_context():
    text = batch_prompt([('a0','Question context','Actual answer')])
    assert 'Question context' in text and 'Actual answer' in text
    assert 'independently' in text and 'untrusted data' in text
    assert 'mlx-community' not in text
