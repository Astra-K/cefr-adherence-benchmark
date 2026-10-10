"""Prompt construction: bare and informed conditions.

The informed prompt embeds the cumulative allowed word list, the grammar list,
and the passing rules in plain words, using final calibration values (never
code). Token counts are logged per prompt.
"""

from .config import CONFIG, LEVELS, TOLERANCE_FINAL, FLOOR_MIN_SHARE, FLOOR_MIN_TOKENS

_BARE = "Reply to this learner at CEFR level {level}.\n\nLearner message: {item}"

_RULES_TEMPLATE = """You are replying to an English learner. Write your reply at CEFR level {level}.

PASSING RULES (plain words):
- Up to {cap_one_pct}% of your words may come from the {one_above} list.
- Up to {cap_two_pct}% of your words may come from lists above {one_above} or be words not in any list below.
{floor_rules}- Write 3 to 5 sentences.
- Reply to the learner only. No explanations about levels or lists.

ALLOWED WORD LIST for level {level} (cumulative, includes all lower levels):
{word_list}

ALLOWED GRAMMAR for level {level} (cumulative):
{grammar_list}

Learner message: {item}"""


def word_list_text(level: str, wl) -> str:
    """Comma-separated cumulative list of clean single-word headwords."""
    from .config import LEVEL_ORDER
    ord_ = LEVEL_ORDER[level]
    def ok(hw):
        return (hw.isalpha() and hw.isascii() and len(hw) > 1) or hw in ("a", "i")
    headwords = sorted({hw for hw, lv in wl.headword_items()
                        if LEVEL_ORDER[lv] <= ord_ and ok(hw)})
    return ", ".join(headwords)


def grammar_list_text(level: str) -> str:
    from .config import LEVEL_ORDER
    from .grammar import DETECTORS
    ord_ = LEVEL_ORDER[level]
    names = []
    seen = set()
    for name, lv, cid, pat, src in DETECTORS:
        if LEVEL_ORDER[lv] <= ord_ and name not in seen:
            seen.add(name)
            names.append(f"{name} (CEFR-J {cid})")
    return "; ".join(names)


def bare_prompt(item: str, level: str) -> str:
    return _BARE.format(level=level, item=item)


def informed_prompt(item: str, level: str, wl, tolerance_final=None,
                    floor_cfg=None, grammar_floors=None) -> str:
    tf = tolerance_final or TOLERANCE_FINAL
    lv_caps = tf.get(level)
    cap_one, cap_two = (
        (lv_caps["one_level_above"], lv_caps["two_plus_above_or_unlisted"])
        if isinstance(lv_caps, dict) else (
            CONFIG["tolerance_start"]["one_level_above"],
            CONFIG["tolerance_start"]["two_plus_above_or_unlisted"],
        )
    )
    cap_one_pct = round(cap_one * 100)
    cap_two_pct = round(cap_two * 100)
    idx = LEVELS.index(level)
    one_above = LEVELS[idx + 1] if idx + 1 < len(LEVELS) else "C2+"
    # plain-words floor rules from calibrated values
    share_floor = FLOOR_MIN_SHARE.get(level)
    min_tok = FLOOR_MIN_TOKENS.get(level, 0)
    band = {"B1": "A2 and B1", "C1": "B2 and C1"}.get(level)
    lines = []
    if share_floor:
        lines.append(f"- At least {round(share_floor * 100)}% of your words should come from the {band} lists (the level floor).\n")
    if min_tok:
        lines.append(f"- Use at least {min_tok} word{'s' if min_tok > 1 else ''} from the {band} lists (the level floor).\n")
    floor_rules = "".join(lines)
    return _RULES_TEMPLATE.format(
        level=level, cap_one_pct=cap_one_pct, cap_two_pct=cap_two_pct,
        one_above=one_above, floor_rules=floor_rules,
        word_list=word_list_text(level, wl),
        grammar_list=grammar_list_text(level),
        item=item,
    )


def est_tokens(text: str) -> int:
    """Deterministic token-count estimate: chars/4 (logged as estimate)."""
    return max(1, round(len(text) / 4))
