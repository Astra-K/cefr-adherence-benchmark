"""Deterministic CEFR-adherence scorer.

Pipeline: clean -> GATE -> ENGINE (vocab+grammar, level-tagged) -> SYNTAX
-> sub-scores -> combined float + adherent flag. Pure stdlib; spaCy optional.
"""

import re
from collections import Counter

from .config import CONFIG, LEVEL_ORDER, GRAMMAR_CEILING_COUNT, FLOOR_MIN_TOKENS
from .thresholds import TOLERANCE_FINAL, FLOOR_MIN_SHARE, GRAMMAR_FLOOR, SYNTAX_BANDS
from .grammar import scan_grammar
from .syntax import syntax_measures, syntax_scores
from .tokenise import split_sentences, token_positions, tokens, is_number
from .wordlists import get_lists

SCORER_VERSION = "0.1.0"

META_TALK_RE = re.compile(
    r"\b(?:as an ai|language model|i'?m sorry|cefr level|great question|"
    r"let me know if|feel free to|delve|furthermore|moreover|in conclusion|"
    r"i cannot|i can'?t assist|my apologies)\b", re.I)

MARKDOWN_RE = re.compile(r"(\*\*|__|\*|`|#+\s|>\s|\[.*?\]\(.*?\))")

PROPER_NOUN_HINTS = re.compile(r"^[A-Z]")


def clean(text: str):
    """Strip markdown; flag meta-talk. Returns (clean_text, flags)."""
    t = MARKDOWN_RE.sub("", text or "")
    flags = []
    if META_TALK_RE.search(t):
        flags.append("meta_talk")
    return t.strip(), flags


def _is_pronoun_initial(text: str, offset: int):
    """Heuristic: capitalized mid-sentence ASCII word (not after .!?)."""
    prefix = text[max(0, offset - 2):offset]
    return not re.search(r"[.!?]\s*$|\n\s*$|^\s*$", prefix)


def gate(text: str):
    """Non-empty, >=2 sentences, mostly-English, no disqualifying meta-talk.
    Relevance is judged OUTSIDE (LLM judge) and passed in as `relevant`.
    """
    flags = []
    if not text or not text.strip():
        return False, ["empty"]
    sents = split_sentences(text)
    if len(sents) < CONFIG["min_sentences"]:
        flags.append("too_few_sentences")
    toks = tokens(text)
    alpha = [t for t in toks if t.isalpha()]
    if not alpha:
        return False, flags + ["no_alpha_tokens"]
    ascii_share = sum(1 for t in alpha if t.isascii()) / len(alpha)
    if ascii_share < 0.9:
        flags.append("not_english")
    # sentence-count gate is hard: <2 sentences is a gate fail
    if len(sents) < CONFIG["min_sentences"]:
        return False, flags
    return True, flags


def analyse(text: str, target_level: str, wl=None):
    """ENGINE: token-level level tags + grammar hits. Returns rich dict."""
    wl = wl or get_lists()
    sents = split_sentences(text)
    token_info = []
    for tok, off in token_positions(text):
        if is_number(tok):
            token_info.append({"tok": tok, "off": off, "kind": "number"})
            continue
        lv = wl.level_of(tok)
        if lv is not None:
            kind = "listed"
        elif tok[:1].isupper() and _is_pronoun_initial(text, off):
            kind = "proper_noun_candidate"
        else:
            kind = "unlisted"
        token_info.append({"tok": tok, "off": off, "kind": kind, "level": lv})

    content = [t for t in token_info
               if t["kind"] in ("listed", "unlisted")]
    content = [t for t in content if len(t["tok"]) > 1]  # drop clitic 's' etc.

    listed_content = [t for t in content if t["kind"] == "listed"]
    unlisted_content = [t for t in content if t["kind"] == "unlisted"]

    t_ord = LEVEL_ORDER[target_level]

    def distance(lv):
        return LEVEL_ORDER[lv] - t_ord

    band_share = Counter()
    band_tokens = []
    for t in listed_content:
        d = distance(t["level"])
        band_share[d] += 1
        band_tokens.append({**t, "dist": d})
    for t in unlisted_content:
        band_share["unlisted"] += 1
        band_tokens.append({**t, "dist": 2})

    denom = len(listed_content) + len(unlisted_content)
    # ceilings: relative to target level
    one_above = [t for t in band_tokens if t["dist"] == 1]
    two_plus = [t for t in band_tokens if t["dist"] >= 2]  # incl. unlisted
    rate_one = len(one_above) / denom if denom else 0.0
    rate_two = len(two_plus) / denom if denom else 0.0

    # floor: share of content lemmas in target's top two bands = target and
    # the level directly BELOW it (A2+B1 for B1; B2+C1 for C1) per the brief
    top2 = [t for t in band_tokens if -1 <= t["dist"] <= 0]
    floor_share = len(top2) / denom if denom else 0.0

    # proper-noun-candidates excluded from violation numerator lists already
    return {
        "n_content": denom,
        "n_listed": len(listed_content),
        "n_unlisted": len(unlisted_content),
        "rate_one_above": rate_one,
        "rate_two_plus": rate_two,
        "floor_share": floor_share,
        "one_above_tokens": [t["tok"] for t in one_above],
        "two_plus_tokens": [t["tok"] for t in two_plus],
        "token_levels": band_tokens,
        "sentences": sents,
    }


