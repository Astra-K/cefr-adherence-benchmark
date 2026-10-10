"""v5 rescore: parity-fixed scorer re-applied to the frozen 360 replies.

Inputs (read-only):
  results/qwen_local_subscription_v4/scored.jsonl  — replies + frozen judge relevance
  kaggle_task/cefr_scorer_embedded.py              — parity-fixed deterministic scorer (sha256-pinned in output)

Output:
  results/qwen_local_benchmark_v5/scored.jsonl, summary.csv, REPORT.md,
  verification.json
Never modifies v4 or raw pilot data.
"""
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kaggle_task"))
import cefr_scorer_embedded as emb  # noqa: E402

V4 = ROOT / "results" / "qwen_local_subscription_v4" / "scored.jsonl"
OUT = ROOT / "results" / "qwen_local_benchmark_v5"


def build_out_row(row: dict) -> dict:
    """Re-score one frozen row, preserving sparse gate-failure results."""
    relevant = row.get("relevance") is True
    score = emb.score_reply(row["reply"], row["level"], relevant=relevant)
    return {
        "key": row["key"], "model": row["model"], "level": row["level"],
        "condition": row["condition"], "relevance": row.get("relevance"),
        "old_combined_v4": row["score"]["combined"],
        "new_combined_v5": score["combined"],
        "adherent_v5": score["adherent"],
        "relevant_adherent_v5": bool(relevant and score["adherent"]),
        "flags_v5": score["flags"],
        "vocab": score.get("vocab"), "n_sentences": score["n_sentences"],
    }


def main() -> int:
    rows = [json.loads(l) for l in V4.read_text().splitlines() if l.strip()]
    assert len(rows) == 360, len(rows)
    assert len({(row["model"], row["key"]) for row in rows}) == 360
    input_sha = hashlib.sha256(V4.read_bytes()).hexdigest()
    emb_sha = hashlib.sha256((ROOT / "kaggle_task" / "cefr_scorer_embedded.py").read_bytes()).hexdigest()

    OUT.mkdir(parents=True, exist_ok=True)
    out_rows = [build_out_row(row) for row in rows]

    with open(OUT / "scored.jsonl", "w") as f:
        for r in out_rows:
            f.write(json.dumps(r) + "\n")

    # summary per model/level/condition
    cells = {}
    for r in out_rows:
        cells.setdefault((r["model"], r["level"], r["condition"]), []).append(r)
    with open(OUT / "summary.csv", "w") as f:
        f.write("model,level,condition,n,mean_v4,mean_v5,delta,relevant_adherent_v5\n")
        for (m, lv, cond), rs in sorted(cells.items()):
            m4 = statistics.mean(x["old_combined_v4"] for x in rs)
            m5 = statistics.mean(x["new_combined_v5"] for x in rs)
            ra = sum(1 for x in rs if x["relevant_adherent_v5"])
            f.write(f"{m},{lv},{cond},{len(rs)},{m4:.4f},{m5:.4f},{m5 - m4:+.4f},{ra}/{len(rs)}\n")

    # overall comparison
    o4 = statistics.mean(r["old_combined_v4"] for r in out_rows)
    o5 = statistics.mean(r["new_combined_v5"] for r in out_rows)
    deltas = [abs(r["new_combined_v5"] - r["old_combined_v4"]) for r in out_rows]
    changed = sum(1 for r in out_rows if abs(r["new_combined_v5"] - r["old_combined_v4"]) > 1e-9)
    adm = {}
    for m in sorted({r["model"] for r in out_rows}):
        mr = [r for r in out_rows if r["model"] == m]
        adm[m] = (statistics.mean(r["new_combined_v5"] for r in mr),
                  sum(1 for r in mr if r["relevant_adherent_v5"]))

    report = [
        "# v5 rescore — parity-fixed scorer on frozen 360 replies",
        "",
        f"- embedded scorer sha256: `{emb_sha}`",
        f"- relevance verdicts: frozen from v4 (subscription judge, GPT-6.1-sol)",
        f"- overall mean: v4 {o4:.4f} -> v5 {o5:.4f}",
        f"- replies with changed combined: {changed}/360",
        f"- max abs per-reply delta: {max(deltas):.4f}",
        "",
        "| model | mean_v5 | relevant+adherent |",
        "|---|---:|---:|",
    ]
    for m, (mv, ra) in adm.items():
        report.append(f"| {m} | {mv:.4f} | {ra}/180 |")
    (OUT / "REPORT.md").write_text("\n".join(report) + "\n")

    verification = {
        "verified": True,
        "rows": len(out_rows),
        "unique_model_keys": len({(row["model"], row["key"]) for row in out_rows}),
        "cells": len(cells),
        "sparse_gate_failures": sum(row["vocab"] is None for row in out_rows),
        "changed_scores": changed,
        "max_abs_delta": round(max(deltas), 4),
        "overall_mean_v4": round(o4, 4),
        "overall_mean_v5": round(o5, 4),
        "input_scored_v4_sha256": input_sha,
        "embedded_scorer_sha256": emb_sha,
        "outputs": {
            name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
            for name in ("scored.jsonl", "summary.csv", "REPORT.md")
        },
    }
    (OUT / "verification.json").write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n"
    )

    print(f"v5 written: {len(out_rows)} rows; overall {o4:.4f} -> {o5:.4f}; changed {changed}/360")
    for m, (mv, ra) in adm.items():
        print(f"  {m}: mean_v5 {mv:.4f}  relevant+adherent {ra}/180")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
