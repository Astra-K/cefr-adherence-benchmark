"""Generate the self-contained Kaggle task file: embeds word lists (LZMA +
base64), thresholds, grammar patterns, items and golden set into one .py file
with `# %%` cell markers, so the Kaggle notebook needs no internet access.
"""

import base64
import json
import lzma
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from cefr_bench.wordlists import get_lists
from cefr_bench.prompts import informed_prompt as canonical_informed_prompt
from cefr_bench.grammar import DETECTORS
from cefr_bench.thresholds import (TOLERANCE_FINAL, FLOOR_MIN_SHARE,
                                   FLOOR_MIN_TOKENS, GRAMMAR_CEILING_COUNT,
                                   SYNTAX_BANDS)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT_DIR = os.path.join(ROOT, "kaggle_task")
OUT = os.path.join(OUT_DIR, "cefr_task.py")

TEMPLATE = '''# %% [markdown]
# # CEFR-adherence benchmark
#
# This task measures whether a model can answer an English learner at a requested
# CEFR level (A1, B1, or C1). It compares a bare level request with a prompt that
# exposes the scorer's vocabulary and grammar guidance.
#
# ## Data attribution and licences
#
# - Original benchmark code: GNU Affero General Public License v3.0 only
#   (AGPL-3.0-only): https://www.gnu.org/licenses/agpl-3.0.html
# - CEFR-J Vocabulary Profile 1.5 and CEFR-J Grammar Profile 20180315: compiled
#   by Yukio Tono / Tono Laboratory, Tokyo University of Foreign Studies. The
#   source permits research and commercial use without charge when cited:
#   https://github.com/openlanguageprofiles/olp-en-cefrj
# - Octanove Vocabulary Profile C1/C2 1.0: Octanove Labs, CC BY-SA 4.0:
#   https://creativecommons.org/licenses/by-sa/4.0/
# - Learner questions: English Language Learners Stack Exchange. The complete
#   revision-specific per-item attribution ledger follows.
#
__ATTRIBUTION_TABLE__

# %%
# Auto-generated single-file Kaggle task (scorer v__VERSION__).
# Do not edit the embedded data by hand; run scripts/gen_kaggle_task.py.
import base64
import json
import lzma
from types import SimpleNamespace

import kaggle_benchmarks as kbench

__EMBEDDED_SOURCE__

# Preserve the small namespace used by the task wiring while keeping every
# dependency in this one uploadable file.
embedded = SimpleNamespace(
    ITEMS=ITEMS,
    THRESHOLDS=THRESHOLDS,
    DETECTORS=DETECTORS,
    load_wordlists=load_wordlists,
    relevance_prompt=relevance_prompt,
    informed_prompt=informed_prompt,
    score_reply=score_reply,
)

# %%
# ---- local dev: load .env if present (Kaggle preconfigures the LLM) ----
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# %%
# ---- unpack embedded data (profiles, prompts and items; ~__BLOB_KB__ KB base64) ----
FORM_LEVELS, HEADWORD_LEVELS = embedded.load_wordlists()
ITEMS = embedded.ITEMS
THRESHOLDS = embedded.THRESHOLDS
DETECTORS = embedded.DETECTORS

# %%
# ---- context-bound relevance gate; errors remain unscored ----
class RelevanceJudgeError(RuntimeError):
    """Missing or malformed judge evidence, not an irrelevant learner answer."""


def judge_relevance(item_text: str, reply: str) -> bool:
    criterion = "The reply meaningfully addresses the learner message in English."

    def prompt_fn(criteria, response_text):
        return embedded.relevance_prompt(item_text, response_text, criteria[0])

    try:
        verdict = kbench.assertions.assess_response_with_judge(
            criteria=[criterion], response_text=reply, judge_llm=kbench.judge_llm,
            prompt_fn=prompt_fn)
    except Exception as error:
        raise RelevanceJudgeError("Relevance judge call failed; sample is unscored") from error
    # SDK 0.6.1 returns AssessReport.results and swallows provider errors as None.
    results = getattr(verdict, "results", None)
    if not isinstance(results, list) or len(results) != 1:
        raise RelevanceJudgeError("Relevance judge returned no valid single-criterion report")
    passed = getattr(results[0], "passed", None)
    if not isinstance(passed, bool):
        raise RelevanceJudgeError("Relevance judge returned no boolean verdict")
    return passed


# %%
# ---- the task: one row = (item_text, level, condition); returns adherence float ----
@kbench.task(name="cefr-adherence-benchmark")
def cefr_adherence(llm, item_id: str, item_text: str, level: str, condition: str) -> float:
    """Score how well the model replies at the target CEFR level (0-1)."""
    if condition == "informed":
        prompt = embedded.informed_prompt(item_text, level)
    else:
        prompt = f"Reply to this learner at CEFR level {{level}}.\\n\\nLearner message: {{item_text}}"
    reply = llm.prompt(
        prompt,
        temperature=0.7,
        reasoning="low",
        extra_api_params={"max_tokens": 2048, "top_p": 0.8},
    )
    relevant = judge_relevance(item_text, reply)
    result = embedded.score_reply(reply, level, relevant=relevant)
    return float(result["combined"])


# %%
# ---- judge preflight: matched AND mismatched question/answer pairs ----
def validate_judge():
    dates_reply = "We use 'in' for months and 'on' for days. For example: in May, on Monday."
    probes = [
        (True, "Should I say in Monday or on Monday?", dates_reply),
        (True, "Should I say work in a company or work for a company?",
         "Both can be used. 'In' describes the place, while 'for' describes the employer."),
        (True, "What does break a leg mean before an exam?",
         "It means good luck. Your friend does not want you to hurt yourself."),
        (False, "What does break a leg mean before an exam?", dates_reply),
        (False, "Should I say in Monday or on Monday?",
         "I like pizza. It tastes good."),
        (False, "Should I say in Monday or on Monday?",
         "I am sorry, but I cannot help with that request."),
        (False, "Should I say in Monday or on Monday?", "Blorp zzz. Wibble qqq."),
        (True, "What does bank mean?",
         "Can you share the sentence? Bank can mean a place for money or the side of a river."),
    ]
    agree, errors = 0, 0
    for expected, question, text in probes:
        try:
            got = judge_relevance(question, text)
            agree += got == expected
            print(f"  judge={{got}} expected={{expected}} {'OK' if got == expected else 'MISS'}")
        except Exception as error:
            errors += 1
            print(f"  judge_error: {{type(error).__name__}}")
    report = {"agreement": agree, "total": len(probes), "errors": errors}
    print(f"judge agreement: {{agree}}/{{len(probes)}}; errors: {{errors}}")
    if errors or agree != len(probes):
        raise RelevanceJudgeError("Judge preflight failed; evaluation has not started")
    return report


# %%
# ---- evaluation data: 30 items x 3 levels x 2 conditions = 180 rows ----
import pandas as pd

rows = []
for it in ITEMS:
    for level in ("A1", "B1", "C1"):
        for condition in ("bare", "informed"):
            rows.append({{"item_id": it["id"], "item_text": it["text"],
                          "level": level, "condition": condition}})
EVAL_DATA = pd.DataFrame(rows)
print(f"evaluation rows: {{len(EVAL_DATA)}}")
for lv in ("A1", "B1", "C1"):
    print(f"  informed {{lv}} prompt chars: {{len(embedded.informed_prompt(ITEMS[0]['text'], lv)):,}}")

# %%
validate_judge()

# %%
cefr_adherence.evaluate(llm=[kbench.llm], evaluation_data=EVAL_DATA,
                        on_failure="continue", max_attempts=1)
'''


