"""CEFR-adherence scorer configuration.

Starting reference values only; final per-level caps/floors/bands come from
calibration (see DEVLOG). None means "not yet calibrated" -> the scorer uses a
neutral value and flags it, so pre-calibration tests never depend on invented
numbers.
"""

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
TARGET_LEVELS = ["A1", "B1", "C1"]

from .thresholds import (  # noqa: E402  (final calibrated values)
    TOLERANCE_FINAL, FLOOR_MIN_SHARE, FLOOR_MIN_TOKENS, GRAMMAR_FLOOR,
    GRAMMAR_CEILING_COUNT, SYNTAX_BANDS,
)

CONFIG = {
    "levels": ["A1", "B1", "C1"],
    # Starting reference values only; final per-level caps come from calibration
    "tolerance_start": {
        "one_level_above": 0.05,
        "two_plus_above_or_unlisted": 0.01,
    },
    # per level: {"one_level_above": float, "two_plus_above_or_unlisted": float}
    # filled by calibration; None -> use tolerance_start
    "tolerance_final": None,
    "threshold_percentile": 10,  # worst 10% of genuine texts fall outside every threshold
    "exclude": ["proper_nouns", "numbers"],
    # Floor: share of content lemmas in the target's top two bands.
    # threshold None -> uncalibrated -> floor factor 1.0 with a flag.
    "floor": {
        "B1": {"band": ["A2", "B1"], "min_share": None},
        "C1": {"band": ["B2", "C1"], "min_share": None},
        # grammar floor: share of sentences with >=1 grammar hit in the band
        "grammar_band": {"B1": ["A2", "B1"], "C1": ["B2", "C1"]},
        "grammar_min_share": {"B1": None, "C1": None},
        "min_content_tokens": 20,
    },
    # Syntax bands per target level: {measure: [p5, p95]} filled by calibration.
    "syntax_bands": None,  # e.g. {"A1": {"sent_len": [3, 12], ...}}
    "weights": {"vocab": 0.4, "grammar": 0.4, "syntax": 0.2},
    "reply_sentences": [3, 5],
    "min_sentences": 2,  # gate: at least 2 sentences
    # ceiling score shape: 1 while ratio<=1, then linear to 0 at ratio 3
    "ceiling_decay": 2.0,
}

LEVEL_ORDER = {lv: i for i, lv in enumerate(LEVELS)}


def level_distance(a: str, b: str) -> int:
    """Signed distance level(a) - level(b). Positive means a is above b."""
    return LEVEL_ORDER[a] - LEVEL_ORDER[b]
