# DEVLOG — CEFR-adherence benchmark

Append-only development log. Seed entries `S01`–`S17` (pre-handover decisions) go at the top once provided; entries `E001` onward are logged at the time of the event. Never edit or delete an earlier entry; supersede with a new entry that names the old one.

---

## E001 · 2026-10-07 16:05 · decision
**Type:** decision
**What:** Project bootstrapped at `~/Projects/cefr-adherence-benchmark` (git initialized). Downloaded CEFR-J Vocabulary Profile v1.5 (7,799 rows), Octanove C1/C2 vocabulary (2,137 rows), CEFR-J Grammar Profile 20180315 (500 rows) from openlanguageprofiles/olp-en-cefrj, plus the Kaggle `write-kaggle-benchmarks` skill doc. Local venv with `kaggle-benchmarks` + pandas installing for offline task validation.
**Why:** Zero-regret groundwork — all inputs are openly licensed and required under every branch of the plan.
**Alternatives considered:** waiting for answers; rejected because list downloads and repo scaffold are needed regardless.
**Learner relevance:** none directly; enables everything else.
**Status:** active
**Story value:** low

## E002 · 2026-10-07 16:07 · surprise
**Type:** surprise
**What:** The DEV challenge page scrape reads "Challenge Status: Live Ended". Verified against the live HTML: the status pill is Alpine.js — both the "Live" and "Ended" spans exist in static HTML and are toggled client-side by an `ended` flag, so scrapers flatten both. Page copy says "Running through October 11"; today is October 7. Challenge is LIVE, deadline 2026-10-11 23:59 PDT (~4.5 days).
**Why:** An "ended" reading would have killed the project; worth logging the artifact.
**Alternatives considered:** none.
**Learner relevance:** none.
**Status:** active
**Story value:** low

## E003 · 2026-10-07 16:10 · decision
**Type:** decision
**What:** Kaggle plan anchored on the CLI workflow from the official skill: `kaggle b init` (fetches Model Proxy creds + writes `.env` with `LLM_DEFAULT`/`LLMS_AVAILABLE`) → validate task locally with `python task.py` → `kaggle b t push -f task.py` → `kaggle b t run -m <model>` → `kaggle b t download`. Key gotchas recorded: every task must end with `.run()`/`.evaluate()` or the push silently no-ops; `-> float` return annotation required for leaderboard scoring; repeat `-m` per model; re-push must repeat `-d` dataset flags.
**Why:** The brief's "first-hour checks" (pip install, internet, response extraction) are answered by validating locally before pushing; the skill documents the entire path.
**Alternatives considered:** building blind in the Kaggle notebook UI; rejected — local validation catches failures before the push→run→wait round-trip.
**Learner relevance:** none directly.
**Status:** active
**Story value:** medium

## E004 · 2026-10-07 18:15 · result
**Type:** result (calibration v1)
**What:** Calibration run on UniversalCEFR English subsets (cambridge_exams, cefr-sp, icle500, elg-cefr-en, cefr-asag; ~12.7k texts → ~900 windows, 3-5 sentences each). Final thresholds after joint-pass loosening: A1 caps 13.6%/14.2%, B1 5.5%/9.9%, C1 1.4%/13.5%; B1 floor 6.25% share. Joint ceiling pass ≥90% at all levels (loosen ×1.22-1.34).
**Why:** brief §Calibration steps 2-5. Starting values (5%/1%) were 3-13x below measured p90s — genuine texts carry far more above-level and unlisted vocab than the reference values assumed.
**Alternatives considered:** keeping reference caps (would fail 20% of genuine texts); rejected.
**Learner relevance:** a tutor reply that stays within caps calibrated on real graded texts is "as level-appropriate as a real textbook passage", not an abstract ideal.
**Replaces / related:** S-none; related E0xx later for final config write
**Status:** active
**Story value:** high

## E005 · 2026-10-07 18:15 · surprise
**Type:** surprise
**What:** The C1 floor is vacuous: p10 of B2+C1-band share in genuine C1 texts is 0.0 (median 4%). Genuine C1 writing is ~80% A1 vocabulary; almost nothing sits in the B2/C1 lists. So at C1 the scorer is effectively a ceiling test, and the floor cannot separate B1 from C1 (null).
**Why:** distribution data in results/calibration_windows_v1.jsonl.
**Alternatives considered:** forcing a nonzero floor (would fail genuine C1 texts); rejected — reported honestly instead.
**Learner relevance:** "write at C1" is not about using C1 words everywhere; it's about NOT slipping below B2 competence. Advanced vocab is a seasoning, not the dish.
**Status:** active
**Story value:** high

