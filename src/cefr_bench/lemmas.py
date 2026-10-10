"""Irregular form tables and inflection expansion (pure Python).

The brief prescribes expanding the word lists with regular suffixes plus an
irregular-verb table, so surface-form matching works without a lemmatiser and
lemmatiser misses never appear as false violations.
"""

# ~170 common irregular verbs: lemma -> (past, past-participle). "-en" forms etc.
IRREGULAR_VERBS = {
    "arise": ("arose", "arisen"), "awake": ("awoke", "awoken"),
    "be": ("was", "been"), "bear": ("bore", "born"), "beat": ("beat", "beaten"),
    "become": ("became", "become"), "begin": ("began", "begun"),
    "bend": ("bent", "bent"), "bet": ("bet", "bet"), "bind": ("bound", "bound"),
    "bite": ("bit", "bitten"), "bleed": ("bled", "bled"), "blow": ("blew", "blown"),
    "break": ("broke", "broken"), "breed": ("bred", "bred"),
    "bring": ("brought", "brought"), "build": ("built", "built"),
    "burn": ("burnt", "burnt"), "burst": ("burst", "burst"),
    "buy": ("bought", "bought"), "catch": ("caught", "caught"),
    "choose": ("chose", "chosen"), "come": ("came", "come"),
    "cost": ("cost", "cost"), "cut": ("cut", "cut"), "deal": ("dealt", "dealt"),
    "dig": ("dug", "dug"), "do": ("did", "done"), "draw": ("drew", "drawn"),
    "dream": ("dreamt", "dreamt"), "drink": ("drank", "drunk"),
    "drive": ("drove", "driven"), "eat": ("ate", "eaten"), "fall": ("fell", "fallen"),
    "feed": ("fed", "fed"), "feel": ("felt", "felt"), "fight": ("fought", "fought"),
    "find": ("found", "found"), "fly": ("flew", "flown"),
    "forbid": ("forbade", "forbidden"), "forget": ("forgot", "forgotten"),
    "forgive": ("forgave", "forgiven"), "freeze": ("froze", "frozen"),
    "get": ("got", "got"), "give": ("gave", "given"), "go": ("went", "gone"),
    "grow": ("grew", "grown"), "hang": ("hung", "hung"), "have": ("had", "had"),
    "hear": ("heard", "heard"), "hide": ("hid", "hidden"), "hit": ("hit", "hit"),
    "hold": ("held", "held"), "hurt": ("hurt", "hurt"), "keep": ("kept", "kept"),
    "know": ("knew", "known"), "lay": ("laid", "laid"), "lead": ("led", "led"),
    "leave": ("left", "left"), "lend": ("lent", "lent"), "let": ("let", "let"),
    "lie": ("lay", "lain"), "light": ("lit", "lit"), "lose": ("lost", "lost"),
    "make": ("made", "made"), "mean": ("meant", "meant"),
    "meet": ("met", "met"), "pay": ("paid", "paid"), "put": ("put", "put"),
    "read": ("read", "read"), "ride": ("rode", "ridden"), "ring": ("rang", "rung"),
    "rise": ("rose", "risen"), "run": ("ran", "run"), "say": ("said", "said"),
    "see": ("saw", "seen"), "sell": ("sold", "sold"), "send": ("sent", "sent"),
    "shake": ("shook", "shaken"), "shine": ("shone", "shone"),
    "shoot": ("shot", "shot"), "show": ("showed", "shown"),
    "shut": ("shut", "shut"), "sing": ("sang", "sung"), "sit": ("sat", "sat"),
    "sleep": ("slept", "slept"), "speak": ("spoke", "spoken"),
    "spend": ("spent", "spent"), "spin": ("spun", "spun"),
    "spread": ("spread", "spread"), "stand": ("stood", "stood"),
    "steal": ("stole", "stolen"), "stick": ("stuck", "stuck"),
    "sting": ("stung", "stung"), "swim": ("swam", "swum"),
    "take": ("took", "taken"), "teach": ("taught", "taught"),
    "tear": ("tore", "torn"), "tell": ("told", "told"),
    "think": ("thought", "thought"), "throw": ("threw", "thrown"),
    "understand": ("understood", "understood"), "wake": ("woke", "woken"),
    "wear": ("wore", "worn"), "win": ("won", "won"), "write": ("wrote", "written"),
}

