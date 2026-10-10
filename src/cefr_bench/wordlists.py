"""Level-tagged word list: loads CEFR-J + Octanove CSVs and expands inflections.

One table for vocab; every form maps to the LOWEST level among its headwords
(most permissive reading -> fewest false violations; documented in DEVLOG).
"""

import csv
import os
from collections import defaultdict

from .config import LEVEL_ORDER
from .lemmas import expand_headword

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "data", "raw"))

FILES = {
    "cefrj": "cefrj-vocabulary-profile-1.5.csv",
    "octanove": "octanove-vocabulary-profile-c1c2-1.0.csv",
}

# collapse CEFR-J sublevels (A1.1 -> A1)
_VALID = {"A1", "A2", "B1", "B2", "C1", "C2"}

# UK -> US spelling normalisation (whitelist, not rules — avoids overreach)
UK_TO_US = {
    "favour": "favor", "favourite": "favorite", "colour": "color",
    "colours": "colors", "behaviour": "behavior", "honour": "honor",
    "humour": "humor", "labour": "labor", "neighbour": "neighbor",
    "centre": "center", "metre": "meter", "theatre": "theater",
    "fibre": "fiber", "litre": "liter", "grey": "gray",
    "optimise": "optimize", "organise": "organize", "realise": "realize",
    "recognise": "recognize", "analyse": "analyze", "utilise": "utilize",
    "emphasise": "emphasize", "prioritise": "prioritize",
    "specialise": "specialize", "practise": "practice",
    "apologise": "apologize", "criticise": "criticize",
    "optimised": "optimized", "organised": "organized",
    "realised": "realized", "recognised": "recognized",
    "scrutinise": "scrutinize", "scrutinises": "scrutinizes",
    "immerse": "immerse",  # no-op guard
}


def _norm_level(raw: str):
    lv = (raw or "").strip().upper()
    if not lv:
        return None
    lv = lv.split(".")[0]
    return lv if lv in _VALID else None


class WordLists:
    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or DATA_DIR
        self.form_levels = {}       # surface form -> lowest CEFR level
        self.form_pos = defaultdict(set)  # surface form -> set of POS
        self.headword_counts = defaultdict(int)
        self.headword_level = {}    # headword -> lowest CEFR level
        self.multiword_skipped = 0
        self._build()

    def headword_items(self):
        """Yield (headword, level) pairs at their lowest level."""
        return self.headword_level.items()

    def _add_form(self, form: str, level: str, pos: str):
        cur = self.form_levels.get(form)
        if cur is None or level < cur:  # string compare works for A1<C1? No.
            from .config import LEVEL_ORDER
            if cur is None or LEVEL_ORDER[level] < LEVEL_ORDER[cur]:
                self.form_levels[form] = level
        self.form_pos[form].add(pos)

    def _build(self):
        rows = []
        for key, fname in FILES.items():
            path = os.path.join(self.data_dir, fname)
            with open(path, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    rows.append(r)
        for r in rows:
            hw = (r.get("headword") or "").strip().lower()
            pos = (r.get("pos") or "").strip().lower()
            lv = _norm_level(r.get("CEFR"))
            if not hw or not lv:
                continue
            # slash-variant headwords (favorite/favourite) -> index each variant
            variants = [v.strip() for v in hw.split("/") if v.strip()]
            for hwv in variants:
                if " " in hwv or "-" in hwv:
                    self.multiword_skipped += 1
                    continue
                self.headword_counts[lv] += 1
                cur = self.headword_level.get(hwv)
                if cur is None or LEVEL_ORDER[lv] < LEVEL_ORDER[cur]:
                    self.headword_level[hwv] = lv
                for form in expand_headword(hwv, pos):
                    self._add_form(form, lv, pos)

    def level_of(self, surface: str):
        """Lowest CEFR level of a surface form, or None if unlisted.
        Falls back to morphological family (suffix strip) and UK spelling
        normalisation, so inflection/variant misses don't become false
        violations (flag-audit finding E011)."""
        t = surface.lower()
        lv = self.form_levels.get(t)
        if lv is not None:
            return lv
        lv = self.form_levels.get(UK_TO_US.get(t, t))
        if lv is not None:
            return lv
        for suf in ("s", "es", "ed", "ing", "ly"):
            if t.endswith(suf) and len(t) > len(suf) + 2:
                stem = t[: -len(suf)]
                for cand in (stem, stem + "e", stem[:-1] if stem[-1:] == stem[-2:-1] else None):
                    if cand:
                        lv = self.form_levels.get(cand)
                        if lv is not None:
                            return lv
        return None

    def pos_of(self, surface: str):
        return self.form_pos.get(surface.lower(), set())


_default = None


def get_lists() -> WordLists:
    global _default
    if _default is None:
        _default = WordLists()
    return _default
