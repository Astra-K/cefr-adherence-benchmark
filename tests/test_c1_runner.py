"""Production composition tests for the separate C1 descriptor runner."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[1]/'src')]
import eval_c1_descriptor as runner
from cefr_bench.c1_descriptor import DIMENSIONS


def result(r):
    return {'id':r['id'],'band':'B2','dimensions':{d:'B2' for d in DIMENSIONS},
            'evidence':[r['text']],'reason':'Observed clear but limited range.','confidence':90}


def test_transport_pinned_no_tools_and_removes_metered_credentials(monkeypatch,tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY','fake-metered-key')
    monkeypatch.setenv('HERMES_MODEL','wrong-route')
    monkeypatch.setattr(runner.shutil,'which',lambda _: '/fake/hermes')
    seen=[]
    group=[{'id':'x','text':'This is a test.','context':'','model':'hidden'}]
    def fake_run(argv,**kwargs):
        seen.append((argv,kwargs))
        return SimpleNamespace(returncode=0,stdout=json.dumps({'assessments':[result(group[0])]}),stderr='session_id: fake\n')
    monkeypatch.setattr(runner.subprocess,'run',fake_run)
    output=runner.call_batch(group,tmp_path/'request')
    assert output['x']['band']=='B2'
    argv,kwargs=seen[0]
    assert argv[argv.index('--provider')+1]=='openai-codex'
    assert argv[argv.index('--model')+1]=='gpt-6.1-sol'
    assert argv[argv.index('--toolsets')+1]=='none'
    assert '--safe-mode' in argv
    assert 'OPENAI_API_KEY' not in kwargs['env'] and 'HERMES_MODEL' not in kwargs['env']
    assert len(list(tmp_path.glob('*.request.json')))==1


def test_resume_uses_validated_reports_and_rejects_changed_text(monkeypatch,tmp_path):
    rows=[{'id':f'x{i}','text':f'Visible text {i}.','context':''} for i in range(7)]
    called=[]
    def batch(group,stem):
        called.append(stem.name)
        return {r['id']:{**result(r),'c1_status':'not_demonstrated'} for r in group}
    monkeypatch.setattr(runner,'call_batch',batch)
    out=runner.evaluate(rows,tmp_path,'phase',workers=2)
    assert len(out)==7 and len(called)==3
    assert len(runner.evaluate(rows,tmp_path,'phase'))==7 and len(called)==3
    modified=[dict(r) for r in rows]; modified[0]['text']='Changed.'
    with pytest.raises(ValueError,match='changed'): runner.evaluate(modified,tmp_path,'phase')


def test_malformed_batch_is_not_written(monkeypatch,tmp_path):
    def broken(group,stem): raise ValueError('Malformed output')
    monkeypatch.setattr(runner,'call_batch',broken)
    with pytest.raises(ValueError): runner.evaluate([{'id':'x','text':'Visible.'}],tmp_path,'phase',workers=1)
    assert (tmp_path/'phase.jsonl').read_text()==''


def test_process_failure_has_no_retry_or_fallback(monkeypatch,tmp_path):
    monkeypatch.setattr(runner.shutil,'which',lambda _: '/fake/hermes')
    calls=[]
    def failed(argv,**kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=1,stdout='',stderr='failure')
    monkeypatch.setattr(runner.subprocess,'run',failed)
    with pytest.raises(RuntimeError,match='no fallback'):
        runner.call_batch([{'id':'x','text':'Visible.'}],tmp_path/'request')
    assert len(calls)==1
