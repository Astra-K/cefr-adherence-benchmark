"""C1 ceiling-off variant: joint-pass logic for corpus windows and reply re-scoring.
The frozen embedded scorer and all existing results stay untouched.

Re-scoring uses the parameterized src scorer with a FULL caps map (all three
levels at their calibrated finals) in which only C1's vocab ceiling is lifted —
passing a partial map would silently drop A1/B1 back to uncalibrated start caps.
"""
import json
from pathlib import Path

from .thresholds import TOLERANCE_FINAL
from .scorer import score_reply

GRAMMAR_CEILING_COUNT = {'A1': 1, 'B1': 2, 'C1': 0}
FLOOR_MIN_SHARE = {'A1': None, 'B1': 0.0625, 'C1': None}
SYNTAX_BANDS = {
    'A1': {'mean_sent_len': (6.18, 16.17), 'clause_per_sent': (1.0, 2.26), 'mean_word_len': (3.35, 4.55)},
    'B1': {'mean_sent_len': (7.3, 25.4), 'clause_per_sent': (1.2, 3.25), 'mean_word_len': (3.64, 5.04)},
    'C1': {'mean_sent_len': (10.97, 35.25), 'clause_per_sent': (1.39, 4.26), 'mean_word_len': (3.98, 5.35)},
}
CEILING_OFF_CAP = 1e9  # effectively no vocab ceiling, keeps arithmetic finite


def _caps_for(target_level, ceiling_off):
    one, two = TOLERANCE_FINAL[target_level]['one_level_above'], TOLERANCE_FINAL[target_level]['two_plus_above_or_unlisted']
    if ceiling_off and target_level == 'C1':
        one, two = CEILING_OFF_CAP, CEILING_OFF_CAP
    return one, two


def window_pass(window, target_level, ceiling_off):
    """Joint adherent pass for a calibration window row at target level.

    Mirrors score_reply's adherent rule: vocab caps (+floor where calibrated),
    grammar ceiling (absolute), grammar floor (vacuous -> not enforced).
    Syntax never gates adherent; it is scored, not gated, in the frozen scorer.
    """
    if target_level not in TOLERANCE_FINAL:
        raise ValueError('unsupported target level')
    cap_one, cap_two = _caps_for(target_level, ceiling_off)
    denom = max(1, int(window['n_content']))
    cap_one = max(cap_one, 1.0/denom)
    cap_two = max(cap_two, 1.0/denom)
    v_ok = float(window['rate_one_above']) <= cap_one and float(window['rate_two_plus']) <= cap_two
    g_ok = int(window['n_grammar_above']) <= GRAMMAR_CEILING_COUNT[target_level]
    thr = FLOOR_MIN_SHARE[target_level]
    floor_met = True if thr is None else float(window['floor_share']) >= thr
    return {'vocab_ceiling': v_ok, 'grammar_ceiling': g_ok, 'floor': floor_met,
            'adherent': bool(v_ok and g_ok and floor_met)}


def window_syntax_ok(window, target_level):
    band = SYNTAX_BANDS[target_level]
    return all(band[m][0] <= float(window[m]) <= band[m][1] for m in band)


def ceiling_off_caps():
    """FULL caps override: calibrated finals for A1/B1, ceiling removed only for C1."""
    caps = {level: {'one_level_above': values['one_level_above'],
                    'two_plus_above_or_unlisted': values['two_plus_above_or_unlisted']}
            for level, values in TOLERANCE_FINAL.items()}
    caps['C1'] = {'one_level_above': CEILING_OFF_CAP, 'two_plus_above_or_unlisted': CEILING_OFF_CAP}
    return caps


def rescore_reply(reply, level, relevant):
    """Re-score with the src scorer; only C1's vocab ceiling is lifted."""
    return score_reply(reply, level, relevant=relevant, caps=ceiling_off_caps())


def load_scored(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]
