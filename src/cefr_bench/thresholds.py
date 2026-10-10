"""FINAL calibrated thresholds — written from results/calibration_v1.json
(calibration v1, 2026-10-07, scorer v0.1.0, seed 13, ~900 windows).

These are the values used in the informed-condition prompts (plain-text rules)
and by default in score_reply(). Regenerate via scripts/run_calibration.py.
"""

TOLERANCE_FINAL = {
    "A1": {"one_level_above": 0.1357, "two_plus_above_or_unlisted": 0.1416},
    "B1": {"one_level_above": 0.0545, "two_plus_above_or_unlisted": 0.0991},
    "C1": {"one_level_above": 0.0139, "two_plus_above_or_unlisted": 0.1351},
}

# vocab floor: min share of content lemmas in target's top two bands
FLOOR_MIN_SHARE = {
    "A1": None,   # no floor at A1 by design
    "B1": 0.0625,
    "C1": None,   # share-floor vacuous (p10=0.0, E005) — see FLOOR_MIN_TOKENS
}

# C1 calibration p10 was zero. A one-token minimum is an uncalibrated
# design choice and belongs in diagnostics, not primary pass/fail or prompts.
FLOOR_MIN_TOKENS = {"A1": 0, "B1": 0, "C1": 0}

# grammar floor share thresholds — vacuous at p10=0 for all levels (E006)
GRAMMAR_FLOOR = {"A1": None, "B1": None, "C1": None}

# grammar CEILING: absolute count of above-target-level hits allowed per reply
# (p90 of n_grammar_above across genuine windows: A1=1, B1=2, C1=0)
GRAMMAR_CEILING_COUNT = {"A1": 1, "B1": 2, "C1": 0}

SYNTAX_BANDS = {
    "A1": {"mean_sent_len": [6.18, 16.17], "clause_per_sent": [1.0, 2.26],
           "mean_word_len": [3.35, 4.55]},
    "B1": {"mean_sent_len": [7.3, 25.4], "clause_per_sent": [1.2, 3.25],
           "mean_word_len": [3.64, 5.04]},
    "C1": {"mean_sent_len": [10.97, 35.25], "clause_per_sent": [1.39, 4.26],
           "mean_word_len": [3.98, 5.35]},
}