IRREGULAR_PLURALS = {
    "man": ["men"], "woman": ["women"], "child": ["children"],
    "person": ["people"], "foot": ["feet"], "tooth": ["teeth"],
    "goose": ["geese"], "mouse": ["mice"], "ox": ["oxen"],
    "die": ["dice"], "louse": ["lice"], "leaf": ["leaves"],
    "life": ["lives"], "knife": ["knives"], "wife": ["wives"],
    "half": ["halves"], "loaf": ["loaves"], "thief": ["thieves"],
    "wolf": ["wolves"], "shelf": ["shelves"], "self": ["selves"],
    "cactus": ["cacti"], "focus": ["foci"], "fungus": ["fungi"],
    "analysis": ["analyses"], "crisis": ["crises"], "thesis": ["theses"],
    "datum": ["data"], "medium": ["media"], "criterion": ["criteria"],
    "phenomenon": ["phenomena"], "sheep": ["sheep"], "fish": ["fish"],
    "deer": ["deer"], "series": ["series"], "species": ["species"],
}

IRREGULAR_ADJ = {
    "good": ["better", "best"], "bad": ["worse", "worst"],
    "far": ["further", "furthest"], "little": ["less", "least"],
    "many": ["more", "most"], "much": ["more", "most"],
    "well": ["better", "best"], "old": ["older", "elder"],
}

VOWELS = set("aeiou")


def _double_consonant(w: str):
    """Return doubled stem for CVC doubling (stop -> stopp), else None."""
    if len(w) >= 3 and w[-1] not in VOWELS and w[-1] not in "wxy" \
            and w[-2] in VOWELS and w[-3] not in VOWELS:
        return w + w[-1]
    return None


def verb_forms(lemma: str):
    forms = {lemma}
    if lemma == "be":
        return {"be", "am", "is", "are", "was", "were", "been", "being",
                "'m", "'re", "'s", "ain't"}
    if lemma in IRREGULAR_VERBS:
        past, pp = IRREGULAR_VERBS[lemma]
        forms |= {past, pp}
    else:
        if lemma.endswith("e"):
            forms |= {lemma + "d", lemma[:-1] + "ing"}
        elif lemma.endswith("y") and len(lemma) > 1 and lemma[-2] not in VOWELS:
            forms |= {lemma[:-1] + "ied", lemma + "ing"}
        else:
            forms.add(lemma + "ed")
            d = _double_consonant(lemma)
            if d:
                forms |= {d + "ed", d + "ing"}
            forms.add(lemma + "ing")
        # past participle == past for regulars
    forms.add(lemma + "s")
    if lemma.endswith(("s", "sh", "ch", "x", "z", "o")):
        forms.add(lemma + "es")
    if lemma.endswith("y") and len(lemma) > 1 and lemma[-2] not in VOWELS:
        forms.add(lemma[:-1] + "ies")
    # note: -ing for non-e verbs added above; for e-verbs added; irregulars:
    if lemma in IRREGULAR_VERBS:
        forms.add(lemma + "ing")
    return forms


def noun_forms(lemma: str):
    forms = {lemma}
    if lemma in IRREGULAR_PLURALS:
        return forms | set(IRREGULAR_PLURALS[lemma])
    if lemma.endswith("y") and len(lemma) > 1 and lemma[-2] not in VOWELS:
        forms.add(lemma[:-1] + "ies")
    elif lemma.endswith(("s", "sh", "ch", "x", "z")):
        forms.add(lemma + "es")
    elif lemma.endswith("f"):
        forms.add(lemma[:-1] + "ves")
    else:
        forms.add(lemma + "s")
    return forms


def adj_forms(lemma: str):
    forms = {lemma}
    if lemma in IRREGULAR_ADJ:
        return forms | set(IRREGULAR_ADJ[lemma])
    if lemma.endswith("e"):
        forms |= {lemma[:-1] + "r", lemma[:-1] + "st"}
    elif lemma.endswith("y") and len(lemma) > 1 and lemma[-2] not in VOWELS:
        forms |= {lemma[:-1] + "ier", lemma[:-1] + "iest"}
    else:
        d = _double_consonant(lemma)
        stem = d if d else lemma
        forms |= {stem + "er", stem + "est"}
    # periphrastic handled at grammar level, not list level
    return forms


def adverb_forms(lemma: str):
    if lemma == "well":
        return {"well", "better", "best"}
    if lemma == "badly":
        return {"badly", "worse", "worst"}
    return {lemma}


POS_EXPANDERS = {
    "verb": verb_forms, "be-verb": verb_forms, "do-verb": verb_forms,
    "have-verb": verb_forms, "modal auxiliary": lambda w: {w},
    "noun": noun_forms, "number": lambda w: {w},
    "adjective": adj_forms, "adverb": adverb_forms,
    "determiner": lambda w: {w}, "pronoun": noun_forms,
    "conjunction": lambda w: {w}, "preposition": lambda w: {w},
    "interjection": lambda w: {w}, "infinitive-to": lambda w: {w},
}


def expand_headword(headword: str, pos: str):
    """Expand a dictionary headword into the surface forms to index."""
    pos = pos.strip().lower()
    hw = headword.strip().lower()
    expander = POS_EXPANDERS.get(pos)
    if expander is None:
        return {hw}
    return {f for f in expander(hw) if f and f.isascii()}