## E006 · 2026-10-07 18:15 · dead-end
**Type:** dead-end
**What:** Grammar-floor at p10 = 0.0 at every level (regex detectors fire too sparsely on 3-5-sentence windows). Grammar floors dropped (recorded as None); grammar still scored via ceiling and the grammar dimension remains in the combined score.
**Why:** p10=0 means 10%+ of genuine windows have zero in-band grammar hits — a nonzero threshold would fail them.
**Alternatives considered:** expanding detectors before calibration; deferred (improvement over adding components, per Agent latitude).
**Learner relevance:** grammar presence is lumpy at short lengths; a 3-5 sentence reply can be perfectly level-appropriate without hitting a specific pattern.
**Status:** active
**Story value:** medium

## E007 · 2026-10-07 18:40 · decision
**Type:** decision (deviation from brief)
**What:** 30 items selected from English Language Learners StackExchange (CC BY-SA 4.0, keyless API, 500-question pool; deterministic filter: 40-320 chars, no site-meta, seeded shuffle; 24 everyday + 6 trap via domain-keyword heuristic). data/items.json carries per-item provenance (question_id, link, license).
**Why:** user requirement: items must come from real human datasets, not AI-generated. The brief's "own items" (introductions/food/directions) would have been hand-written; ELL is the best open real-learner source (verified vs Tatoeba/DailyDialog/TOEFL11/NUCLE/EFCAMDAT — see data/raw/item_source_research.md).
**Consequence (disclosed):** items are usage questions ("in or for?", "Alex's vs Alex'?") not small-talk scenarios, so the task measures "can the model explain at the learner's level" — a tutor-authentic task. Traps = domain questions (back-end developer, COVID vaccine tweet, courtroom "hearing") that invite jargon.
**Alternatives considered:** Tatoeba (native, not learner); DailyDialog (native, tokenized, NC); writing items ourselves (violates user requirement).
**Learner relevance:** maximal — these are actual questions real learners asked.
**Status:** active
**Story value:** high

## E008 · 2026-10-07 19:05 · audit
**Type:** audit
**What:** Golden set v1: 30 snippets (10/level, 5 compliant + 5 planted violations) — scorer classifies 30/30 adherent-correct; meta-talk items verified as flagged (flag, not gate-fail, per brief). Gate tests (empty/1-sentence/non-English/irrelevant -> 0) pass. pytest 3/3.
**Why:** brief §Validation 1.
**Fixes triggered:** (a) contraction clitic 's counted as unlisted token -> dropped from content; (b) slash headwords (favorite/favourite) were skipped -> now split+indexed (favourite went from unlisted to A1); (c) C1 cap1 (1.39%) was sub-token -> brief's minimum-one-token rule applied to caps AND floors (C1 floor: >=1 B2/C1-band token); (d) adherent flag now includes floor satisfaction.
**Status:** active
**Story value:** medium

## E009 · 2026-10-07 19:05 · audit
**Type:** audit
**What:** Flag-precision audit v2: 60 flagged tokens, 59 real violations, 1 artifact (1.7%). Earlier run showed 16.7% artifacts -> fixes: slash-variant headwords, UK/US whitelist, suffix-stem fallback in level_of. Stem-resolvable flags are REAL when the stem itself is above target (e.g. 'employment' -> 'employ' B2 at target B1). results/flag_audit.json
**Why:** brief §Validation 2 (~40 flags hand-checked).
**Status:** active
**Story value:** medium

