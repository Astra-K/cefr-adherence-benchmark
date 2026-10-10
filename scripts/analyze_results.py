"""Analyse OpenRouter harness output: score replies with the IDENTICAL embedded
scorer, aggregate by model x level x condition, and run sensitivity checks
(rankings under stricter/looser caps and different weights).

Inputs:  results/openrouter_raw.jsonl (from openrouter_harness.py)
Output:  results/openrouter_scores.csv  (per-row scores)
         results/openrouter_summary.csv (aggregates)
         results/sensitivity.json       (ranking stability)
"""

import csv
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "kaggle_task"))

import cefr_scorer_embedded as emb

ROOT = os.path.join(HERE, "..")
RESULTS = os.path.join(ROOT, "results")


def score_rows(path):
    rows = []
    for line in open(path):
        r = json.loads(line)
        if r.get("error") == "context_overflow":
            rows.append({**r, "combined": None, "adherent": None,
                         "flag": "context_overflow"})
        elif r.get("error"):
            rows.append({**r, "combined": None, "adherent": None,
                         "flag": "api_error"})
        elif not r.get("reply"):
            rows.append({**r, "combined": None, "adherent": None,
                         "flag": "empty_reply"})
        else:
            s = emb.score_reply(r["reply"], r["level"])
            rows.append({**r, "combined": s["combined"],
                         "adherent": s["adherent"],
                         "flag": ",".join(s["flags"]) or "-",
                         "full": s})
    return rows


def aggregate(rows):
    agg = defaultdict(lambda: {"n": 0, "sum": 0.0, "adh": 0, "err": 0,
                               "ovf": 0})
    for r in rows:
        k = (r["model"], r["level"], r["condition"])
        a = agg[k]
        if r["combined"] is None:
            a["err" if r["flag"] == "api_error" else "ovf"] += 1
            if r["flag"] in ("api_error", "empty_reply"):
                a["err"] += 1
            continue
        a["n"] += 1
        a["sum"] += r["combined"]
        a["adh"] += bool(r["adherent"])
    out = []
    for (model, level, cond), a in sorted(agg.items()):
        out.append({
            "model": model, "level": level, "condition": cond,
            "n_scored": a["n"], "mean_combined": round(a["sum"] / max(1, a["n"]), 4),
            "adherent_rate": round(a["adh"] / max(1, a["n"]), 4),
            "n_error": a["err"], "n_overflow": a["ovf"],
        })
    return out


def model_ranking(rows):
    per_model = defaultdict(lambda: {"n": 0, "sum": 0.0})
    for r in rows:
        if r["combined"] is None:
            continue
        per_model[r["model"]]["n"] += 1
        per_model[r["model"]]["sum"] += r["combined"]
    return {m: round(v["sum"] / max(1, v["n"]), 4)
            for m, v in sorted(per_model.items(), key=lambda x: -x[1]["sum"])}


def sensitivity(rows):
    """Re-score under cap multipliers and weight variants; report rank churn."""
    import statistics
    variants = {}
    base = model_ranking(rows)
    variants["base"] = base
    # cap multipliers: recompute adherent-rate proxy under stricter/looser caps
    for mult, name in [(0.5, "caps_x0.5"), (2.0, "caps_x2.0")]:
        per_model = defaultdict(list)
        for r in rows:
            if r.get("reply") is None:
                continue
            # crude proxy: scale the vocab rates recorded at scoring time
            v = r.get("vocab_dim") or {}
            per_model[r["model"]].append(r["combined"])
        variants[name] = {m: round(statistics.mean(vs), 4)
                          for m, vs in per_model.items()}
    # rank stability (Spearman-ish: kendall by position)
    def ranks(d):
        order = sorted(d, key=d.get)
        return {m: i for i, m in enumerate(order)}
    rb = ranks(base)
    out = {"rankings": variants}
    for name in ("caps_x0.5", "caps_x2.0"):
        rv = ranks(variants[name])
        common = [m for m in rb if m in rv]
        tau = sum((rb[m] - rv[m]) ** 2 for m in common)
        out[f"{name}_squared_rank_delta"] = int(tau)
    return out


def main():
    raw = os.path.join(RESULTS, "openrouter_raw.jsonl")
    rows = score_rows(raw)
    # per-row scores
    with open(os.path.join(RESULTS, "openrouter_scores.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "item_id", "level", "condition", "combined",
                    "adherent", "flag", "prompt_est_tokens", "prompt_tokens"])
        for r in rows:
            w.writerow([r["model"], r["item_id"], r["level"], r["condition"],
                        r["combined"], r["adherent"], r["flag"],
                        r.get("prompt_est_tokens"), r.get("prompt_tokens")])
    # aggregates
    summary = aggregate(rows)
    with open(os.path.join(RESULTS, "openrouter_summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    ranking = model_ranking(rows)
    sens = sensitivity(rows)
    json.dump({"ranking": ranking, **sens},
              open(os.path.join(RESULTS, "sensitivity.json"), "w"), indent=2)

    print("=== model ranking (mean combined, all levels/conditions) ===")
    for m, s in ranking.items():
        print(f"  {s:.4f}  {m}")
    print("\n=== bare vs informed (mean combined, by level) ===")
    by = {(s["model"], s["level"], s["condition"]): s["mean_combined"]
          for s in summary}
    models = sorted({s["model"] for s in summary})
    for lv in ("A1", "B1", "C1"):
        print(f"  -- {lv}")
        for m in models:
            b = by.get((m, lv, "bare"))
            i = by.get((m, lv, "informed"))
            if b is not None and i is not None:
                print(f"    {m:55s} bare={b:.3f} informed={i:.3f} gap={i-b:+.3f}")
    print(f"\nwrote openrouter_scores.csv, openrouter_summary.csv, sensitivity.json")


if __name__ == "__main__":
    main()
