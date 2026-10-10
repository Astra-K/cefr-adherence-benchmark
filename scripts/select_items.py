"""Select 30 benchmark items (24 everyday + 6 trap) from the ELL StackExchange
pool (real human learner questions, CC BY-SA 4.0), deterministically.

Selection is code, not vibes: filters are explicit, seed is fixed, provenance
is kept per item. Output: data/items.json
"""

import html
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

POOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw", "_pool.json")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "items.json")

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")

# topics that make a learner message an "everyday" scenario
EVERYDAY_HINTS = [
    "food", "eat", "cook", "hobby", "hobbies", "weekend", "holiday", "travel",
    "family", "friend", "school", "work", "job", "morning", "weather", "sport",
    "music", "movie", "book", "read", "walk", "city", "home", "shopping",
    "restaurant", "coffee", "tea", "breakfast", "dinner", "lunch", "greet",
    "introduce", "name", "birthday", "party", "garden", "dog", "cat", "pet",
    "bus", "train", "direction", "hotel", "airport", "phone", "email",
]

# specialized domains -> trap candidates (tutor must explain at target level)
TRAP_HINTS = [
    "law", "legal", "court", "attorney", "constitution", "lawsuit", "sue",
    "medical", "medicine", "diagnosis", "symptom", "doctor", "pharmacy",
    "insurance", "contract", "mortgage", "tax", "investment", "stock",
    "chemistry", "physics", "biology", "engineering", "software", "algorithm",
    "patent", "bureaucracy", "parliament", "election", "diploma", "thesis",
    "academic", "jargon", "technical", "terminology",
]


def clean_body(b):
    t = TAG_RE.sub(" ", html.unescape(b or ""))
    return WS_RE.sub(" ", t).strip()


def classify(item):
    text = (item.get("title", "") + " " + item.get("body_text", "")).lower()
    has_everyday = any(h in text for h in EVERYDAY_HINTS)
    trap_hits = [h for h in TRAP_HINTS if h in text]
    return has_everyday, trap_hits


def main():
    pool = json.load(open(POOL))
    rng = random.Random(42)

    cand = []
    for it in pool:
        body = clean_body(it.get("body_text", ""))
        title = clean_body(it.get("title", ""))
        # constraints: self-contained, not too long, not site-meta
        if not (40 <= len(body) <= 320):
            continue
        if re.search(r"stack exchange|stackexchange|this site|ell\.stack|closed|duplicate", body, re.I):
            continue
        if re.search(r"grammar term|part of speech|punctuation|comma|apostrophe", title, re.I):
            continue  # meta-linguistic grammar-term questions: keep scenarios human
        it2 = dict(it)
        it2["body_text"] = body
        it2["title"] = title
        cand.append(it2)

    everyday, traps = [], []
    for it in cand:
        has_ev, trap_hits = classify(it)
        if len(trap_hits) >= 1 and (len(body := it["body_text"])) :
            traps.append(it)
        elif has_ev:
            everyday.append(it)

    # dedupe by question_id
    def dedupe(xs):
        seen = set()
        out = []
        for x in xs:
            if x["question_id"] not in seen:
                seen.add(x["question_id"])
                out.append(x)
        return out

    everyday, traps = dedupe(everyday), dedupe(traps)
    rng.shuffle(everyday)
    rng.shuffle(traps)

    chosen_ev = everyday[:24]
    chosen_tr = traps[:6]
    # if not enough traps, top up with highest-score specialized-ish items
    if len(chosen_tr) < 6:
        for it in sorted(cand, key=lambda x: -x.get("score", 0)):
            if it not in chosen_tr and it.get("question_id") not in {c["question_id"] for c in chosen_ev}:
                chosen_tr.append(it)
            if len(chosen_tr) == 6:
                break

    items = []
    for kind, group in [("everyday", chosen_ev), ("trap", chosen_tr)]:
        for it in group:
            items.append({
                "id": f"{kind[0]}{len([i for i in items if i['kind']==kind])+1:02d}",
                "kind": kind,
                "text": it["body_text"],
                "title": it["title"],
                "source": "ell.stackexchange.com",
                "question_id": it["question_id"],
                "link": it["link"],
                "score": it.get("score"),
                "license": "CC BY-SA 4.0",
            })

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(items, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"selected {len(items)} items ({sum(1 for i in items if i['kind']=='everyday')} everyday, {sum(1 for i in items if i['kind']=='trap')} trap)")
    for i in items:
        print(f"[{i['id']}|{i['kind']}] ({i['score']}) {i['text'][:110]}")


if __name__ == "__main__":
    main()
