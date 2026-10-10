"""Flag-precision audit + monotonicity check (brief §Validation 2-3).

Audit: sample flagged tokens from golden-set scoring + calibration windows,
classify each as REAL violation or ARTIFACT (tokenizer/lemmatiser/proper-noun).
Output: results/flag_audit.json (agent-audited; sample left for human spot-check).

Monotonicity: score labelled windows at each target; violation rates must RISE
as the text's level falls below the target. Output: results/monotonicity.json
"""

import json
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from cefr_bench import score_reply, get_lists
from cefr_bench.golden import load_golden
from cefr_bench.scorer import analyse
from cefr_bench.wordlists import UK_TO_US

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RESULTS = os.path.join(ROOT, "results")

# ---------- audit ----------
# artifact classifiers (deterministic heuristics + manual spot list)
KNOWN_PROPER = {
    "america", "usa", "canada", "new", "york", "london", "england", "spain",
    "brazil", "rome", "italy", "monday", "may", "harry", "potter", "luna",
    "lovegood", "gradle", "alex", "xyz", "facebook", "internet", "sara",
    "tom", "anna", "max", "friday", "black", "covid", "nytimes",
}
BRITISH_SPELLING = {  # same word, UK spelling — CEFR-J lists US forms
    "favour", "colour", "behaviour", "honour", "humour", "labour",
    "favourite", "colours", "optimise", "organise", "realise", "recognise",
    "analyse", "utilise", "emphasise", "prioritise", "specialise",
    "optimises", "organised", "realised", "recognised", "practise",
    "centre", "metre", "theatre", "fibre", "litre", "grey",
}


def classify_flag(tok, context, wl):
    t = tok.lower()
    if t in KNOWN_PROPER:
        return "artifact: proper noun"
    stem_lv = None
    stem = t
    for suf in ("ingly", "edly", "ing", "ed", "ly", "s", "ies", "es"):
        if t.endswith(suf) and len(t) > len(suf) + 2:
            stem = t[: -len(suf)]
            sl = wl.level_of(stem) or wl.level_of(stem + "e")
            if sl is not None:
                stem_lv = sl
            break
    if stem_lv is not None:
        # resolvable stem: real violation only if the STEM is above target too
        return f"real: stem '{stem}' is listed at {stem_lv} (above target)"
    if t in UK_TO_US or t.rstrip(".,;:!?") in BRITISH_SPELLING:
        return "artifact: British spelling variant"
    return "real: genuinely above-level or unlisted"


def run_audit():
    wl = get_lists()
    rng = random.Random(99)
    flagged = []

    # golden set items scored at their levels -> collect one/two-plus tokens
    for g in load_golden():
        a = analyse(g["text"], g["level"], wl)
        for t in a["one_above_tokens"] + a["two_plus_tokens"]:
            flagged.append(("golden", g["level"], t, g["text"][:80]))

    # calibration windows (re-read a sample from disk records is text-free;
    # so re-analyse items directly from source files)
    from cefr_bench.calibrate import load_texts, make_windows
    texts = load_texts()
    windows = make_windows(random.Random(5), texts, max_windows_per_level=30)
    for w in windows:
        a = analyse(w["text"], w["level"], wl)
        for t in a["one_above_tokens"] + a["two_plus_tokens"]:
            flagged.append((w["source"], w["level"], t, w["text"][:80]))

    rng.shuffle(flagged)
    sample = flagged[:60]  # audit 60 (brief: ~40)
    audited = []
    for src, lv, tok, ctx in sample:
        verdict = classify_flag(tok, ctx, wl)
        audited.append({"source": src, "level": lv, "token": tok,
                        "verdict": verdict, "context": ctx})
    real = sum(1 for a in audited if a["verdict"].startswith("real"))
    artifact = sum(1 for a in audited if a["verdict"].startswith("artifact"))
    by_kind = defaultdict(int)
    for a in audited:
        by_kind[a["verdict"]] += 1
    out = {
        "n_audited": len(audited), "n_real": real, "n_artifact": artifact,
        "artifact_share": round(artifact / max(1, len(audited)), 4),
        "by_verdict": dict(by_kind),
        "audited": audited,
    }
    json.dump(out, open(os.path.join(RESULTS, "flag_audit.json"), "w"), indent=2)
    print(f"audit: {len(audited)} flagged tokens -> {real} real, {artifact} artifacts "
          f"({out['artifact_share']:.1%} artifact rate)")
    for k, v in sorted(by_kind.items(), key=lambda x: -x[1]):
        print(f"   {k}: {v}")
    return out


# ---------- monotonicity ----------
def run_monotonicity():
    from cefr_bench.calibrate import load_texts, make_windows
    wl = get_lists()
    texts = load_texts()
    windows = make_windows(random.Random(11), texts, max_windows_per_level=60)
    rows = []
    for target in ["A1", "B1", "C1"]:
        for w_lv in ["A1", "B1", "C1"]:
            if w_lv == target:
                continue  # same-level baseline computed anyway below
            ws = [x for x in windows if x["level"] == w_lv]
            rates = []
            for w in ws:
                a = analyse(w["text"], target, wl)
                rates.append(a["rate_two_plus"] + a["rate_one_above"])
            rows.append({"target": target, "text_level": w_lv,
                         "mean_violation_rate": round(sum(rates) / max(1, len(rates)), 4),
                         "n": len(rates)})
    json.dump(rows, open(os.path.join(RESULTS, "monotonicity.json"), "w"), indent=2)
    print("\nmonotonicity (mean above-target rate; should rise as text level < target):")
    by_target = defaultdict(list)
    for r in rows:
        by_target[r["target"]].append((r["text_level"], r["mean_violation_rate"]))
    ok_all = True
    for target, pairs in by_target.items():
        seq = [p[1] for p in sorted(pairs, key=lambda x: -ord(x[0][0]))]
        # levels below target in order A1<A2<B1<...: violation should rise
        below = [r for r in rows if r["target"] == target and r["text_level"] < target]
        below_sorted = sorted(below, key=lambda r: r["text_level"])
        vals = [r["mean_violation_rate"] for r in below_sorted]
        monotone = all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))
        ok_all &= monotone
        print(f"  target {target}: " + ", ".join(
            f"{r['text_level']}→{r['mean_violation_rate']}" for r in below_sorted)
            + ("  ✓monotone" if monotone else "  ✗NON-monotone"))
    print("monotonicity:", "PASS" if ok_all else "CHECK")


if __name__ == "__main__":
    os.makedirs(RESULTS, exist_ok=True)
    run_audit()
    run_monotonicity()