def ceiling_score(rate_one: float, rate_two: float, caps):
    """caps = (cap_one, cap_two). Score 1 while ratio<=1, then linear to 0 at 3x."""
    cap_one, cap_two = caps
    r1 = rate_one / cap_one if cap_one > 0 else (0.0 if rate_one == 0 else 99.0)
    r2 = rate_two / cap_two if cap_two > 0 else (0.0 if rate_two == 0 else 99.0)
    ratio = max(r1, r2)
    score = 1.0 if ratio <= 1.0 else max(0.0, 1.0 - (ratio - 1.0) / CONFIG["ceiling_decay"])
    adherent = (rate_one <= cap_one) and (rate_two <= cap_two)
    return score, ratio, adherent


def floor_factor(share: float, threshold):
    if threshold is None:
        return 1.0, "floor_uncalibrated"
    return min(1.0, share / threshold), None


def grammar_scores(hits, target_level):
    """Grammar ceiling = hits strictly above target band grammar; floor =
    share of sentences with >=1 hit within target's top two bands."""
    t_ord = LEVEL_ORDER[target_level]
    above = [h for h in hits if LEVEL_ORDER[h["level"]] > t_ord]
    within_top2 = [h for h in hits if t_ord - 1 <= LEVEL_ORDER[h["level"]] <= t_ord]
    n_sents = max(1, len({h["sentence"] for h in hits}) or 1)
    # sentences with at least one within-band hit / total sentences
    return above, within_top2


