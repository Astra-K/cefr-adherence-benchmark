"""Calibration: sample 3-5 sentence windows from CEFR-labelled texts, measure
the full distribution of every scorer quantity, set thresholds at the rule-
given percentiles (caps = p90 of violation rate, floors = p10 of share,
syntax bands = p5-p95), bootstrap CIs, joint-pass adjustment, separation check.

Levels: '+' variants collapse to base (A1+ -> A1; logged DEVLOG).
Sentence-level pools (cefr-sp) are joined into consecutive groups to form
windows — statistics are sentence-local so coherence does not matter.
"""

import json
import os
import random
import statistics

from .config import LEVEL_ORDER
from .scorer import analyse, SCORER_VERSION
from .grammar import scan_grammar
from .syntax import syntax_measures
from .tokenise import split_sentences

UC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                      "data", "raw", "universalcefr")

FILES = ["cambridge_exams.json", "cefr-sp.json", "icle500.json",
         "elg-cefr-en.json", "cefr_asag.json"]


def _base_level(lv):
    lv = (lv or "").strip().upper()
    if not lv or lv == "NA":
        return None
    lv = lv.split("+")[0]
    return lv if lv in LEVEL_ORDER else None


def load_texts():
    """Yield dicts {level, source, license, text}."""
    out = []
    for f in FILES:
        path = os.path.join(UC_DIR, f)
        if not os.path.exists(path):
            continue
        for r in json.load(open(path)):
            lv = _base_level(r.get("cefr_level"))
            if lv and r.get("text") and len(r["text"].strip()) > 20:
                out.append({
                    "level": lv, "source": r.get("source_name", f),
                    "license": r.get("license", "?"), "text": r["text"],
                })
    return out


def make_windows(rng, texts, sent_lo=3, sent_hi=5, max_windows_per_level=400):
    """Non-overlapping windows from documents; consecutive groups from pools."""
    by_level = {}
    for t in texts:
        by_level.setdefault(t["level"], []).append(t)
    windows = []
    for lv, items in by_level.items():
        rng.shuffle(items)
        made = 0
        # document-level first (richer), then sentence pools
        docs = [t for t in items if len(split_sentences(t["text"])) >= 6]
        pools = [t for t in items if len(split_sentences(t["text"])) < 6]
        for t in docs:
            if made >= max_windows_per_level:
                break
            sents = split_sentences(t["text"])
            n = rng.randint(sent_lo, sent_hi)
            if len(sents) <= n:
                cand = [t["text"]]
                starts = [0]
            else:
                starts = sorted(rng.sample(range(len(sents) - n + 1),
                                           min(3, len(sents) - n + 1)))
                cand = [" ".join(sents[s:s + n]) for s in starts]
            for s, txt in zip(starts, cand):
                if made >= max_windows_per_level:
                    break
                windows.append({"level": lv, "source": t["source"],
                                "license": t["license"], "text": txt})
                made += 1
        # sentence pools: join consecutive items in file order (already shuffled)
        flat = []
        for t in pools:
            flat.append(t["text"].strip())
        i = 0
        while i + sent_lo <= len(flat) and made < max_windows_per_level:
            n = rng.randint(sent_lo, min(sent_hi, len(flat) - i))
            windows.append({"level": lv, "source": pools[i].get("source", "?"),
                            "license": pools[i].get("license", "?"),
                            "text": " ".join(flat[i:i + n])})
            made += 1
            i += n
    return windows


def measure_windows(windows, wl):
    """Run ENGINE + SYNTAX per window; return enriched records (text kept for
    cross-level re-analysis in the separation check)."""
    from .scorer import grammar_scores
    out = []
    for w in windows:
        a = analyse(w["text"], w["level"], wl)
        sm = syntax_measures(w["text"])
        hits = scan_grammar(w["text"], a["sentences"])
        above, within_top2 = grammar_scores(hits, w["level"])
        n_sents = max(1, len(a["sentences"]))
        g_floor_share = len({h["sentence"] for h in within_top2}) / n_sents
        out.append({
            **w,
            "n_content": a["n_content"],
            "n_unlisted": a["n_unlisted"],
            "rate_one_above": a["rate_one_above"],
            "rate_two_plus": a["rate_two_plus"],
            "floor_share": a["floor_share"],
            "mean_sent_len": sm["mean_sent_len"],
            "clause_per_sent": sm["clause_per_sent"],
            "mean_word_len": sm["mean_word_len"],
            "n_grammar_hits": len(hits),
            "n_grammar_above": len(above),
            "g_floor_share": g_floor_share,
        })
    return out


def pct(xs, p):
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def stats(xs):
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": round(statistics.mean(xs), 4),
            "sd": round(statistics.pstdev(xs), 4) if len(xs) > 1 else 0.0,
            "p10": round(pct(xs, 10), 4), "p50": round(pct(xs, 50), 4),
            "p90": round(pct(xs, 90), 4)}


def bootstrap_ci(xs, stat_fn, n_boot=1000, seed=7, alpha=5):
    """Percentile bootstrap CI for stat_fn(xs)."""
    rng = random.Random(seed)
    vals = []
    xs = list(xs)
    for _ in range(n_boot):
        sample = [xs[rng.randrange(len(xs))] for _ in range(len(xs))]
        v = stat_fn(sample)
        if v is not None:
            vals.append(v)
    if not vals:
        return (None, None)
    vals.sort()
    return (round(vals[int(len(vals) * alpha / 200)], 4),
            round(vals[int(len(vals) * (1 - alpha / 200))], 4))


