"""Deterministic tokeniser and sentence splitter (stdlib only)."""

import re

WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|[0-9]+(?:[.,][0-9]+)*")
# Keep closing quotation marks/brackets attached to the preceding sentence.
SENT_SPLIT_RE = re.compile(
    r"(?:(?<=[.!?])|(?<=[.!?][\"'”’)\]]))\s+(?=[\"'“‘(\[]?[A-Z])"
    r"|(?<=[.!?])\s*$|\n+"
)
SENT_END_RE = re.compile(r"[.!?][\"'”’)\]]*$")

CONTRACTION_SPLIT_RE = re.compile(r"^(.*?)(n't|'s|'re|'ve|'ll|'d|'m)$")

# 's after a word is a clitic (possessive or contracted is) — not a content
# word, so it maps to nothing and never enters level counting.
CONTRACTION_TAIL = {
    "n't": ["not"], "'re": ["are"], "'ve": ["have"], "'ll": ["will"],
    "'d": ["would"], "'m": ["am"], "'s": [],
}

NUMBER_RE = re.compile(r"^[0-9]+(?:[.,][0-9]+)*$")


def split_sentences(text: str):
    """Split into sentences on terminal punctuation and newlines."""
    parts = [p.strip() for p in SENT_SPLIT_RE.split(text or "") if p and p.strip()]
    # merge fragments that have no terminal punctuation into the previous part
    merged = []
    for p in parts:
        if merged and not SENT_END_RE.search(merged[-1]) and not re.match(r"^[-*\d]+[.)]", p):
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


def tokens(text: str):
    """Word/number tokens, contractions split into stems + tails."""
    out = []
    for m in WORD_RE.finditer(text or ""):
        tok = m.group(0)
        cm = CONTRACTION_SPLIT_RE.match(tok)
        if cm and cm.group(2) in CONTRACTION_TAIL:
            stem, tail = cm.group(1), cm.group(2)
            if stem:
                out.append(stem)
            out.extend(w for w in CONTRACTION_TAIL[tail] if w)
        else:
            out.append(tok)
    return out


def is_number(tok: str) -> bool:
    return bool(NUMBER_RE.match(tok))


def sentence_initial_positions(text: str):
    """Character offsets where sentences start (for proper-noun heuristic)."""
    return {m.start() for m in re.finditer(r"(?:^|(?<=[.!?])\s+|\n)(?=[\"'(\[]?[A-Za-z])", text or "")}


def token_positions(text: str):
    """Yield (token, char_offset) pairs matching tokens()."""
    out = []
    for m in WORD_RE.finditer(text or ""):
        tok = m.group(0)
        cm = CONTRACTION_SPLIT_RE.match(tok)
        if cm and cm.group(2) in CONTRACTION_TAIL:
            stem, tail = cm.group(1), cm.group(2)
            if stem:
                out.append((stem, m.start()))
            for w in (x for x in CONTRACTION_TAIL[tail] if x):
                out.append((w, m.end()))
        else:
            out.append((tok, m.start()))
    return out