## E010 · 2026-10-07 19:05 · surprise
**Type:** surprise
**What:** Monotonicity holds for LISTED vocabulary (C2-rate at target C1: A1 texts 0.0000 < B1 0.0002 < C1 0.0019) but fails on unlisted share at C1 (A1 3.5% > B1 2.4%): genuine A1 graded readers contain MORE unlisted tokens than B1 essays (character names, animal words like 'otter' that CEFR-J simply doesn't list). Reported as disclosed limitation; unlisted-share is a noisy signal at short lengths.
**Why:** results/monotonicity.json + listed-only breakdown.
**Learner relevance:** 'unlisted' does not mean 'too hard' — lists are incomplete at the edges; that's why caps are calibrated, not assumed.
**Status:** active
**Story value:** high

## E011 · 2026-10-07 19:45 · result
**Type:** result
**What:** All builds complete for the local phase. (1) Self-contained Kaggle task `kaggle_task/cefr_task.py` + `cefr_scorer_embedded.py` (181 KB, gzipped base64 lists; identical scorer verified vs src: B1-good 1.0/True, A1-trap 0.533/False; both compile; judge gate + 6-probe judge validation included; 180-row eval grid built-in). (2) OpenRouter harness (resumable, $15 cap, est. $7.81 for 10 models x 180 prompts; context-overflow logged separately; temp 0.2). (3) Analysis + sensitivity scripts. (4) Prompt-size report: informed A1 2.2k / B1 9.8k / C1 18.4k tokens (bare 72); word lists A1 1,055 / B1 4,375 / C1 7,723 cumulative headwords.
**Why:** brief §first-hour checks and §Model testing.
**Status:** active
**Story value:** medium

## E012 · 2026-10-07 19:45 · decision
**Type:** decision
**What:** Bare prompt kept EXACTLY as the brief specifies ("Reply to this learner at CEFR level X." — no sentence-count hint; the 3-5 sentence instruction lives in the informed condition's rules and the scorer's syntax bands). Embedded scorer floors use calibrated values; C1 minimum-token floor (>=1 B2/C1 token) is in both scorer and informed prompts.
**Why:** earlier draft leaked a "Write 3 to 5 sentences" line into the bare prompt — caught during task-file review.
**Status:** active
**Story value:** low

## E013 · 2026-10-07 19:55 · audit
**Type:** audit (task wiring, real SDK)
**What:** Ran kaggle_task/cefr_task.py end-to-end against the installed kaggle-benchmarks 0.6.1 with a mock LLM: 8/8 runs, correct per-level scores, provenance columns in results. Three bugs found+fixed: (1) evaluate() passes ALL DataFrame columns as kwargs -> item_id added to task signature; (2) assess_response_with_judge criteria must be a LIST (a string got char-enumerated into 110 garbage criteria items); (3) doubled-brace template artifacts -> generator now un-escapes. Also verified: judge kwargs, kbench.judge_llm, on_failure/max_attempts all match the installed API.
**Why:** docs-vs-installed drift is the top push-failure risk; verified before any credential is involved.
**Status:** active
**Story value:** low

## E014 · 2026-10-08 · relevance-gate regression repair
**Type:** fix and verification
**What:** Fixed the canonical generator and generated Kaggle task: judge now receives learner message plus reply in JSON-bound data, reads `AssessReport.results[0].passed`, and treats missing/malformed reports or SDK-swallowed provider failures (`None`) as unscored errors. Genuine irrelevance scores zero. Replaced context-free probes with eight matched/mismatched question/reply cases; disagreement or errors block the sweep. Tests exercise generated production functions through the installed SDK, including evaluation completed/errored separation and a real temporary run JSON artifact. Added 11 relevance regression/integration tests alongside the 3 existing scorer tests. Local fixtures do not prove live judge agreement.
**RED evidence:** the original task awarded an explicitly irrelevant SDK verdict 0.9785 instead of zero; missing helper/error handling and context-free validation also failed the new acceptance tests.
**Verification:** `env -u PYTHONPATH .venv/bin/python -m pytest tests -q`; `git diff --check`. pytest was installed into the project venv with uv; host Python 3.9 plus inherited PYTHONPATH was incompatible. Generator-only blob churn was discarded after confirming decompressed payload and non-blob AST were identical, preserving the existing scorer/data unchanged.
**Remaining before paid comparisons:** current OpenRouter harness has no relevance judge (not gate-equivalent); integrate the same policy, validate live-judge agreement, exclude/replace image-dependent e03, and restore title context for e05/t06. Everyday/trap keyword labels remain heuristic. No paid calls, publication, commit, or push performed. A run JSON artifact does not itself carry input provenance; retain the evaluation-grid/run-ID mapping for offline analysis.
**Status:** local fix verified; live-provider/data-preflight gates pending
**Story value:** medium


## E015 · 2026-10-08 · cleaned, frozen local-first Qwen pilot

**Scope:** owner-selected Qwen3.5-2B/9B local, Qwen3.8-27B/Flash API later; no paid calls.
**Data:** 30 real ELL questions with original titles/full normalized bodies. Replaced one image-dependent item and three API-license-unreported items using recorded human-source candidates (seed 42). Per-item author, license 3.0/4.0, URLs, raw hashes and modifications are recorded. Dataset SHA-256: 02057556dd4bff7154911f84b50169641b17dcd8bceca50c832741e40d4c1501.
**Runtime:** verified stock community MLX 4-bit revisions/shard hashes; mlx-lm 0.31.3, mlx 0.31.2. Host HF cache because the Seagate drive is not mounted. Sequential runner, identity-checked JSONL resume, per-row fsync, resource caps/watchdog, no silent prompt truncation. Both six-row real smoke tests passed, including full C1 prompts (17,906 tokens on first question); observed peak 1.95/6.38 GB. Truncated generations are preserved with finish_reason=length.
**Scoring correction:** C1 one-word design floor moved to diagnostics; primary C1 ceilings do not establish full C1 proficiency. Four previously failing under-level golden fixtures now intentionally document that blind spot; this is not claimed as restored 30/30 CEFR classification accuracy. Shared informed prompts and context-bound relevance prompt/probes are tested against the embedded task. Generation final scores/relevance stay null; a separate fixed-route, budget-gated live judge still needs validation.
**Verification:** 27 tests passed, 5 SDK subtests passed, compileall and diff whitespace checks clean (one existing generator escape warning). Full controller started and real progress beyond smoke verified; generation is running, not complete. PID/status/logs belong to cefr-adherence-benchmark. API comparison/model routing and paid judge remain deferred.

## E016 · 2026-10-08 · accepted C1 evaluation change

**Type:** learning and owner-approved decision
**Evidence:** All 360 frozen local replies have relevance-gated scores (`results/qwen_local_subscription_v4/verification.json`). Relevance is not teaching correctness or CEFR proficiency. Re-scoring the five compliant A1 golden fixtures at C1 labelled all five adherent (combined scores 0.9232–0.9568). These are authored regression controls, not independent expert labels.
**Learning:** Ceiling compliance is not evidence of demonstrated C1 proficiency. A simple short answer can be appropriate for a C1 learner without demonstrating C1 range; requested learner level, response difficulty and demonstrated proficiency are distinct constructs.
**Accepted rules:** Preserve existing results. Add a separate descriptor-based C1 assessment for grammatical range/control, precision, coherence and appropriate register. Allow “insufficient evidence.” Do not enforce advanced-word quotas or reward jargon, verbosity or length. Keep relevance, CEFR ceiling compliance, demonstrated C1 and factual/teaching correctness separate.
**Execution order:** Validate the candidate evaluator using below-level controls and held-out expert-labelled B2/C1/C2 texts, with provenance, licensing, calibration/source/participant overlap and domain shift checked. Missing C2 or independent labels remain explicit limitations. Then assess saved replies with their paired A1/B1 counterparts as controls before API-model expansion. A diagnostic pilot must not be described as a validated C1 certification.
**Source:** Council of Europe, CEFR Companion Volume, chapter 5: https://rm.coe.int/chapter-5-communicative-language-competences/1680a084c3; ledger `results/c1_eval_sources.json`.
**Supersedes / clarifies:** E005/E008/E012/E015: the C1 minimum-token floor remains diagnostic only; historical 30/30 golden accuracy is not evidence of current C1 separation. E015's generation/judging-pending status is historical; local scoring is complete.
**Status:** owner approved saving these rules and running evaluations; replacement evaluator implementation and independent validation not yet complete at this entry.
**Story value:** high — test the evaluator, not only the models.

## E017 · 2026-10-08 · C1 descriptor pilot failed; full re-evaluation blocked

**Type:** executed diagnostic, negative result and validation stop
**What was built/run:** Separate `c1_descriptor.py` rubric/parser and `eval_c1_descriptor.py` subscription runner; whole-text exact evidence quotes, blinded model/target metadata, insufficient-evidence band, fixed pilot gates and no changes to original scores. All five authored A1 controls were classified below B2 in a live preflight. The labelled pilot used 12 whole ICLE500 essays at each of B2/C1/C2, plus the five A1 negatives (41 judgments), selected with seed 42 before seeing descriptor outcomes.
**Result:** Corpus B2 → 4 below B2 / 8 B2; corpus C1 → 12 B2; corpus C2 → 11 B2 / 1 C1. Binary sensitivity to corpus-labelled C1-or-higher was 1/24 (4.17%; Wilson 95% interval 0.74–20.24%); specificity 12/12 (100%; interval 75.75–100%); no abstentions or authored-negative C1 false positives. The pre-specified 80% sensitivity/specificity gate failed. No descriptor sweep of the 360 model replies was started. Do not tune on these cases and then claim the same set is held out.
**Corpus caveats:** UniversalCEFR records/directory identify ICLE500 as manual expert-rated, CC0, and report Rasch kappa -0.02. The source was also used in old ceiling calibration. Parent exclusion was reconstructed with old/new splitters, but original lexical calibration measurements did not reproduce; original parent-ID/hash receipts and participant metadata are absent. Thus this is a provisional reconstructed-document pilot, NOT verified source/participant-disjoint validation. The failure establishes disagreement with these noisy labels, not that either corpus labels or judge decisions are definitively correct.
**Access/privacy:** Cambridge Write & Improve 2024 has examiner-assigned final-text labels but requires registration/license acceptance and restricts commercial LLM processing to no-training-retention routes; no corpus download, registration or transfer was performed. Do not silently send it through a consumer subscription judge.
**Verification:** `verify_c1_descriptor.py --out-dir results/c1_descriptor_diagnostic_v1` verified 41 unique assessments, source text/label identity, exact evidence quotations, frozen input/code hashes, subscription provider/model and no-tool sessions. `pytest tests -q`: 64 passed, 5 SDK subtests passed; compileall and whitespace checks clean. Subscription quota only; no metered API model runs, publication, commit or push.
**Artifacts:** `configs/C1_EVAL_PROTOCOL.md`, `data/c1_descriptor_controls_v1.json`, `results/c1_descriptor_diagnostic_v1/{validation.jsonl,validation_metrics.json,validation_confusion.csv,verification.json,REPORT.md}`. Original local results remain in `results/qwen_local_subscription_v4/`.
**Learning:** Passing easy negative controls is not evaluator validity. Check positive sensitivity, per-level confusion, abstentions, label reliability and overlap; preflight/protocol execution verification is not linguistic validity.
**Clarification of historical calibration counts:** Saved artifacts contain 2,113 windows across six levels, of which 913 are at the three scored targets A1/B1/C1, from 11,841 downloaded raw records. Earlier “~900 windows” referred approximately to target-level windows, not the full stored calibration file.
**Status:** accepted rules saved and evaluation pilot executed/verified; replacement C1 evaluator NOT cleared. Model-response descriptor re-scoring and API-model expansion remain blocked on a reliable validation route.
**Story value:** high — an honest failed evaluator beats a polished but invalid leaderboard.

## E018 · 2026-10-08 · ReadMe++ source lead verified; not production-proficiency gold

**Type:** primary-source verification of delegated research
**Verified artifact:** `/tmp/readme_en.json`, SHA-256 `6c5cb5608b5379115c911a5dfbbbc458556b03014287863088885e918185af89`, 2,822 English sentence-level reference records; B2 896 / C1 377 / C2 71. All converted records carry `CC BY SA NC 4.0`; dataset card specifies CC BY-NC-SA 4.0. This named subset is not one of the five calibration inputs.
**Primary evidence:** Naous et al., EMNLP 2024, https://aclanthology.org/2024.emnlp-main.682.pdf (§3.2): labels are sentence reading/comprehension difficulty, not learner production proficiency. An author annotation set plus two additional CEFR-trained language-speaking/annotation-experienced annotators per language; final rating by majority vote. English Krippendorff alpha 0.78 and Pearson 0.81. This corrects the delegated report's shorthand of “two experts” and range-level agreement. The paper's authors/annotator selection description is not evidence of CEFR examiner certification.
**Limits and corrections:** Different named corpus is not proof of original-source or participant independence; several upstream domains overlap (e.g. Wikipedia). The UniversalCEFR conversion drops original domain/context/source metadata, so original-source exclusion needs the primary release. Single-sentence readability gold cannot certify demonstrated advanced production or coherent tutor discourse; complex domain terminology can increase reading difficulty without advanced grammatical range. Keep it as a separate readability diagnostic, not a replacement validation gate for the descriptor scorer. CC BY-NC-SA permits licensed noncommercial sharing with attribution/share-alike; it is not a blanket redistribution ban. However the primary release includes source-specific terms and explicitly permission-gates clinical reports, so raw text redistribution or clinical-source use requires its own review. The repository's MIT software license is not the dataset license.
**Decision:** no additional judging, no promotion of the failed C1 descriptor evaluator, and no model-response re-scoring based solely on this lead. Earlier execution findings and blocked status remain unchanged. Source is usable for a future explicitly separate reading-difficulty diagnostic after original-source/rights checks.
**Story value:** medium — a labelled dataset is only useful when it measures the intended construct.

## E019 · 2026-10-08 · Owner accepted multi-scale tutor-adherence assessment

**Type:** approved evaluation design; not an implementation or validation claim
**Primary outcome:** whole-reply suitability/accessibility for the requested learner level, rather than requiring every sentence or reply to demonstrate production at that exact level. Clear simpler language can be appropriate for an advanced learner.
**Assessment units:** contextual individual-sentence diagnostics for local vocabulary/syntax difficulty; contiguous passage diagnostics for cumulative difficulty and connections between ideas; whole-reply assessment for accessibility, organisation and register. Preserve local above-level breaches so an aggregate mean cannot hide a difficult sentence. Demonstrated grammatical range/C1 production remains a separate optional descriptor diagnostic with insufficient-evidence abstention; relevance and teaching correctness remain separate axes.
**Validation rule:** sentence labels apply to their labelled target, even when surrounding context is supplied. Do not inherit labels for surrounding passages or concatenate unrelated labelled sentences into synthetic gold passages. Passage-level validity requires labels for the actual contiguous passages. Increasing span alone cannot explain or repair E017, which already judged whole essays; the original ceiling scorer already operates on whole replies.
**Execution boundary:** existing scores, frozen pilot protocol and failed-pilot evidence remain unchanged. No new judge/model run or code change is claimed by this design approval. The multi-scale assessment needs implementation and separate validation before replacing reported benchmark outcomes.
**Story value:** high — match the assessment unit and construct to the actual tutoring task.

## E020 · 2026-10-08 · C1 ceiling-off experiment: passes still happen; separation collapses

**Type:** executed diagnostic (corpus windows + frozen 360 replies), TDD-first
**What ran:** `src/cefr_bench/c1_ceiling_off.py` + `scripts/analyze_c1_ceiling_off.py` → `results/c1_ceiling_off_v1/` (9 new tests; suite 73 passed + 5 subtests). Only the C1 vocab ceiling is lifted (caps→1e9); grammar ceiling (C1: 0 above-level hits), floors and syntax unchanged. Frozen v4 outputs untouched; relevance labels reused.
**Corpus windows scored at the C1 target (joint-pass rate, ceiling-on → off):** A1 25/113 (22.1%) → 65/113 (57.5%); A2 146/400 (36.5%) → 182 (45.5%); B1 179/400 (44.8%) → 239 (59.8%); B2 375/400 (93.8%) → 400 (100%); C1 375/400 (93.8%) → 400 (100%); C2 398/400 (99.5%) → 400 (100%). The A1-vs-C1 pass gap shrinks from ~71.7pp to ~42.5pp: the vocab ceiling was the strongest remaining separator; the grammar ceiling alone cannot discriminate.
**LLM replies (C1 cells):** essentially unchanged — 2B bare 0.9663→0.9663, informed 0.9309→0.9320; 9B bare 1.0→1.0, informed 0.9954→0.9985; adherent 117/120→119/120 (both gains = e07:C1:informed on each model, pure vocab-ceiling misses). Models almost never trip the C1 ceiling on tutor replies.
**Conclusion:** passes still happen without the ceiling — more of them, including far more below-level corpus text. Ceiling-off makes C1 strictly weaker, not stronger. Recommendation: KEEP the C1 vocab ceiling (it is the main discrimination signal at C1) and report C1 as saturated-by-design for strong models; the "easy target" phenomenon is genuine but not caused by the ceiling.
**Side-finding (scorer drift):** comparing v4-embedded stored scores vs current `src` scorer on identical A1/B1 replies shows semantic divergence unrelated to ceiling-off: 21/240 non-C1 replies differ; 2 B1-informed material (e07 0.2→0.575, e19 0.5989→0.8898). Embedded zeroes the vocab dimension on B1 floor-miss; `src` gives partial credit (`floor_share/threshold`, 0.7273 for e19). The verbatim-embed guarantee covered `tokenise.py` only — scorer semantics were never parity-asserted. Follow-up needed before any Kaggle publication claim of single-source-of-truth scoring.
**Verification:** pytest 73 passed + 5 subtests; manifest hashes pinned (`windows 3617d975…`, `scored 397e9187…`); analysis is read-only over frozen artifacts.

## E021 · 2026-10-09 · parity-fixed v5 rescore completed

**Type:** scorer repair, frozen-output rescore and evidence seal
**What:** Restored embedded/canonical scorer parity without regenerating model replies or relevance verdicts. The v5 export now tolerates the intentionally sparse score shape emitted by structural gate failures (`vocab` is absent there) and records that field as null. Added a regression test. Rescored all 360 frozen replies and wrote `results/qwen_local_benchmark_v5/{scored.jsonl,summary.csv,REPORT.md,verification.json}`.
**Result:** overall mean 0.8890→0.8908; 22/360 combined scores changed; maximum absolute per-reply correction 0.3750. Qwen3.5-2B-4bit mean 0.8321 with 113/180 relevant+adherent; Qwen3.5-9B-4bit mean 0.9495 with 148/180. The v4 source and relevance labels remain unchanged.
**Verification:** 360 rows, 360 unique `(model,key)` identities, 12 complete 30-row cells, one sparse gate-failure record, and SHA-256 seals for source scorer, input and three output artifacts.
**Status:** complete; v5 supersedes v4 only for deterministic CEFR scoring.
**Story value:** medium — small implementation drift changed some scores, so the publication reports the correction instead of hiding it.

## E022 · 2026-10-09 · Kaggle publication candidate prepared

**Type:** packaging, attribution and release preparation
**What:** Rebuilt `kaggle_task/cefr_task.py` as the actual single file accepted by `kaggle b t push -f`. It now embeds the scorer/data module and visible licence/attribution Markdown rather than importing a sibling. Added an isolated-file execution regression test. Installed Kaggle CLI 2.2.4 in `.venv`, pinned local requirements, added AGPL-3.0-only for original code, and generated a 30-item author/source/licence table in `THIRD_PARTY_NOTICES.md`.
**Artifact curation:** deleted the tracked stale fail-open `.task.json` and ten old local `.run.json` files; `.gitignore` now excludes regenerated task/run metadata and raw request directories. The context-bound Kaggle relevance judge remains the primary binary gate. The failed C1 descriptor judge is documented only as an optional, unvalidated research extension.
**Publication material:** rewrote `README.md`, replaced stale story notes, drafted `DEV_SUBMISSION_DRAFT.md`, and rendered/visually inspected `assets/cefr-adherence-cover.png` (1200×630). The draft clearly separates frozen local evidence from the still-missing live Kaggle table.
**Verification:** generated task hash `f1fe809f…`; embedded scorer hash `c0e517a8…`; two consecutive generations were byte-identical. Full suite: 82 passed + 5 SDK subtests. Isolated task execution, compileall, dependency consistency, v5 evidence seal, citation ledger, and `git diff --check` passed.
**Still manual:** Kaggle authentication, quota/model catalogue review, push, live runs, download/log inspection, task publication, benchmark-collection creation, public repository URL, cover upload and DEV publication. No Kaggle credentials, paid API calls, remote writes, commit, push or publication occurred.
**Status:** local publication candidate complete; live Kaggle/DEV steps pending owner accounts.
**Story value:** high — the upload artifact is now reproducible, inspectable and legally attributed.

## E023 · 2026-10-09 · Kaggle push blocked by server-side source-kernel creation

**Type:** live platform qualification and bounded recovery
**What happened:** Authenticated model discovery succeeded, but every `kaggle b t push` returned `An error occurred while saving the entity changes`. Kaggle created a private task entity with `creationState=UNSPECIFIED`, `sourceKernelId=null`, `source=UNSPECIFIED`, and no backing notebook. Re-pushing the same slug then failed with `exists but has no source kernel`. The same server error reproduced with a 247-byte minimal task, proving the blocker is not the benchmark source, embedded data, task size, or task code.
**Bounded fixes before isolation:** Removed database-hostile generated lines (largest fell from 120,832 to 211 characters), moved items/prompts/detectors/thresholds into the compressed payload, and changed the payload from gzip to LZMA. The final Python artifact is 179,398 bytes and its converted notebook is 201,989 bytes. Added a max-line regression gate.
**Server evidence:** Four private orphan entities are visible under the owner account, all `Unspecified`: `cefr-adherence`, `cefr-tutor-adherence`, `cefr-level-adherence`, and the minimal `cefr-kbench-smoke`. CLI delete is present but explicitly prints that server-side delete is unsupported. No model run or inference spend occurred.
**Current local verification:** final task SHA-256 `b32f17c7…`; embedded scorer SHA-256 `39b73078…`; two generations byte-identical; 83 tests + 5 SDK subtests passed; v5 outputs unchanged at 0.8908 overall; compileall and whitespace checks passed.
**Manual recovery:** Open Kaggle Benchmarks in the authenticated web UI, complete/accept any early-access onboarding, and remove or repair the four `Unspecified` tasks if the UI permits. Create one starter task from `https://www.kaggle.com/benchmarks/tasks/new` so the account has a backing source kernel, then retry the CLI push with a fresh final slug. If the web UI cannot create a task, report the task URLs and server message to Kaggle support; further CLI retries only create more orphans.
**Status:** local candidate remains green; Kaggle platform/account source-kernel creation is the only push blocker.
**Story value:** low for the article, high for release truth.

**UI correction:** The owner task-list URL printed by Kaggle CLI 2.2.4 (`/benchmarks/tasks/<owner>/`) is not a working routed page and shows “We can't find this page.” The browser recovery path is to sign into kaggle.com as the CLI account and open `/benchmarks/tasks/new` directly. Orphan visibility remains CLI-only unless an individual task route becomes usable.

## E024 · 2026-10-10 · Kaggle versions 1–4 audited; 2,048-token candidate prepared

**Type:** live platform execution, negative-result preservation, and release hardening
**Version chain:** v1 failed before evaluation because SDK 0.6.1 requires `llm=[kbench.llm]`; v2 completed but hidden reasoning starved 179/180 outputs at a 512-token cap; v3 added `reasoning="none"` and reached mean 0.9284, yet 31/180 answers visibly truncated because Gemini 3.7 Flash does not support thinking-off; v4 used supported `reasoning="low"` with a 1,024-token combined allowance.
**Version-4 result:** Kaggle reported Completed. Independent download audit found 180/180 completed rows, 180/180 local score parity, mean 0.9679, 180/180 relevance, and 153/180 relevant-plus-adherent. Artifact-accounted cost was $0.991827825; cumulative quota after the run and bounded probes was $3.039692625 under the owner-authorized $4 version-4 ceiling.
**Publication verdict:** REJECTED. Manual inspection of every cap-pressure answer found 14/180 ending mid-sentence at 1,020 output tokens. Platform completion and score parity do not make truncated generations valid evidence. Receipt: `results/kaggle_live_v4/{verification.json,manual_review.json,REPORT.md}`.
**Next candidate:** canonical source and regression tests now require Gemini `reasoning="low"` with a 2,048-token combined allowance. The generated standalone task also embeds a visible 30-item author/source/revision-licence table and AGPL URL. Full local suite: 85 tests + 5 SDK subtests passed before the attribution addition; final release gates must be rerun after all audit fixes. No version 5 was pushed and no second model was started.
**Release hygiene:** licensing-incomplete ELL research pools, UniversalCEFR learner texts, machine-bound subscription traces, and C1 control texts remain local and ignored. Public evidence retains final attributed items, hashes, aggregate metrics, portable v5 local results, and a compact C1 failure summary.
**Status:** version 4 preserved as invalid negative evidence; version 5 locally prepared but blocked on separate paid-run authorization.
**Story value:** high — the release distinguishes green infrastructure from valid evaluation and removes unnecessary personal/licensing-sensitive source text.

## E025 · 2026-10-10 · Kaggle version 5 passes release gates

**Type:** final live evaluation and independent publication qualification
**Candidate identity:** `kaggle_task/cefr_task.py` SHA-256 `4466d17236635941357937a9813a0ae371495381b5cd844d1d365e488a2e189d`; Gemini 3.7 Flash; temperature 0.7; top-p 0.8; supported low reasoning; 2,048-token combined reasoning-and-answer allowance; one attempt per row.
**Platform result:** version 5 completed privately under the stable `cefr-adherence-benchmark` slug. Run ID 4621190. Final cumulative quota was $4.056429375; version-5 delta was $1.016736750.
**Independent verifier:** 180/180 rows and IDs complete; 180/180 completed states; 180/180 score parity; 180/180 relevant; 154/180 relevant and adherent; mean 0.9612; zero scores 0; near-cap outputs 0; verification errors 0; exact local/remote task identity matched.
**Manual integrity review:** all 180 visible endings reviewed. Twenty-five conservative heuristic flags were checked and found to be Markdown/quotation/emoji false positives. Visibly truncated answers: 0/180. Receipts: `results/kaggle_live_v5/{verification.json,manual_review.json,ending_review.txt,REPORT.md}`.
**Publication verdict:** PASS. Version 5 may replace rejected version 4 as the release candidate. Task, collection, source repository, and DEV article still require publication/read-back.
**Story value:** high — a doubled combined allowance eliminated visible truncation without changing the scorer, row set, or one-attempt policy.
