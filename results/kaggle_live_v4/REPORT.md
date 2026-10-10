# Kaggle live benchmark verification

- Rows: **180/180**
- Mean score: **0.9679**
- Relevant: **180/180**
- Relevant and adherent: **153/180**
- Score parity: **180/180**
- Near combined 1024-token cap: **19/180**
- Non-terminal endings near cap: **14/180**
- Short answers near cap: **9/180**
- Artifact-accounted cost: **$0.991828**
- Task SHA-256: `e0769398fb5897c66f06cd82440c41495e003d8f2e8c4782ca3cc7a18f050e6a`
- Verification errors: **0**
- Manual publication verdict: **REJECTED**
- Visibly truncated answers: **14/180** (`1, 25, 26, 31, 37, 61, 85, 109, 112, 115, 121, 139, 145, 157`)

The downloaded schema omits provider finish reasons. Manual inspection of all 19 cap-pressure rows found 14 answers ending mid-sentence at 1,020 output tokens. Version 4 is internally consistent but not publication-valid; `manual_review.json` is the bounded review receipt.
