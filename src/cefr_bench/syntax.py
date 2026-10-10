"""Syntax: sentence length, clauses per sentence, word length — bands from
calibration; uncalibrated -> distance-free neutral score with flag."""

from .tokenise import split_sentences, tokens


def syntax_measures(text: str):
    sents = [s for s in split_sentences(text) if s.strip()]
    sent_lens = []
    clause_counts = []
    word_lens = []
    for s in sents:
        toks = tokens(s)
        if not toks:
            continue
        sent_lens.append(len(toks))
        word_lens.extend(len(t) for t in toks if t.isalpha())
        # clause approximation: coordinating + subordinating conjunctions +
        # relative pronouns + semicolons
        import re
        clause_markers = re.findall(
            r"\b(?:and|but|or|so|because|although|though|while|when|if|since|that|which|who|whereas|;\s+)\b", s, re.I)
        clause_counts.append(1 + len(clause_markers))
    import statistics
    return {
        "n_sentences": len(sents),
        "mean_sent_len": statistics.mean(sent_lens) if sent_lens else 0.0,
        "max_sent_len": max(sent_lens) if sent_lens else 0,
        "clause_per_sent": statistics.mean(clause_counts) if clause_counts else 0.0,
        "mean_word_len": statistics.mean(word_lens) if word_lens else 0.0,
        "sent_lens": sent_lens,
        "clause_counts": clause_counts,
    }


def band_score(value: float, band):
    """1 inside band, linear decay outside, 0 at 2x band distance."""
    if band is None:
        return None  # uncalibrated -> neutral handled by caller
    lo, hi = band
    if lo <= value <= hi:
        return 1.0
    width = max(hi - lo, 1e-9)
    if value < lo:
        d = (lo - value) / width
    else:
        d = (value - hi) / width
    return max(0.0,  1.0 - d)


def syntax_scores(measures: dict, bands):
    """bands: {measure: [p5,p95]} for the target level, or None. Returns dict + flag."""
    out = {}
    neutral = True
    for key in ["mean_sent_len", "clause_per_sent", "mean_word_len"]:
        b = bands.get(key) if bands else None
        s = band_score(measures[key], b)
        if s is None:
            out[key] = (1.0, "uncalibrated")
        else:
            out[key] = (s, f"band={b}")
            neutral = False
    score = sum(v[0] for v in out.values()) / 3
    return score, out, ("syntax_uncalibrated" if neutral else None)