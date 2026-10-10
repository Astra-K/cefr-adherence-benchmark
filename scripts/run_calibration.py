"""Run calibration, write results/calibration_v1.json + a readable summary,
and dump per-window measures for later analysis."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from cefr_bench.calibrate import calibrate
from cefr_bench.wordlists import get_lists

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

if __name__ == "__main__":
    wl = get_lists()
    result, recs = calibrate(wl)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "calibration_v1.json"), "w") as f:
        json.dump(result, f, indent=2)
    with open(os.path.join(OUT, "calibration_windows_v1.jsonl"), "w") as f:
        for r in recs:
            r = {k: v for k, v in r.items() if k != "text"}  # no third-party text
            f.write(json.dumps(r) + "\n")
    # summary
    print("=== THRESHOLDS ===")
    for lv, th in result["thresholds"].items():
        print(f"{lv}: cap1={th['cap_one_above']} ci={th['cap_one_ci']} | "
              f"cap2+={th['cap_two_plus']} ci={th['cap_two_ci']} | "
              f"floor={th['floor_min_share']} gfloor={th['grammar_floor']} | "
              f"bands={th['syntax_bands']}")
    print("\n=== JOINT PASS ===")
    print(json.dumps(result["joint_pass"], indent=2))
    print("\n=== SEPARATION ===")
    print(json.dumps(result["separation"], indent=2))
    print("\n=== UNLISTED SHARE (domain-shift signal) ===")
    for lv, s in result["stats"].items():
        print(f"{lv}: unlisted share mean={s['unlisted_share_of_content']['mean']}, p90={s['unlisted_share_of_content']['p90']}, n={s['n_windows']}/{s['n_assessable']}")
    if result["notes"]:
        print("\nNOTES:", result["notes"])
