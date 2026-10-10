# C1 descriptor diagnostic — frozen pilot protocol v1

This is a separate experimental text-level assessment, not a replacement for the existing ceiling scores and not CEFR certification. The owner accepted this change (DEVLOG E016).

## Construct and rubric

- Adapted from Council of Europe CEFR Companion Volume (2020), chapter 5: grammatical range/control, precision, coherence and appropriate register.
- Holistic observed-text bands: below B2, B2, C1, C2, or insufficient evidence. C1/C2 count as demonstrated C1-or-higher in this diagnostic, not proof of precisely C1-target matching.
- A concise simple reply may be appropriate for an advanced learner without demonstrating advanced range. No minimum-word quota, rare-word quota, automatic verbosity/formality reward or jargon bonus.
- Exact text quotations ground every accepted judgment; quotation validation proves grounding, not correct CEFR classification. Confidence values are judge self-reports, not calibrated probabilities.
- Requested level and model identity are blinded. The learner question is context only for register/precision. Relevance and factual/teaching correctness are separate axes.

## Validation gates specified before labelled-corpus results

- Minimum 10 below-C1 labelled texts and 10 C1-or-higher labelled texts.
- Binary sensitivity and specificity at least 0.80, with abstentions kept in the denominators; overall abstention at most 0.20.
- No C1/C2 false positives among the five authored compliant A1 golden negative controls.
- These are engineering pilot gates, not statistically justified certification thresholds. Small sample sizes and confidence intervals must be disclosed; passing does not establish independent human agreement or corpus-to-tutor transfer.
- Prefer source/participant-disjoint, expert-labelled B2/C1/C2 material. Record missing levels, author/text label distinctions, licenses, independence evidence and retrieval hashes. Do not invent C2 labels or treat course-level labels as expert ratings.
- The saved-answer sweep is blocked if the combined pilot gate fails. Preserve the failure and do not tune to this test set then relabel it held-out. Missing source/participant proof means results remain provisional, not fully validated.

## Execution

`src/cefr_bench/c1_descriptor.py` owns the rubric/parser/metrics. `scripts/eval_c1_descriptor.py` runs controls first, then the 360 frozen saved replies if the pilot gate passes. Every requested-level arm is assessed under the same rubric, so A1/B1 replies serve as same-question counterfactual controls, not expert-labelled negative examples.

Subscription only: pinned GPT-6.1-sol/openai-codex; safe mode; no tools; no provider fallback; two concurrent calls maximum; three texts per batch; one retry only for malformed or ungrounded JSON. Raw request/response logs, input/code hashes and provider/no-tool session verification are retained. No new model generation and no metered API candidate runs in this phase. Previous score files remain untouched.

## Known risks

Essay/readability corpora differ from short tutor responses; categorical proficiency labels may describe whole texts, authors or reading difficulty. Expert-rating evidence must be stated precisely. Correlated replies, one generation per arm, output-cap truncation, single-judge bias, batch effects and insufficient-evidence rates limit interpretation. Advanced-sounding but incorrect explanations can still receive high language-range judgments: teaching accuracy is not measured here.

Source: <https://rm.coe.int/chapter-5-communicative-language-competences/1680a084c3>.
