---
title: Can an AI tutor stay at the learner's level?
published: false
tags: devchallenge, kagglechallenge, ai, machinelearning
cover_image: https://raw.githubusercontent.com/Astra-K/cefr-adherence-benchmark/main/assets/cefr-adherence-cover.png
---

*This is a submission for the [Kaggle Benchmarking Challenge](https://dev.to/challenges/kaggle-2026-09-23).*

A tutor can give a correct answer and still fail the learner. Ask for an A1 explanation and many models will return a polished paragraph full of vocabulary and grammar the student has not learned yet.

I built a benchmark for that gap: can a model answer a real English-learning question while staying near a requested CEFR level?

## What I benchmarked

The task gives a model one of 30 questions from English Language Learners Stack Exchange and asks for an answer at A1, B1, or C1. Each question appears twice:

- **Bare:** ask for the target level and nothing else.
- **Informed:** include the vocabulary and grammar guidance used by the scorer.

That produces 180 rows per model: 30 questions × 3 levels × 2 conditions.

For a fixed reply and relevance verdict, the CEFR component is deterministic. It combines vocabulary, grammar, and syntax:

```text
score = 0.4 × vocabulary + 0.4 × grammar + 0.2 × syntax
```

A separate context-bound judge checks whether the answer addresses the learner's actual question. This is deliberately narrow. The judge does not grade style or factual correctness, and it does not replace the deterministic CEFR scorer. If the judge fails or returns malformed evidence, the row stays unscored instead of passing by default.

There is no numeric rule such as `score >= 0.8`. The separate Boolean `adherent` diagnostic requires the structural gate, the level-specific vocabulary ceiling and floor, and the grammar ceiling to pass. The “relevant and adherent” counts below additionally require the relevance verdict to pass. Syntax affects the continuous score but not that Boolean diagnostic.

The informed prompt calls its plain-language generation guidance `PASSING RULES`; that heading does not create a Kaggle pass/fail threshold. Its request for 3–5 sentences is prompt guidance, while the Boolean scorer's structural gate requires at least two detected sentences.

### How I calibrated the level thresholds

I did not choose the vocabulary and syntax limits after seeing model answers. With seed 13, I sampled 913 windows of 3–5 sentences at A1, B1, and C1 from five frozen UniversalCEFR English subsets. Of those, 891 windows contained at least 20 recognized content words and entered the threshold fit.

For each target level, the vocabulary ceilings began at the 90th percentile of the corresponding violation rate in genuine level-labelled windows. I then loosened the two ceilings together in 5% steps until at least 90% of assessable windows passed both. The vocabulary floor came from the 10th percentile of the share of words in the target's top two bands. Syntax bands use the 5th–95th percentile range for sentence length, clauses per sentence, and word length. Grammar ceilings use the 90th-percentile absolute count of detected above-level constructions.

| Target | One level above | Two-plus levels above or unlisted | Vocabulary floor | Above-level grammar allowance |
|---|---:|---:|---:|---:|
| A1 | 13.57% | 14.16% | none by design | at most 1 hit |
| B1 | 5.45% | 9.91% | at least 6.25% A2/B1 words | at most 2 hits |
| C1 | 1.39% | 13.51% | none: calibrated 10th percentile was zero | 0 hits |

At scoring time, each vocabulary allowance has a one-token minimum so that one necessary off-list word does not automatically fail a short reply. The zero C1 floor is not hidden: it is why I describe the benchmark as testing ceiling adherence rather than proving complete C1 proficiency, and why a validated C1 floor is the first item in the follow-up plan. The frozen aggregate calibration artifact and code are public.[6][7]

The Kaggle upload is one Python file. It contains the scorer, calibrated thresholds, word profiles, 30 attributed questions, prompts, and an eight-pair judge preflight. It needs no project files or internet downloads at runtime.

## Models tested

### Local development pilot

Before publishing to Kaggle, I froze 360 outputs from two quantized local models:

| Model | Parameters | Mean score | Relevant and adherent |
|---|---:|---:|---:|
| Qwen3.5-2B-4bit | 2B | 0.8321 | 113/180 |
| Qwen3.5-9B-4bit | 9B | 0.9495 | 148/180 |

Both models used the same 30 questions, prompts, decoding configuration, and 512-token output ceiling. The relevance decisions were frozen before the parity-fixed v5 rescore.

### Kaggle models

The final Kaggle run used Gemini 3.7 Flash with supported low reasoning and a 2,048-token combined reasoning-and-answer allowance:

| Kaggle model | Why it is in the lineup | Mean score |
|---|---|---:|
| Gemini 3.7 Flash | Efficient mandatory-thinking model available through Kaggle's hosted catalogue | 0.9612 |

The two local Qwen models plus one live Kaggle model are enough for a bounded, real-model result, but not for a broad scaling or cross-provider claim. A second Kaggle model would strengthen the public leaderboard; it was deliberately deferred because it required separate spend approval.

## Findings

The 9B local model scored 0.9495, compared with 0.8321 for the 2B model. It also produced more replies that were both relevant and CEFR-adherent: 148 versus 113.

That result needs a narrow interpretation. It says the 9B model handled this scorer and these 30 questions better. It does not show that parameter count alone causes CEFR adherence, and two models are not a scaling study.

The informed prompt did not help every target level equally. In the frozen local pilot it generally produced shorter outputs, while the score effect varied by model and target level. The paired bare/informed design exposes that trade-off instead of assuming more instructions always help.

The largest methodological surprise came from C1. The calibrated vocabulary floor collapsed to zero. A reply can avoid above-level vocabulary and still sound much simpler than C1. I tested a separate descriptor-based judge as a possible repair. It passed the authored A1 negative controls but detected only 4.17% of the labelled C1/C2 positives, so I rejected it rather than tuning after seeing the answers.

That failed evaluator is not part of the benchmark score. It is preserved as an optional diagnostic and a record of what did not work.

The final Kaggle run completed all 180 rows. Independent rescoring matched Kaggle on 180/180 rows; all 180 replies were relevant, 154 were both relevant and CEFR-adherent, no output was near the combined 2,048-token cap, and manual review found zero visibly truncated answers. An earlier 1,024-token run scored 0.9679 but was rejected because 14 replies ended mid-sentence—platform completion alone was not enough.

Kaggle's task column displays 55.6%, which matches the lowest v5 row score (`0.5558`) after percentage formatting. It is not a response pass rate and not the 180-row mean (`0.9612`). Because the float-returning task has no numeric pass threshold, I disabled the benchmark's overall-score column and report the verified aggregates explicitly.

## What I would measure next

The highest-priority change is a validated C1 floor. That needs source-disjoint, participant-disjoint labelled text or human ratings on short tutor replies. I would also add factual-correctness checks, because relevance only tells us that an answer addresses the question.

A larger question set would reduce item sensitivity. The current 30 questions are real and fully attributed, but they are not a representative sample of all learner levels, first languages, or question types.

## Reproducibility and attribution

The repository preserves the generated task, deterministic scorer tests, source hashes, result summaries, and a per-item attribution table.

Kaggle currently displays an Apache 2.0 metadata label on the task and benchmark pages. The uploaded notebook and source repository preserve the actual artifact terms: original benchmark code is AGPL-3.0-only, while embedded third-party material retains its separately listed licences. The platform label does not replace those notices.

The benchmark uses CEFR-J Vocabulary Profile 1.5 and Grammar Profile 20180315 from Tono Laboratory at Tokyo University of Foreign Studies, plus the Octanove C1/C2 profile under CC BY-SA 4.0.[1] The learner questions retain the original author, profile link, question link, applicable CC BY-SA revision licence, source snapshot hash, and transformation record.[2]

No UniversalCEFR learner text is embedded in the Kaggle task or public source repository. Frozen English subsets contributed aggregate calibration statistics; the public evidence retains source identities, hashes, aggregate results, and their recorded CC BY-NC-SA 4.0 or CC0 1.0 terms.[5]

## My benchmark

**Kaggle task:** <https://www.kaggle.com/benchmarks/tasks/astrakamratowski/cefr-adherence-benchmark/5>

**Kaggle benchmark:** <https://www.kaggle.com/benchmarks/astrakamratowski/cefr-adherence-benchmark>

**Source repository:** <https://github.com/Astra-K/cefr-adherence-benchmark>

## Sources

[1] https://raw.githubusercontent.com/openlanguageprofiles/olp-en-cefrj/master/README.md — Open Language Profiles: CEFR-J datasets and terms
[2] https://meta.stackexchange.com/help/licensing — Stack Exchange network licensing and revision-specific licence guidance
[5] https://universalcefr.github.io — UniversalCEFR data directory and licences
[6] https://github.com/Astra-K/cefr-adherence-benchmark/blob/main/results/calibration_v1.json — frozen aggregate calibration artifact
[7] https://github.com/Astra-K/cefr-adherence-benchmark/blob/main/src/cefr_bench/calibrate.py — calibration procedure