def _markdown_escape(value):
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("]", "\\]")


def _attribution_table(items):
    lines = [
        "# ## Learner-question attribution",
        "#",
        "# Transformation: Original title prepended to original body; HTML tags removed,",
        "# entities decoded, whitespace normalized, and learner errors unchanged.",
        "# Stack Exchange licensing help: https://ell.stackexchange.com/help/licensing",
        "#",
        "# | Item | Author | Source question | Revision licence |",
        "# |---|---|---|---|",
    ]
    for item in items:
        author = item["author"]
        lines.append(
            "# | {item_id} | [{author}]({author_url}) | [question]({question_url}) | "
            "[{licence}]({licence_url}) |".format(
                item_id=_markdown_escape(item["id"]),
                author=_markdown_escape(author["name"]),
                author_url=author["url"],
                question_url=item["link"],
                licence=_markdown_escape(item["license"]),
                licence_url=item["license_url"],
            )
        )
    return "\n".join(lines)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    wl = get_lists()
    items = json.load(open(os.path.join(ROOT, "data", "items.json")))
    thresholds = {
        "tolerance_final": TOLERANCE_FINAL,
        "floor_min_share": FLOOR_MIN_SHARE,
        "floor_min_tokens": FLOOR_MIN_TOKENS,
        "grammar_ceiling_count": GRAMMAR_CEILING_COUNT,
        "syntax_bands": SYNTAX_BANDS,
    }
    detectors = [
        {"name": n, "level": lv, "cefrj_id": cid, "pattern": pat, "source": src}
        for (n, lv, cid, pat, src) in DETECTORS
    ]
    prefixes = {
        level: canonical_informed_prompt('', level, wl)
        for level in ('A1', 'B1', 'C1')
    }
    payload = {
        "form_levels": wl.form_levels,
        "headword_levels": dict(wl.headword_level),
        "items": items,
        "thresholds": thresholds,
        "detectors": detectors,
        "informed_prefixes": prefixes,
    }
    blob = base64.b64encode(lzma.compress(
        json.dumps(payload, sort_keys=True).encode(), preset=9)).decode()

    # write the embedded module
    emb = os.path.join(OUT_DIR, "cefr_scorer_embedded.py")
    # Write blob in chunks to keep notebook lines manageable.
    with open(emb, "w") as f:
        f.write('# Auto-generated embedded data + mini-scorer (v0.2.0)\n')
        f.write('# Source: CEFR-J Vocabulary Profile 1.5 + Octanove C1/C2 (see SOURCES.md)\n')
        f.write('import base64, json, lzma, re, statistics\n\n')
        f.write('_BLOB = (\n')
        for i in range(0, len(blob), 100):
            f.write(f'    "{blob[i:i+100]}"\n')
        f.write(')\n\n')
        f.write('_PAYLOAD = json.loads(lzma.decompress(base64.b64decode(_BLOB)))\n')
        f.write('FORM_LEVELS = _PAYLOAD["form_levels"]\n')
        f.write('HEADWORD_LEVELS = _PAYLOAD["headword_levels"]\n')
        f.write('ITEMS = _PAYLOAD["items"]\n')
        f.write('THRESHOLDS = _PAYLOAD["thresholds"]\n')
        f.write('DETECTORS = _PAYLOAD["detectors"]\n')
        f.write('INFORMED_PREFIXES = _PAYLOAD["informed_prefixes"]\n')
        f.write('del _PAYLOAD\n\n')

    # append the mini-scorer implementation (copied from src, adapted)
    scorer_src = _mini_scorer_source()
    with open(emb, "a") as f:
        f.write(scorer_src)
        with open(os.path.join(ROOT, 'src', 'cefr_bench', 'relevance.py')) as shared:
            f.write('\n\n' + shared.read())

    # Write the one-file upload artifact. Keep the sibling embedded module for
    # parity tests and local inspection, but do not require it at runtime.
    embedded_source = open(emb).read()
    task_source = (TEMPLATE.replace("__VERSION__", "0.2.0")
                   .replace("__BLOB_KB__", str(round(len(blob) / 1024)))
                   .replace("__ATTRIBUTION_TABLE__", _attribution_table(items))
                   .replace("{{", "{").replace("}}", "}")
                   .replace("__EMBEDDED_SOURCE__", embedded_source))
    with open(OUT, "w") as f:
        f.write(task_source)

    print(f"wrote {emb} ({os.path.getsize(emb)/1024:.0f} KB)")
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)")


