# Story and publication notes

The publishable article now lives in [`DEV_SUBMISSION_DRAFT.md`](DEV_SUBMISSION_DRAFT.md). This file records the remaining editorial decisions without mixing them into the draft.

## Core story

An AI tutor can answer correctly while using language above the learner's level. The benchmark tests that gap on 30 real English-learning questions at A1, B1, and C1, with bare and scorer-informed prompts.

The useful result is not simply that the 9B local model outscored the 2B model. The benchmark also exposed a weak C1 floor and rejected an attempted descriptor judge that failed validation. Reporting the failed evaluator makes the submission more honest and more useful.

## Evidence allowed in the article

- 360 frozen local replies: 180 per model.
- Qwen3.5-2B-4bit: mean 0.8321; 113/180 relevant and adherent.
- Qwen3.5-9B-4bit: mean 0.9495; 148/180 relevant and adherent.
- Combined mean: 0.8908.
- The v5 scorer changed 22/360 scores relative to v4; maximum absolute correction 0.3750.
- The optional C1 descriptor judge failed its gate with 4.17% sensitivity and is not part of the primary score.

- Kaggle version 5: 180/180 completed and 180/180 local score parity; mean 0.9612; 180/180 relevant; 154/180 relevant plus CEFR-adherent; 0 near-cap outputs; 0 visibly truncated answers after full ending review.
- Kaggle's 55.6% task display matches the minimum row score (0.5558), not a pass rate or the arithmetic mean. The task defines no numeric pass threshold; the benchmark uses No overall score.

Do not claim that model size causes adherence, that the scorer proves language proficiency, that rejected version 4 is publication-valid, or that the two-model local pilot represents the wider model market.

## Still required before DEV publication

1. Review the final documentation changes and public benchmark description.
2. Commit and push the final documentation update under Astra-K.
3. Re-run the release gates and anonymous-link checks against the final commit.
4. Publish exactly one DEV submission with the required tags before the contest deadline, only after explicit human approval.

## Optional, not blocking

- A paid API run on a larger model. Only do this if the article will discuss frontier-model behavior.
- Further work on a C1 descriptor judge. Treat it as a separate experimental task until it passes a locked validation set.
- More learner questions or human ratings.

## Editorial checks

- Keep the local and Kaggle result tables separate.
- State which judge produced each relevance label.
- Report unscored and truncated rows.
- Preserve per-item attribution and ShareAlike notices.
- Link the public Kaggle benchmark collection, not only the task or notebook.
