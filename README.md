# CEFR-adherence benchmark

Can a language model answer an English learner at the requested level instead of merely answering correctly? This benchmark measures tutor replies at A1, B1, and C1 under two conditions: a bare level request and an informed prompt that exposes the scorer's vocabulary and grammar guidance.

The project is the published [DEV submission](https://dev.to/astra_k/can-an-ai-tutor-stay-at-the-learners-level-270k) for the [Kaggle Benchmarks Challenge][4]. The [public Kaggle benchmark](https://www.kaggle.com/benchmarks/astrakamratowski/cefr-adherence-benchmark) contains the independently verified [version 5 task](https://www.kaggle.com/benchmarks/tasks/astrakamratowski/cefr-adherence-benchmark/5): 180/180 completed rows, 180/180 score parity, zero visible truncations, and mean score 0.9612.

## Current evidence

The frozen local pilot contains 360 replies: 30 learner questions × 3 target levels × 2 prompt conditions × 2 local models. The table uses the parity-fixed v5 scorer and the frozen relevance decisions from the audited subscription-judge run.

| Model | Mean score | Relevant and CEFR-adherent |
|---|---:|---:|
| `mlx-community/Qwen3.5-2B-4bit` | 0.8321 | 113/180 |
| `mlx-community/Qwen3.5-9B-4bit` | 0.9495 | 148/180 |
| Combined | 0.8908 | 261/360 |

The larger local model scored higher, but this two-model pilot is not enough to support a general scaling claim. Full cell-level results are in [`results/qwen_local_benchmark_v5/summary.csv`](results/qwen_local_benchmark_v5/summary.csv), with a short report in [`results/qwen_local_benchmark_v5/REPORT.md`](results/qwen_local_benchmark_v5/REPORT.md).

The final Kaggle-hosted run used Gemini 3.7 Flash on all 180 rows. The independently recomputed arithmetic mean was **0.9612**, with **180/180 relevant** and **154/180 relevant-plus-adherent** replies. Independent verification found **180/180 score parity**, **0/180 near-cap outputs**, and **0/180 visibly truncated answers**. See [`results/kaggle_live_v5/REPORT.md`](results/kaggle_live_v5/REPORT.md).

Kaggle's task column displays **55.6%**, which matches the run's lowest row score (`0.5558`) after percentage formatting; it is not a pass rate or the 180-row mean. This float-returning task defines no numeric pass threshold, so the public benchmark intentionally uses **No overall score**. The separate relevant-plus-adherent diagnostic is described below.

## What the scorer measures

The deterministic scorer is pure Python and returns a value from 0 to 1.

```text
reply
  -> structural gate
  -> context-bound relevance gate
  -> vocabulary ceiling and floor
  -> grammar ceiling
  -> syntax bands
  -> 0.4 vocabulary + 0.4 grammar + 0.2 syntax
```

- The structural gate requires non-empty output, at least two detected sentences, and at least one recognized ASCII alphabetic token. English relevance is handled separately by the context-bound judge; this gate is not a language detector.
- Vocabulary ceilings penalize words above the target band. The B1 floor requires some A2/B1 vocabulary; the calibrated C1 floor is zero and is therefore a known blind spot.
- Grammar ceilings count detected above-level constructions.
- Syntax compares sentence length, clauses per sentence, and word length with calibrated bands.
- The Kaggle task uses `kbench.judge_llm` only for binary, context-bound relevance. Missing or malformed judge evidence raises an unscored error instead of passing by default. Eight matched and mismatched probes must pass before the sweep starts.

There is no rule such as `score >= 0.8`. The Boolean `adherent` diagnostic is true when the structural gate passes, the vocabulary ceiling is respected, the applicable vocabulary floor is met, and the above-level grammar count stays within its calibrated limit. The reported relevant-plus-adherent count additionally requires the relevance judge to pass. Syntax changes the continuous 0–1 score but does not decide that Boolean diagnostic.

The informed prompt uses the heading `PASSING RULES` for plain-language generation guidance. That wording does not create a Kaggle pass/fail threshold. In particular, its request for 3–5 sentences is prompt guidance; the Boolean scorer only requires at least two detected sentences at the structural gate.

The relevance judge is part of the primary Kaggle task because a fluent off-topic answer should not earn a high adherence score. A separate C1 descriptor judge was tested as an experimental extension, but it achieved only 4.17% sensitivity on the labelled pilot and failed its validation gate. It remains an optional research direction and is not included in the primary score.

## Repository map

```text
src/cefr_bench/        canonical scorer, prompts, thresholds, and utilities
data/items.json        30 attributed ELL Stack Exchange questions
data/golden.json       hand-written scorer controls
kaggle_task/cefr_task.py
                       generated single-file Kaggle upload artifact
scripts/               generation, calibration, audit, and evaluation tools
results/               curated reports, summaries, manifests, and diagnostics
tests/                 scorer, parity, relevance, and artifact tests
```

`kaggle_task/cefr_scorer_embedded.py` is retained for local parity testing. The upload artifact does not import it: `cefr_task.py` embeds the scorer, profiles, items, attribution metadata, and prompts in one file.

## Reproduce the local checks

Python 3.11 is the verified interpreter.

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
env -u PYTHONPATH .venv/bin/python scripts/gen_kaggle_task.py
env -u PYTHONPATH .venv/bin/python -m pytest tests -q
git diff --check
git diff --exit-code -- kaggle_task/cefr_task.py kaggle_task/cefr_scorer_embedded.py
```

The `env -u PYTHONPATH` prefix prevents an unrelated Hermes runtime path from shadowing the project environment. In a public-only checkout, the suite reports 85 passed, 2 intentional private-evidence skips, and 5 SDK subtests; the owner tree with those excluded inputs reports 87 passed and 5 SDK subtests. Aggregate Qwen evidence, exact model IDs, hashes, and per-cell summaries are public. The 360 full generated replies are intentionally excluded; `scripts/rescore_v5_parity.py` is for owners who retain or regenerate that local input.

## Kaggle publication workflow

Kaggle's CLI converts the file passed to `kaggle b t push -f` into the task notebook and provides commands for model runs, status, downloads, and publication.[3]

The repository already has Kaggle CLI 2.2.4 installed in `.venv`. The owner must authenticate because the command writes a short-lived Model Proxy credential to `.env`:

```bash
source .venv/bin/activate
kaggle auth login
kaggle b auth -y
kaggle b t models
```

`kaggle auth login` opens Kaggle's OAuth flow and caches the account credential locally. `kaggle b auth -y` then writes the short-lived Model Proxy variables to the gitignored `.env`; do not paste either credential into an issue, commit, or chat. Kaggle CLI 2.2.4 does not expose the documented `kaggle b quota` command in every build, so verify the daily and monthly AI-quota counters in the task editor before a live run.

The current local candidate fixes generation at temperature `0.7`, top-p `0.8`, Gemini's supported `low` reasoning level, and a 2,048-token combined reasoning-and-answer ceiling. It uses one attempt per row so a provider-wide failure cannot silently double the inference budget. Version 4 used 1,024 tokens and is retained only as rejected evidence because 14/180 visible answers ended mid-sentence.

```bash
kaggle b t push cefr-adherence-benchmark -f kaggle_task/cefr_task.py --wait
kaggle b t status cefr-adherence-benchmark
kaggle b t run cefr-adherence-benchmark -m <MODEL> --wait
kaggle b t status cefr-adherence-benchmark
kaggle b t download cefr-adherence-benchmark --include-source -o results/kaggle_live
```

Inspect every failed or unscored row before publication. If the task and runs are sound:

```bash
kaggle b t publish cefr-adherence-benchmark
```

The public benchmark is <https://www.kaggle.com/benchmarks/astrakamratowski/cefr-adherence-benchmark>. It contains the public version 5 task and its imported Gemini 3.7 Flash result. Its overall-score mode is deliberately disabled because Kaggle's displayed task value matches the minimum row rather than the independently recomputed row mean.

### Are the two local models and one live Kaggle model enough?

They demonstrate that the benchmark runs against real models and support a bounded comparison: two frozen local Qwen models plus one independently audited Kaggle-hosted Gemini run. They do not support a broad scaling or cross-provider claim. A second Kaggle model would strengthen the leaderboard but is not required for this bounded release and was not run.

## Data, attribution, and licences

The generated Kaggle notebook carries the source and licence notices in a visible Markdown cell. [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) also lists all 30 question authors, profile links, question URLs, and per-revision licences.

- CEFR-J Vocabulary Profile 1.5 and Grammar Profile 20180315 are copyright Tono Laboratory, TUFS. The upstream repository permits research and commercial use without charge when properly cited.[1]
- The Octanove Vocabulary Profile C1/C2 1.0 is licensed CC BY-SA 4.0.[1]
- The learner questions come from English Language Learners Stack Exchange. Stack Exchange applies Creative Commons Attribution-ShareAlike per post revision; the frozen API records identify CC BY-SA 3.0 or 4.0 for each item.[2]
- Frozen UniversalCEFR subsets were used to derive aggregate calibration statistics. The public repository retains source identities, hashes, aggregate statistics, and licence metadata—not the learner texts themselves. Four source subsets are CC BY-NC-SA 4.0 and ICLE500 is CC0 1.0 according to the UniversalCEFR directory.[5] No UniversalCEFR text is embedded in the Kaggle task or published run artifacts.
- The Kaggle Benchmarks SDK is an Apache-2.0 runtime dependency and is not vendored.

Attribution does not cancel ShareAlike obligations. Preserve `ITEMS` metadata and the third-party notices when redistributing or adapting the task.

Kaggle currently displays an Apache 2.0 metadata label on the task and benchmark pages. The uploaded notebook and this repository preserve the actual artifact terms: original benchmark code is AGPL-3.0-only, and embedded third-party material retains its separately listed licences. The platform label does not replace those copyright and licence notices.

## Limitations

- The vocabulary profiles are CEFR-J resources, not a complete representation of global English usage.
- The 30 learner questions are real but small and not labelled by learner proficiency.
- The C1 vocabulary floor is not validated, so an under-level reply can pass the current C1 ceiling checks.
- Grammar detectors cover selected constructions rather than the full CEFR descriptor space.
- Relevance is not factual correctness.
- The local pilot uses two quantized Qwen models and a different judge route from Kaggle's live task.
- Some local generations reached their 512-token ceiling; the reports preserve rather than hide those cases. Kaggle version 4 was likewise rejected—not published—after 14/180 answers visibly ended mid-sentence at its 1,024-token combined ceiling.

## Sources and prior work

The repository's method also references UniversalCEFR (arXiv:2506.01419), Malik et al. (2024), *From Tarzan to Tolkien*, and the TSAR 2025 readability-controlled simplification shared task. These are context for the method, not sources of redistributed text in the Kaggle artifact.

## Source repository

Public source: <https://github.com/Astra-K/cefr-adherence-benchmark>

## Licence

Copyright © 2026 Astra / Astra-K. Original benchmark code is licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). Third-party datasets and adapted question text retain thei...[truncated]

## Sources

[1] https://raw.githubusercontent.com/openlanguageprofiles/olp-en-cefrj/master/README.md — Open Language Profiles: CEFR-J datasets and terms
[2] https://meta.stackexchange.com/help/licensing — Stack Exchange network licensing and revision-specific licence guidance
[3] https://github.com/Kaggle/kaggle-cli/blob/main/skills/references/benchmarks.md — Kaggle CLI benchmark workflow
[4] https://dev.to/challenges/kaggle-2026-09-23 — Kaggle Benchmarks Challenge
[5] https://universalcefr.github.io — UniversalCEFR data directory and licences
