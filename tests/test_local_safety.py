import importlib.util
import sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from local_safety import read_vm_stat,read_swap,preflight,SafetyError,WatchdogConfig,watchdog_run


def test_memory_uses_actual_page_size_and_preflight_refuses_pressure():
    text = 'Mach Virtual Memory Statistics: (page size of 4096 bytes)\nPages free: 10.\nPages inactive: 20.\n'
    assert read_vm_stat(text)['available_bytes'] == 30*4096
    snap = {'available_bytes':8*1024**3,'swap_used_fraction':0,'conflicts':[]}
    with pytest.raises(SafetyError): preflight(5,900,snapshot_data=snap)
    snap['available_bytes'] = 24*1024**3
    snap['conflicts'] = [{'pid':123,'reason':'other project'}]
    with pytest.raises(SafetyError): preflight(5,900,snapshot_data=snap)


def test_stale_watchdog_pid_is_never_killed(tmp_path):
    killed=[]
    cfg = WatchdogConfig(pid=999,start_token='expected-start',report_path=tmp_path/'report.json')
    report = watchdog_run(cfg,token_fn=lambda _: 'reused-pid',
                          kill_fn=lambda *a:killed.append(a),sleep_fn=lambda _:None)
    assert report['status']=='stale_fingerprint'
    assert killed==[]