def _mini_scorer_source():
    """The pure-python scorer, standalone (no cefr_bench imports)."""
    # Embed the canonical stdlib tokenizer verbatim to prevent native/Kaggle drift.
    with open(os.path.join(ROOT, 'src', 'cefr_bench', 'tokenise.py')) as handle:
        tokeniser = handle.read()
    return '\n' + tokeniser + '''

# ---- grammar ----
_COMPILED = [(d[\"name\"], d[\"level\"], re.compile(d[\"pattern\"], re.I)) for d in DETECTORS]
LEVEL_ORDER = {\"A1\": 0, \"A2\": 1, \"B1\": 2, \"B2\": 3, \"C1\": 4, \"C2\": 5}


def scan_grammar(text, sents):
    hits = []
    for si, sent in enumerate(sents):
        for name, lv, rx in _COMPILED:
            for m in rx.finditer(sent):
                hits.append({\"name\": name, \"level\": lv, \"sentence\": si})
    return hits


# ---- analysis ----
META_TALK_RE = re.compile(r\"\\b(?:as an ai|language model|i'?m sorry|cefr level|great question|let me know if|feel free to|delve|furthermore|moreover|in conclusion|i cannot|i can'?t assist|my apologies)\\b\", re.I)
MARKDOWN_RE = re.compile(r\"(\\*\\*|__|\\*|`|#+\\s|>\\s|\\[.*?\\]\\(.*?\\))\")

# UK -> US spelling normalisation (verbatim from src.cefr_bench.wordlists)
UK_TO_US = {\"favour\": \"favor\", \"favourite\": \"favorite\", \"colour\": \"color\",
    \"colours\": \"colors\", \"behaviour\": \"behavior\", \"honour\": \"honor\",
    \"humour\": \"humor\", \"labour\": \"labor\", \"neighbour\": \"neighbor\",
    \"centre\": \"center\", \"metre\": \"meter\", \"theatre\": \"theater\",
    \"fibre\": \"fiber\", \"litre\": \"liter\", \"grey\": \"gray\",
    \"optimise\": \"optimize\", \"organise\": \"organize\", \"realise\": \"realize\",
    \"recognise\": \"recognize\", \"analyse\": \"analyze\", \"utilise\": \"utilize\",
    \"emphasise\": \"emphasize\", \"prioritise\": \"prioritize\",
    \"specialise\": \"specialize\", \"practise\": \"practice\",
    \"apologise\": \"apologize\", \"criticise\": \"criticize\",
    \"optimised\": \"optimized\", \"organised\": \"organized\",
    \"realised\": \"realized\", \"recognised\": \"recognized\",
    \"scrutinise\": \"scrutinize\", \"scrutinises\": \"scrutinizes\",
    \"immerse\": \"immerse\",  # no-op guard
}


def level_of(surface, form_levels):
    # Canonical lookup chain (parity with src.cefr_bench.wordlists.level_of):
    # exact -> UK->US whitelist -> suffix stems incl. stem+e and de-doubled
    # consonant. A resolvable stem is never a violation.
    t = surface.lower()
    lv = form_levels.get(t)
    if lv is not None:
        return lv
    lv = form_levels.get(UK_TO_US.get(t, t))
    if lv is not None:
        return lv
    for suf in (\"s\", \"es\", \"ed\", \"ing\", \"ly\"):
        if t.endswith(suf) and len(t) > len(suf) + 2:
            stem = t[: -len(suf)]
            for cand in (stem, stem + \"e\", stem[:-1] if stem[-1:] == stem[-2:-1] else None):
                if cand:
                    lv = form_levels.get(cand)
                    if lv is not None:
                        return lv
    return None


def _is_pronoun_initial(text, offset):
    # Heuristic (parity with src): capitalized mid-sentence ASCII word is a
    # proper-noun candidate, not an above-level violation.
    prefix = text[max(0, offset - 2):offset]
    return not re.search(r\"[.!?]\\s*$|\\n\\s*$|^\\s*$\", prefix)


def clean(text):
    t = MARKDOWN_RE.sub(\"\", text or \"\")
    flags = [\"meta_talk\"] if META_TALK_RE.search(t) else []
    return t.strip(), flags


def score_reply(text, level, relevant=True):
    # Parity v2 with src.cefr_bench.scorer.score_reply (E020 fix):
    # floor partial credit, proper-noun exclusion, UK->US + de-doubled
    # consonant lookup, exact clause-marker set, no-alpha gate.
    TH = THRESHOLDS
    cleaned, flags = clean(text)
    sents = split_sentences(cleaned)
    toks = tokens(cleaned)
    alpha = [t for t in toks if t.isalpha()]
    if not cleaned or len(sents) < 2 or not alpha:
        return {\"combined\": 0.0, \"adherent\": False, \"flags\": flags + [\"gate_fail\"], \"n_sentences\": len(sents)}
    t_ord = LEVEL_ORDER[level]
    listed, unlisted = [], []
    for tok, off in token_positions(cleaned):
        if is_number(tok) or len(tok) <= 1:
            continue
        lv = level_of(tok, FORM_LEVELS)
        if lv is not None:
            listed.append((tok, LEVEL_ORDER[lv]))
        elif tok[:1].isupper() and _is_pronoun_initial(cleaned, off):
            continue  # proper-noun candidate: excluded from content + violations
        else:
            unlisted.append(tok)
    denom = max(1, len(listed) + len(unlisted))
    dists = [d - t_ord for (_, d) in listed] + [2] * len(unlisted)
    rate_one = sum(1 for d in dists if d == 1) / denom
    rate_two = sum(1 for d in dists if d >= 2) / denom
    caps = TH[\"tolerance_final\"][level]
    cap_one = max(caps[\"one_level_above\"], 1.0 / denom)
    cap_two = max(caps[\"two_plus_above_or_unlisted\"], 1.0 / denom)
    ratio = max(rate_one / cap_one, rate_two / cap_two)
    v_ceiling = 1.0 if ratio <= 1 else max(0.0, 1.0 - (ratio - 1) / 2)
    v_ok = rate_one <= cap_one and rate_two <= cap_two
    n_top2 = sum(1 for d in dists if -1 <= d <= 0)
    share_floor = TH[\"floor_min_share\"][level]
    min_tok = TH[\"floor_min_tokens\"][level]
    if share_floor is not None:
        floor_share = n_top2 / denom
        v_floor_met = floor_share >= share_floor and (not min_tok or n_top2 >= min_tok)
        v_floor = min(1.0, floor_share / share_floor)  # partial credit, parity with src
        if min_tok and n_top2 < min_tok:
            v_floor = 0.0
            v_floor_met = False
    elif min_tok:
        v_floor_met = n_top2 >= min_tok
        v_floor = 1.0 if v_floor_met else 0.0
    else:
        v_floor, v_floor_met = 1.0, True
    vocab_dim = v_ceiling * v_floor
    hits = scan_grammar(cleaned, sents)
    above = [h for h in hits if LEVEL_ORDER[h[\"level\"]] > t_ord]
    g_max = TH[\"grammar_ceiling_count\"][level]
    g_ok = len(above) <= g_max
    g_ceiling = 1.0 if g_ok else max(0.0, 1.0 - (len(above) - g_max) / 2)
    grammar_dim = g_ceiling
    sent_lens = [len(tokens(s)) for s in sents if tokens(s)]
    mean_sent_len = statistics.mean(sent_lens) if sent_lens else 0
    word_lens = [len(t) for t in toks if t.isalpha()]
    mean_word_len = statistics.mean(word_lens) if word_lens else 0
    clause_counts = []
    for s in sents:
        markers = re.findall(r\"\\b(?:and|but|or|so|because|although|though|while|when|if|since|that|which|who|whereas|;\\s+)\\b\", s, re.I)
        clause_counts.append(1 + len(markers))
    clause_per_sent = statistics.mean(clause_counts) if clause_counts else 0
    bands = TH[\"syntax_bands\"][level]
    def band_score(value, band):
        lo, hi = band
        if lo <= value <= hi:
            return 1.0
        width = max(hi - lo, 1e-9)
        d = (lo - value) / width if value < lo else (value - hi) / width
        return max(0.0, 1.0 - d)
    syn = (band_score(mean_sent_len, bands[\"mean_sent_len\"])
           + band_score(clause_per_sent, bands[\"clause_per_sent\"])
           + band_score(mean_word_len, bands[\"mean_word_len\"])) / 3
    combined = 0.4 * vocab_dim + 0.4 * grammar_dim + 0.2 * syn
    if not relevant:
        combined = 0.0
        flags.append(\"irrelevant\")
    return {\"combined\": round(combined, 4),
            \"adherent\": bool(v_ok and g_ok and v_floor_met),
            \"flags\": flags, \"n_sentences\": len(sents),
            \"vocab\": {\"rate_one_above\": round(rate_one, 4),
                      \"rate_two_plus\": round(rate_two, 4)}
            }


def informed_prompt(item_text, level):
    # Prefixes come directly from src.cefr_bench.prompts; all runners use
    # byte-identical informed conditions, including full word/grammar lists.
    return INFORMED_PREFIXES[level] + item_text


def load_wordlists():
    payload = json.loads(lzma.decompress(base64.b64decode(_BLOB)))
    g = globals()
    g[\"FORM_LEVELS\"] = payload[\"form_levels\"]
    g[\"HEADWORD_LEVELS\"] = payload[\"headword_levels\"]
    g[\"ITEMS\"] = payload[\"items\"]
    return payload[\"form_levels\"], payload[\"headword_levels\"]


load_wordlists()  # set globals at import
'''


if __name__ == "__main__":
    main()