def calibrate(wl, seed=13, max_windows=400):
    rng = random.Random(seed)
    texts = load_texts()
    windows = make_windows(rng, texts, max_windows_per_level=max_windows)
    recs = measure_windows(windows, wl)
    by_level = {}
    for r in recs:
        by_level.setdefault(r["level"], []).append(r)

    result = {"scorer_version": SCORER_VERSION, "seed": seed,
              "thresholds": {}, "stats": {}, "notes": []}

    for lv in ["A1", "B1", "C1"]:
        rs = by_level.get(lv, [])
        if len(rs) < 30:
            result["notes"].append(f"{lv}: only {len(rs)} windows — small")
        # keep only assessable windows (>= 20 content tokens)
        ok = [r for r in rs if r["n_content"] >= 20] or rs

        cap_one = pct([r["rate_one_above"] for r in ok], 90)
        cap_two = pct([r["rate_two_plus"] for r in ok], 90)
        floor_share_p10 = pct([r["floor_share"] for r in ok], 10)
        gfloor_p10 = pct([r["g_floor_share"] for r in ok], 10)

        result["thresholds"][lv] = {
            "cap_one_above": round(cap_one, 4),
            "cap_two_plus": round(cap_two, 4),
            "floor_min_share": None if lv == "A1" else round(floor_share_p10, 4),
            "grammar_floor": None if lv == "A1" else round(gfloor_p10, 4),
            "syntax_bands": {
                "mean_sent_len": [round(pct([r["mean_sent_len"] for r in ok], 5), 2),
                                   round(pct([r["mean_sent_len"] for r in ok], 95), 2)],
                "clause_per_sent": [round(pct([r["clause_per_sent"] for r in ok], 5), 2),
                                     round(pct([r["clause_per_sent"] for r in ok], 95), 2)],
                "mean_word_len": [round(pct([r["mean_word_len"] for r in ok], 5), 2),
                                   round(pct([r["mean_word_len"] for r in ok], 95), 2)],
            },
        }
        result["stats"][lv] = {
            "n_windows": len(rs), "n_assessable": len(ok),
            "rate_one_above": stats([r["rate_one_above"] for r in ok]),
            "rate_two_plus": stats([r["rate_two_plus"] for r in ok]),
            "floor_share": stats([r["floor_share"] for r in ok]),
            "g_floor_share": stats([r["g_floor_share"] for r in ok]),
            "mean_sent_len": stats([r["mean_sent_len"] for r in ok]),
            "clause_per_sent": stats([r["clause_per_sent"] for r in ok]),
            "mean_word_len": stats([r["mean_word_len"] for r in ok]),
            "unlisted_share_of_content": stats(
                [r["n_unlisted"] / max(1, r["n_content"]) for r in ok]),
        }
        # bootstrap CIs for the two caps
        result["thresholds"][lv]["cap_one_ci"] = bootstrap_ci(
            [r["rate_one_above"] for r in ok], lambda s: pct(s, 90))
        result["thresholds"][lv]["cap_two_ci"] = bootstrap_ci(
            [r["rate_two_plus"] for r in ok], lambda s: pct(s, 90))

    # ---- joint pass check + loosening to 90% ----
    joint = {}
    for lv in ["A1", "B1", "C1"]:
        th = result["thresholds"][lv]
        rs = [r for r in by_level.get(lv, []) if r["n_content"] >= 20]

        def ceil_pass(recs):
            ok = [r for r in recs if r["rate_one_above"] <= th["cap_one_above"]
                  and r["rate_two_plus"] <= th["cap_two_plus"]]
            return len(ok) / max(1, len(recs))

        cp = ceil_pass(rs)
        # brief: if joint ceiling pass < 90%, loosen until it reaches 90%
        loosen_factor = 1.0
        while cp < 0.90 and loosen_factor < 10.0:
            th["cap_one_above"] = round(th["cap_one_above"] * 1.05, 4)
            th["cap_two_plus"] = round(th["cap_two_plus"] * 1.05, 4)
            loosen_factor *= 1.05
            cp = ceil_pass(rs)
        if lv == "A1":
            floor_ok = rs  # no floor
        else:
            floor_ok = [r for r in rs
                        if r["floor_share"] >= (th["floor_min_share"] or 0)
                        and r["g_floor_share"] >= (th["grammar_floor"] or 0)]
        joint[lv] = {
            "ceil_pass": round(cp, 4),
            "floor_pass": round(len(floor_ok) / max(1, len(rs)), 4),
            "loosen_factor": round(loosen_factor, 3),
        }
    result["joint_pass"] = joint

    # ---- separation check: adjacent-level floors, measured at the FLOOR's
    # target level (re-analyse lower-level texts at the higher target) ----
    def fail_rate(test_lv, floor_lv):
        th = result["thresholds"][floor_lv]
        if th["floor_min_share"] in (None, 0.0):
            return None  # vacuous floor cannot separate
        rs = [r for r in by_level.get(test_lv, []) if r["n_content"] >= 20]
        if not rs:
            return None
        failed = 0
        for r in rs:
            a = analyse(r["text"], floor_lv, wl)
            if a["floor_share"] < th["floor_min_share"]:
                failed += 1
        return round(failed / len(rs), 4)

    result["separation"] = {
        "A1_failing_B1_floor": fail_rate("A1", "B1"),
        "B1_failing_C1_floor": fail_rate("B1", "C1"),
    }
    return result, recs
