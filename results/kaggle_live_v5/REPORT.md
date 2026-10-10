# Kaggle live benchmark verification

- Rows: **180/180**
- Mean score: **0.9612**
- Relevant: **180/180**
- Relevant and adherent: **154/180**
- Score parity: **180/180**
- Near combined 2048-token cap: **0/180**
- Non-terminal endings near cap: **0/180**
- Short answers near cap: **0/180**
- Artifact-accounted cost: **$1.008716**
- Task SHA-256: `4466d17236635941357937a9813a0ae371495381b5cd844d1d365e488a2e189d`
- Verification errors: **0**

Near-cap counts are diagnostics, not automatic proof of truncation because the downloaded schema omits provider finish reasons.

## Manual visible-answer review

- Visible endings reviewed: **180/180**
- Heuristic-flagged endings reviewed: **25/25**
- Visibly truncated answers: **0/180**
- Verdict: **passes visible-answer integrity gate**

All heuristic flags were false positives caused by Markdown italics, quoted examples, emoji, or closing quotation marks. Combined output-token counts include hidden reasoning; high combined counts did not correspond to incomplete visible answers in this run. The exact review receipt is `manual_review.json`; the complete ending ledger is `ending_review.txt`.
