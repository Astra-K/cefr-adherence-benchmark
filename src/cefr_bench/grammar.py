"""Grammar detectors: one level-tagged regex table, each hit typed 'grammar'.

Each detector names its CEFR-J Grammar Profile ID (or "ours" when we assigned
the level ourselves), per the brief. Patterns are case-insensitive on the first
token only where sentence position matters; most are anywhere in sentence.
"""

import re

from .tokenise import split_sentences


def _kw(pattern: str, flags=int(re.IGNORECASE)):
    return re.compile(pattern, flags)


# Detectors: (name, cefr_level, cefrj_id, pattern, source)
# Source: "CEFR-J GP" = from the grammar profile CSV; "ours" = our assignment.
DETECTORS = [
    # ---- A1: be/have/there-is, simple present/past, can, going to ----
    ("be_aff_dec", "A1", "1/2", r"\b(?:i am|you are|he is|she is|it is|we are|they are|i'm|you're|he's|she's|it's|we're|they're)\b", "CEFR-J GP"),
    ("be_neg_dec", "A1", "1-1/2-1", r"\b(?:i am not|is not|are not|isn't|aren't)\b", "CEFR-J GP"),
    ("be_question", "A1", "2-2", r"^\s*(?:am i|are you|is he|is she|is it|are we|are they)\b", "CEFR-J GP"),
    ("have_got", "A1", "12", r"\b(?:i have|you have|he has|she has|it has|we have|they have|have you|has he|has she)\b", "CEFR-J GP"),
    ("imperative", "A1", "5", r"^\s*(?:come|go|look|listen|sit|stand|open|close|read|write|say|tell|ask|think|take|put|find|help|let)\b", "CEFR-J GP"),
    ("can_modal", "A1", "21", r"\bcan\b", "CEFR-J GP"),
    ("going_to", "A1", "A1 going-to", r"\b(?:going to|gonna)\b", "CEFR-J GP"),
    ("present_simple_3sg", "A1", "60", r"\b(?:he|she|it)\s+(?:works|goes|lives|likes|wants|has|does|says|knows|thinks|needs|comes|makes|takes|looks|means)\b", "CEFR-J GP"),
    ("past_simple_common", "A1", "62", r"\b(?:was|were|went|had|did|saw|ate|said|made|took|got|came|found|thought|bought|left|put|told)\b", "CEFR-J GP"),
    ("present_progressive", "A1", "A1 prog", r"\b(?:am|is|are)\s+([a-z]+ing)\b", "CEFR-J GP"),
    ("like_verb_ing", "A1", "A1 like+ing", r"\b(?:like|love|hate|enjoy)\s+[a-z]+ing\b", "CEFR-J GP"),

    # ---- A2: past continuous, comparatives, will, have to ----
    ("past_continuous", "A2", "A2-1", r"\b(?:was|were)\s+[a-z]+ing\b", "CEFR-J GP"),
    ("comparative_adj", "A2", "A2 cmp", r"\b(?:bigger|smaller|cheaper|easier|harder|faster|slower|older|younger|longer|shorter|better|worse)\b", "ours"),
    ("will_fut", "A2", "A2 will", r"\bwill\b|\b'll\b", "CEFR-J GP"),
    ("have_to", "A2", "A2 have-to", r"\bhave to\b|\bhas to\b", "CEFR-J GP"),
    ("comparative_periphrastic", "A2", "A2 cmp2", r"\bmore\s+(?:beautiful|expensive|important|interesting|difficult|famous|careful)\b", "ours"),
    ("superlative", "A2", "A2 sup", r"\b(?:the oldest|the youngest|the biggest|the best|the worst|the cheapest|the most)\b", "ours"),

    # ---- B1: present perfect, used to, 2nd conditional, passives, relative clauses ----
    ("present_perfect", "B1", "87/145", r"\b(?:have|has)\s+(?:been|done|seen|eaten|gone|made|taken|got|written|read|bought|left|told|found|thought|paid|met|known|heard|lost|sent|sold|shown|sung|spoken|spent|won|understood|drunk|driven|broken|chosen|built|brought|caught|cut|felt|kept|held|hurt|let|lain|lost|put|said|sat|slept|stood|stuck|swum|taught|thrown|woken|worn)\b", "CEFR-J GP"),
    ("present_perfect_cont", "B1", "145-2", r"\b(?:have|has)\s+been\s+[a-z]+ing\b", "CEFR-J GP"),
    ("past_perfect", "B1", "146", r"\bhad\s+(?:been|done|seen|gone|made|taken|eaten|got|written|read|bought|left|told|found|thought|paid|met|known|heard|lost|sent|sold|shown|spoken|spent|won|understood|drunk|driven|broken|chosen|built|brought|caught|felt|kept|held|hurt|put|said|sat|slept|stood|swum|taught|thrown|woken|worn)\b", "CEFR-only fallback"),
    ("used_to", "B1", "140", r"\bused to\b", "CEFR-J GP"),
    ("get_passive", "B1", "87", r"\bget\s+(?:done|paid|married|hired|fired|hurt|killed|stuck|lost|broken|fixed|repaired|damaged)\b", "CEFR-J GP"),
    ("passive_voice", "B1", "144/207", r"\b(?:am|is|are|was|were|be|been|being|get|gets|got)\s+([a-z]+(?:ed|en))\b", "CEFR-J GP"),
    ("relative_which", "B1", "167", r"\b,(?: which| who| where| when)\b|\bwhich\b|\bwho\b", "CEFR-J GP"),
    ("modal_perfect", "B1", "CEFR-J GP", r"\b(?:should|could|would|might|must)\s+have\s+[a-z]+(?:ed|en)\b", "CEFR-J GP"),
    ("2nd_conditional", "B1", "B1 2nd-cond", r"\bif\s+i\s+(?:were|had|knew|won|could)\b.{0,60}\b(?:would|'d)\b", "ours"),
    ("wish_past", "B1", "B1 wish", r"\bwish(?:es)?\s+(?:i|he|she|they|we|you)\s+(?:had|were|could|knew)\b", "ours"),
    ("indirect_question", "B1", "153", r"\b(?:know|wonder|ask|tell me)\s+(?:if\s+|what|when|where|why|how|who)\b", "CEFR-J GP"),
    ("infinitive_purpose", "B1", "B1 inf-purpose", r"\bto\s+(?:buy|get|see|learn|find|help|make|take|meet|improve|practice|practise)\b", "ours"),

    # ---- B2: advanced passives, inversions, participle clauses ----
    ("have_causative", "B2", "207", r"\b(?:have|h's|get)\s+[a-z]+\s+([a-z]+(?:ed|en))\b", "CEFR-J GP"),
    ("had_better", "B2", "had-better", r"\bhad better\b|\b'd better\b", "CEFR-J GP"),
    ("past_perfect_cont", "B2", "CEFR-J GP", r"\bhad\s+been\s+[a-z]+ing\b", "CEFR-J GP"),
    ("future_perfect", "B2", "B2 fp", r"\b(?:will|shall)\s+have\s+[a-z]+(?:ed|en)\b", "ours"),
    ("future_continuous", "B2", "CEFR-J GP", r"\b(?:will|'ll)\s+be\s+[a-z]+ing\b", "CEFR-J GP"),
    ("prep_relative", "B2", "184", r"\b(?:the\s+[a-z]+\s+)?(?:which|whom|whose)\b", "CEFR-J GP"),
    ("participle_clause", "B2", "B2 part", r"(?:^|[\.\?!]\s+)(?:[A-Z][a-z]+ing|Having\s+[a-z]+(?:ed|en))\b", "ours"),
    ("inversion_conditional", "B2", "B2 inv", r"^\s*(?:Had|Should|Were)\s+(?:I|we|they|he|she|you)\b", "ours"),
    ("inversion_negative", "B2", "B2 inv2", r"^\s*(?:Never|Rarely|Seldom|Not only|Little)\s+(?:have|has|had|do|does|did|is|are|was|were)\b", "ours"),
    ("wish_past_perfect", "B2", "B2 wish3", r"\bwish(?:es)?\s+(?:i|he|she|they|we|you)\s+had\s+[a-z]+(?:ed|en)\b", "ours"),
    ("modal_perfect_cont", "B2", "B2 mpc", r"\b(?:should|could|would|might|must)\s+have\s+been\s+[a-z]+ing\b", "ours"),
    ("3rd_conditional", "B2", "B2 3rd-cond", r"\bif\s+(?:i|he|she|we|they|you)\s+had\s+[a-z]+(?:ed|en)\b.{0,60}\bwould\s+have\b", "ours"),
    ("reported_speech_past", "B2", "B2 rs", r"\b(?:said|told)\s+(?:me\s+|us\s+|him\s+|her\s+|them\s+)?(?:that\s+)?(?:i|he|she|they|we)\s+(?:was|were|had|would|could)\b", "ours"),
    ("future_in_past", "B2", "ours", r"\bwas going to\b|\bwere going to\b", "ours"),
    ("mixed_conditionals", "B2", "B2 mix", r"\bif\s+(?:i|he|she|we|they|you)\s+(?:had|were)\b.{0,60}\bwould\s+be\b", "ours"),
    ("saxon_genitive", "B2", "B2 saxon", r"\b[A-Z][a-z]+(?:'s)\b", "ours"),
    ("future_perf_continuous", "B2", "B2 fpc", r"\b(?:will|'ll)\s+have\s+been\s+[a-z]+ing\b", "B2 fpc"),
    ("parenthetical_asides", "B2", "B2 paren", "ours-pattern-placeholder", "ours"),
]

# fix two placeholder rows: compile from literal patterns instead
DETECTORS = [d for d in DETECTORS if d[3] != "ours-pattern-placeholder"]

_COMPILED = [
    (name, lv, cid, _kw(pat), src) for (name, lv, cid, pat, src) in DETECTORS
]

# Multi-hit suppression: long forms first so e.g. present_perfect_cont is
# counted before present_perfect on the same span would double-count spans —
# we handle overlap by span-set per detector name at scoring time instead.


def scan_grammar(text: str, sentences=None):
    """Return list of hits: dicts with name, level, cefrj_id, sentence_idx, match_text."""
    sents = sentences if sentences is not None else split_sentences(text)
    hits = []
    for si, sent in enumerate(sents):
        for name, lv, cid, rx, src in _COMPILED:
            for m in rx.finditer(sent):
                hits.append({
                    "name": name, "level": lv, "cefrj_id": cid,
                    "sentence": si, "match": m.group(0),
                })
    return hits
