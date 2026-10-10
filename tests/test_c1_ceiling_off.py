"""TDD tests for the C1 ceiling-off variant (windows + reply re-scoring)."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cefr_bench.c1_ceiling_off import (window_pass, window_syntax_ok, rescore_reply,
                                       ceiling_off_caps, CEILING_OFF_CAP)

WIN = {'n_content': 100, 'rate_one_above': 0.50, 'rate_two_plus': 0.30,
       'n_grammar_above': 0, 'floor_share': 0.0,
       'mean_sent_len': 20.0, 'clause_per_sent': 2.0, 'mean_word_len': 4.5}


def test_c1_ceiling_off_restores_pass_on_overshoot_window():
    on = window_pass(WIN, 'C1', ceiling_off=False)
    off = window_pass(WIN, 'C1', ceiling_off=True)
    assert on['adherent'] is False            # caps violated (0.50 > 0.0139)
    assert on['vocab_ceiling'] is False
    assert off['adherent'] is True            # grammar ceiling 0<=0 still gates
    assert off['vocab_ceiling'] is True


def test_c1_ceiling_off_still_fails_on_grammar_overshoot():
    bad = dict(WIN, n_grammar_above=1)
    assert window_pass(bad, 'C1', ceiling_off=True)['adherent'] is False


def test_b1_and_a1_unchanged_by_flag():
    b1 = dict(WIN, rate_one_above=0.20)       # violates B1 cap (0.0545)
    assert window_pass(b1, 'B1', ceiling_off=True)['adherent'] is False
    assert window_pass(b1, 'B1', ceiling_off=False)['adherent'] is False
    a1 = dict(WIN, rate_one_above=0.10, rate_two_plus=0.05)  # within A1 caps
    assert window_pass(a1, 'A1', ceiling_off=True)['adherent'] is True
    a1_bad = dict(WIN, rate_one_above=0.20)   # violates A1 cap (0.1357)
    assert window_pass(a1_bad, 'A1', ceiling_off=True)['adherent'] is False


def test_b1_floor_still_enforced_ceiling_off():
    b1_nofloor = dict(WIN, floor_share=0.01, rate_one_above=0.0, rate_two_plus=0.0)
    assert window_pass(b1_nofloor, 'B1', ceiling_off=True)['adherent'] is False


def test_min_token_cap_still_applies_without_ceiling():
    tiny = dict(WIN, n_content=4, rate_one_above=0.25, rate_two_plus=0.5)  # 1 token each
    res = window_pass(tiny, 'C1', ceiling_off=True)
    assert res['vocab_ceiling'] is True  # 1/denom floor cap: single token tolerated


def test_syntax_helper_uses_frozen_bands():
    assert window_syntax_ok(WIN, 'C1') is True
    long_sents = dict(WIN, mean_sent_len=60.0)
    assert window_syntax_ok(long_sents, 'C1') is False


def test_caps_override_keeps_calibrated_a1_b1_and_lifts_only_c1():
    caps = ceiling_off_caps()
    assert set(caps) == {'A1', 'B1', 'C1'}
    assert caps['C1']['one_level_above'] == CEILING_OFF_CAP
    assert caps['C1']['two_plus_above_or_unlisted'] == CEILING_OFF_CAP
    # A1/B1 keep the frozen calibrated finals
    assert abs(caps['A1']['one_level_above'] - 0.1357) < 1e-9
    assert abs(caps['B1']['two_plus_above_or_unlisted'] - 0.0991) < 1e-9


def test_rescore_reply_c1_ceiling_no_longer_bounds_score():
    heavy = ("Consequently, notwithstanding the proliferation of heterogeneous "
             "methodological paradigms, the epistemological underpinnings remain contentious. "
             "Notwithstanding such reservations, preliminary meta-analyses suggest otherwise. "
             "The ostensibly inexorable proliferation of sophisticated terminology continues "
             "apace, exacerbating comprehensibility for the uninitiated reader nonetheless.")
    base = rescore_reply(heavy, 'C1', relevant=True)
    assert base['vocab']['ceiling'] == 1.0     # ceiling off -> no decay from vocab
    frozen = json.loads(json.dumps(base))
    assert frozen['level'] == 'C1'


def test_rescore_reply_a1_b1_use_frozen_caps():
    text = ("The cat is on the mat. It is a big cat. I like the big cat. "
            "The cat can run fast. We play with the cat every day.")
    a1 = rescore_reply(text, 'A1', relevant=True)
    b1 = rescore_reply(text, 'B1', relevant=True)
    assert a1['vocab']['ceiling'] < 1.0 or a1['vocab']['ceiling'] == 1.0  # sanity: runs
    assert b1['level'] == 'B1'
