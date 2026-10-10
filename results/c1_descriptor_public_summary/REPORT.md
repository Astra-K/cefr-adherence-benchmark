# C1 descriptor diagnostic — aggregate public summary

The proposed descriptor judge was rejected and never added to the benchmark score. It was tested on 36 labelled ICLE500 essays—12 each at B2, C1, and C2—plus five authored A1 negative controls.

| Source label | Below B2 | B2 | C1 | C2 | Insufficient evidence |
|---|---:|---:|---:|---:|---:|
| B2 | 4 | 8 | 0 | 0 | 0 |
| C1 | 0 | 12 | 0 | 0 | 0 |
| C2 | 0 | 11 | 1 | 0 | 0 |

- Sensitivity to labelled C1-or-higher: **1/24 (4.17%)**; Wilson 95% interval **0.74–20.24%**.
- Specificity on labelled B2: **12/12 (100%)**; Wilson 95% interval **75.75–100%**.
- Authored A1 negative-control false positives: **0/5**.
- Abstentions: **0/36**.
- Pre-specified pilot gate: **failed**.

The rubric was not tuned after observing these outcomes, and no sweep of the 360 saved model replies was started.

## Limitations

- ICLE500 was also used in earlier ceiling calibration; this was not source-disjoint validation.
- Original parent-selection receipts and participant identifiers were unavailable.
- UniversalCEFR reports very low annotator agreement for ICLE500 (Rasch kappa −0.02).
- Whole learner essays differ materially from short tutor replies.
- Twelve texts per level form a small, non-representative pilot.
- Raw learner texts and subscription-session traces are intentionally excluded from the public release. Their source hashes and aggregate metrics are retained in `metrics.json`.