def score_reply(text: str, target_level: str, relevant=True, cfg=None,
                wl=None, caps=None, floors=None, syntax_bands=None,
                grammar_floors=None):
    """Full pipeline. Returns dict with combined float + sub-scores + flags.
    caps: {level: (cap_one, cap_two)}; floors: {level: float};
    syntax_bands: {level: {measure: [lo,hi]}}; grammar_floors: {level: float}.
    All default to CONFIG / None->uncalibrated-neutral.
    """
    cfg = cfg or CONFIG
    t_ord = LEVEL_ORDER[target_level]

    cleaned, clean_flags = clean(text)
    passed, gate_flags = gate(cleaned)
    flags = clean_flags + gate_flags
    if not passed:
        return {
            "version": SCORER_VERSION, "level": target_level,
            "combined": 0.0, "adherent": False, "gate_passed": False,
            "flags": flags + (["irrelevant"] if not relevant else []),
            "n_sentences": 0,
        }

    a = analyse(cleaned, target_level, wl)
    if a["n_content"] < cfg["floor"]["min_content_tokens"]:
        flags.append("too_short_to_assess")

    # ---- vocab ceiling/floor ----
    caps_map = caps or cfg.get("tolerance_final") or TOLERANCE_FINAL
    lv_final = caps_map.get(target_level) if isinstance(caps_map, dict) else None
    level_caps = (
        (lv_final["one_level_above"], lv_final["two_plus_above_or_unlisted"])
        if isinstance(lv_final, dict) else (
            cfg["tolerance_start"]["one_level_above"],
            cfg["tolerance_start"]["two_plus_above_or_unlisted"],
        )
    )
    denom = max(1, a["n_content"])
    # brief §Calibration: minimum cap of ONE token (a p90 below one token is
    # sub-token granularity and would flag a single word)
    level_caps = (max(level_caps[0], 1.0 / denom), max(level_caps[1], 1.0 / denom))
    v_ceiling, v_ratio, v_ok = ceiling_score(a["rate_one_above"], a["rate_two_plus"], level_caps)

    v_floor_thr = FLOOR_MIN_SHARE.get(target_level)
    if floors is not None:
        v_floor_thr = floors.get(target_level, v_floor_thr)
    n_top2_tokens = sum(1 for t in a["token_levels"] if -1 <= t["dist"] <= 0)
    v_floor_min_tok = FLOOR_MIN_TOKENS.get(target_level, 0)
    if target_level == "A1":
        v_floor, v_floor_note, v_floor_met = 1.0, None, True  # no floor at A1
    elif v_floor_thr is None and v_floor_min_tok:
        # share-floor vacuous; minimum-token floor applies (C1: >=1 B2/C1 token)
        v_floor_met = n_top2_tokens >= v_floor_min_tok
        v_floor = 1.0 if v_floor_met else 0.0
        v_floor_note = None
    elif v_floor_thr is None:
        v_floor, v_floor_note, v_floor_met = 1.0, None, True
    else:
        v_floor, v_floor_note = floor_factor(a["floor_share"], v_floor_thr)
        v_floor_met = a["floor_share"] >= v_floor_thr
        if v_floor_note:
            flags.append(v_floor_note)
        if v_floor_min_tok and n_top2_tokens < v_floor_min_tok:
            v_floor = 0.0
            v_floor_met = False

    vocab_dim = v_ceiling * v_floor

    # ---- grammar ----
    hits = scan_grammar(cleaned, a["sentences"])
    above, within_top2 = grammar_scores(hits, target_level)
    # grammar ceiling: ABSOLUTE count of above-level hits (calibrated p90)
    g_max = GRAMMAR_CEILING_COUNT.get(target_level, 2)
    g_rate = len(above)
    if g_rate <= g_max:
        g_ceiling, g_ratio, g_ok = 1.0, 0.0, True
    else:
        over = g_rate - g_max
        g_ceiling = max(0.0, 1.0 - over / 2.0)  # -0.5 per extra hit
        g_ceiling, g_ratio, g_ok = g_ceiling, over, False
    # grammar floor: share of sentences with a within-top-2-band hit
    n_sents = max(1, len(a["sentences"]))
    g_floor_share = len({h["sentence"] for h in within_top2}) / n_sents
    gf_thr = (grammar_floors or {}).get(target_level) or GRAMMAR_FLOOR.get(target_level)
    if target_level == "A1":
        g_floor, g_floor_note = 1.0, None  # no floor at A1 by design
    else:
        if gf_thr is None:
            g_floor, g_floor_note = 1.0, None  # floor vacuous per calibration (E006)
        else:
            g_floor, g_floor_note = floor_factor(g_floor_share, gf_thr)
            if g_floor_note:
                flags.append(g_floor_note)
    grammar_dim = g_ceiling * g_floor

    # ---- syntax ----
    sm = syntax_measures(cleaned)
    sb = (syntax_bands or {}).get(target_level) or SYNTAX_BANDS.get(target_level)
    syn_score, syn_detail, syn_flag = syntax_scores(sm, sb)
    if syn_flag:
        flags.append(syn_flag)
    syntax_dim = syn_score

    w = cfg["weights"]
    combined = (w["vocab"] * vocab_dim + w["grammar"] * grammar_dim
                + w["syntax"] * syntax_dim)
    if not relevant:
        combined = 0.0
        flags.append("irrelevant")

    adherent = bool(v_ok and g_ok and v_floor_met)
    weakest = min(vocab_dim, grammar_dim, syntax_dim)

    return {
        "version": SCORER_VERSION,
        "level": target_level,
        "combined": round(combined, 4),
        "weakest_link": round(weakest, 4),
        "adherent": adherent,
        "gate_passed": True,
        "flags": flags,
        "n_sentences": len(a["sentences"]),
        "vocab": {"ceiling": round(v_ceiling, 4), "floor": round(v_floor, 4),
                  "dim": round(vocab_dim, 4), "ratio": None if v_ratio is None else round(v_ratio, 3),
                  "rate_one_above": round(a["rate_one_above"], 4),
                  "rate_two_plus": round(a["rate_two_plus"], 4),
                  "floor_share": round(a["floor_share"], 4),
                  "one_above_tokens": a["one_above_tokens"][:20],
                  "two_plus_tokens": a["two_plus_tokens"][:20]},
        "grammar": {"ceiling": round(g_ceiling, 4), "floor": round(g_floor, 4),
                    "dim": round(grammar_dim, 4),
                    "n_hits": len(hits), "n_above": len(above),
                    "above_names": sorted({h["name"] for h in above})[:10],
                    "floor_share": round(g_floor_share, 4)},
        "syntax": {"dim": round(syntax_dim, 4), **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in syn_detail.items()}},
        "measures": {k: (round(v, 3) if isinstance(v, float) else v)
                     for k, v in sm.items() if not isinstance(v, list)},
        "clean_len": len(cleaned),
    }
