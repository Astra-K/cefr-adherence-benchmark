"""Parity contract: the generated Kaggle/embedded scorer must match the canonical
src scorer on every saved answer and on targeted divergence fixtures.

Locks in the E020 finding: verbatim-embedding the tokenizer alone did NOT keep
scorer semantics aligned (floor hard-zero vs partial credit, UK→US lookup,
proper-noun exclusion, de-doubled-consonant stems).
"""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'kaggle_task'))

import cefr_scorer_embedded as embedded
from cefr_bench.scorer import score_reply as src_score

SCORED = ROOT / 'results/qwen_local_subscription_v4/scored.jsonl'


def _both(text, level):
    e = embedded.score_reply(text, level, relevant=True)
    s = src_score(text, level, relevant=True)
    return e, s


def test_gate_fails_agree():
    text = "Only one sentence here."
    e, s = _both(text, 'A1')
    assert e['combined'] == 0.0 == s['combined']
    assert e['adherent'] is False and s['adherent'] is False


def test_b1_floor_miss_partial_credit_parity():
    # e19:B1:informed — src floor partial credit 0.7273; embedded used to hard-zero
    text = ("Black Friday is not called Black Friday. Black Friday is a special "
            "shopping day in the USA and Canada. The word \"black\" does not mean "
            "darkness. It comes from the color black. On this day, people buy many "
            "new things. Many shops open early. Everyone is happy on this day. "
            "They sell cheap things too. So, it is a happy day. We do not have to "
            "worry about dark days.")
    e, s = _both(text, 'B1')
    assert s['vocab']['floor'] == 0.7273, s['vocab']['floor']
    assert e['combined'] == s['combined'], (e['combined'], s['combined'])


def test_uk_spelling_lookup_parity():
    text = ("She always colours her drawings with care. The behaviour of the "
            "class was good today. They organised a small party for their "
            "teacher. Everyone realised it was a nice surprise. The centre of "
            "the room was full. It was a grey and quiet evening. She likes to "
            "analyse her mistakes and practise reading every day.")
    for level in ('A1', 'B1', 'C1'):
        e, s = _both(text, level)
        assert e['combined'] == s['combined'], (level, e['combined'], s['combined'])
        assert e['vocab']['rate_two_plus'] == s['vocab']['rate_two_plus'], level


def test_proper_noun_exclusion_parity():
    # mid-sentence capitalized unlisted words are excluded in src; embedded used
    # to count them as two_plus violations
    text = ("Yesterday Maria and Francesco visited the museum with their friend "
            "Katarzyna. They saw many old paintings and learned about the history "
            "of the city. Maria liked the small statues the most because they "
            "looked very old. Francesco took many photos of the big hall to show "
            "his family at home.")
    for level in ('A1', 'B1', 'C1'):
        e, s = _both(text, level)
        assert e['combined'] == s['combined'], (level, e['combined'], s['combined'])
        assert e['vocab']['rate_two_plus'] == s['vocab']['rate_two_plus'], (
            level, e['vocab']['rate_two_plus'], s['vocab']['rate_two_plus'])


def test_dedoubled_consonant_stem_parity():
    # "running" -> run (stem[:-1] on doubled consonant); embedded lacked this
    text = ("He was running in the park when he saw a big dog. The dog was "
            "swimming in the small lake near the trees. A woman was sitting on "
            "a bench and reading a book quietly. He stopped running and walked "
            "home slowly in the rain.")
    e, s = _both(text, 'A1')
    assert e['combined'] == s['combined'], (e['combined'], s['combined'])


def test_all_360_saved_answers_parity():
    if not SCORED.exists():
        pytest.skip('requires intentionally excluded full local-model replies')
    rows = [json.loads(l) for l in SCORED.read_text().splitlines()]
    assert len(rows) == 360
    mismatches = []
    for r in rows:
        e = embedded.score_reply(r['reply'], r['level'], relevant=(r['relevance'] is True))
        s = src_score(r['reply'], r['level'], relevant=(r['relevance'] is True))
        if e['combined'] != s['combined']:
            mismatches.append((r['key'], e['combined'], s['combined']))
    assert not mismatches, mismatches[:10]


def test_c1_ceiling_restored_in_embedded_thresholds():
    # C1 vocab ceiling must remain in primary scoring (E020: keep the ceiling)
    TH = embedded.THRESHOLDS
    assert TH['tolerance_final']['C1']['one_level_above'] == 0.0139
    assert TH['tolerance_final']['C1']['two_plus_above_or_unlisted'] == 0.1351
    assert TH['floor_min_tokens']['C1'] == 0  # diagnostic-only, not primary scoring
