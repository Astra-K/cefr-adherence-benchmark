# Data sources & licenses

| File | Source | License | Use |
| --- | --- | --- | --- |
| `cefrj-vocabulary-profile-1.5.csv` | [openlanguageprofiles/olp-en-cefrj](https://github.com/openlanguageprofiles/olp-en-cefrj) (CEFR-J Vocabulary Profile v1.5) | Free for research and commercial use with citation; © Tono Laboratory, TUFS | A1–B2 word levels |
| `octanove-vocabulary-profile-c1c2-1.0.csv` | same repository (Octanove Vocabulary Profile 1.0) | CC BY-SA 4.0 | C1/C2 word levels — check share-alike before redistributing derived lists |
| `cefrj-grammar-profile-20180315.csv` | same repository (CEFR-J Grammar Profile 20180315) | Same as CEFR-J (Tono Lab, TUFS; cite) | Seed for grammar detectors; partly untranslated from Japanese |

Notes:
- CEFR-J is a Japan-localised CEFR — disclosed in the DEV post.
- Sublevels are collapsed into A1/A2/B1/B2 (CEFR-J uses e.g. A1.1, A1.2).
- Calibration thresholds were derived from frozen UniversalCEFR English subsets. The raw texts are intentionally excluded from the public repository because four subsets are CC BY-NC-SA 4.0 and may contain personal learner narratives; `icle500` is CC0 1.0. Published calibration artifacts retain source identities, hashes, aggregate statistics, and licence metadata. The generated Kaggle task contains aggregate thresholds only. Directory, original-paper links, and licence table: https://universalcefr.github.io/


## Frozen ELL question snapshots (local evidence only)

The full Stack Exchange API snapshots and 500-question research pool remain in a local, ignored evidence archive and are not redistributed. The public `../items.json` contains only the 30 benchmark adaptations and carries per-question author/name/link, original title, normalized original body, revision-specific licence and licence URL, source-snapshot hash, and transformation/replacement notes. Licences are CC BY-SA **3.0 or 4.0** as reported by each admitted source record. Four excluded inputs and deterministic replacements are listed in `../items_preparation_audit.json`. Attribution does not eliminate share-alike obligations. Historical everyday/trap buckets are not validated domains; neither the question nor the author's proficiency has a CEFR label.
