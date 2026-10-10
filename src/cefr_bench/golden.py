"""Golden set: 10 snippets per level (5 compliant, 5 with planted violations).
Ours (brief: golden set is hand-written by us). Each record:
{level, expect_adherent, violation: null|description, text}
Run: PYTHONPATH=src python3 -m pytest tests/ -q
"""

import json
import os

GOLDEN = [
    # ---------------- A1 compliant ----------------
    ("A1", True, None, "Hello! My name is Anna. I am from Brazil. I like music and I play the piano. Do you like music?"),
    ("A1", True, None, "Hi Tom! This is my dog. His name is Max. He is two years old. He likes to run in the park. He is very happy."),
    ("A1", True, None, "Good morning! The weather is nice today. It is sunny and warm. I want to walk to school. Do you want to come with me?"),
    ("A1", True, None, "Hi! I am new here. I live in a small house with my family. My mother cooks dinner every day. I like her food very much."),
    ("A1", True, None, "Hello Sara! Thank you for your letter. I am happy to read it. I go to English class on Monday. My teacher is very kind."),
    # ---------------- A1 violations ----------------
    ("A1", False, "vocab: B2+ words throughout", "Certainly! Your enquiry regarding temporal prepositions is quite fascinating. Utilising 'in' for enclosed spaces and 'at' for specific locations demonstrates remarkable linguistic sophistication."),
    ("A1", False, "vocab: unlisted advanced words", "Ah, the ubiquitous apostrophe! Its deployment after sibilants remains contentious among pedants. Orthographic conventions notwithstanding, consistency is paramount."),
    ("A1", False, "grammar: B2 inversion", "Never have I encountered such a perplexing query. Should you require further elucidation, do not hesitate to requisition assistance. Rarely does one stumble upon such intrigue."),
    ("A1", False, "syntax: very long sentences", "When you want to say where you work you should know that in English we use different prepositions depending on whether you are talking about the company as a place or as an institution because the meaning changes quite a lot in each case."),
    ("A1", False, "meta-talk + advanced vocab", "As an AI, I find your question fascinating. The orthographic conventions you reference reflect diachronic phonological erosion of the genitive suffix."),
    # ---------------- B1 compliant ----------------
    ("B1", True, None, "That's a good question! Both sentences are correct, but they mean slightly different things. When you work in a company, you talk about the place. When you work for a company, you talk about the job. I hope this helps you!"),
    ("B1", True, None, "Great example! We usually add 's to a name, like Alex's house. If the name ends with s, some people write Alex' house, but Alex's is more common today. Keep practicing and it will feel natural soon."),
    ("B1", True, None, "I understand why this confuses you. We say it is raining because the verb describes the weather, not an action. You could also say it is snowing or it is sunny. English uses it for weather in general."),
    ("B1", True, None, "What an interesting idiom! To break a leg means good luck, especially before a show or an exam. Your friend wanted to wish you success. It sounds strange, but actors have used it for many years."),
    ("B1", True, None, "Let me explain the difference. Use in for months and years, like in May or in 2020. Use on for days, like on Monday. Use at for exact times, like at six o'clock. Try writing three sentences to practice!"),
    # ---------------- B1 violations ----------------
    ("B1", False, "vocab: C1 words", "Undoubtedly, the distinction you've stumbled upon exemplifies the inherent arbitrariness of prepositional semantics, a perennial conundrum for L2 acquirers striving toward nativelike proficiency."),
    ("B1", False, "grammar: C1 constructions (inversion, participle)", "Should you wish to master these prepositions, immerse yourself in authentic corpora. Having internalised the collocational patterns, you will find the choices intuitive. Not until then will fluency materialise."),
    ("B1", False, "vocab: unlisted jargon", "The genitive apostrophe postdates the erosion of the Old English case system; its orthographic codification was driven by printers' conventions rather than phonological transparency."),
    ("B1", False, "syntax: extremely long sentence", "When you are choosing between in and for you have to think about whether you are describing a position inside a physical space or a relationship with an organisation because English speakers use these prepositions differently depending on whether the company is a place where you go every day or an abstract entity that employs you."),
    ("B1", False, "meta-talk + advanced", "As an AI language model, I must emphasise that diachronic linguistics renders this question fascinating, though the pedagogical implications merit considerable elaboration."),
    # ---------------- C1 compliant ----------------
    ("C1", True, None, "The distinction is subtle but consistent. 'In' suggests enclosed or volumetric spaces, whereas 'at' denotes a point, which is why we work in a building but at a company. Should further examples help, I'd gladly provide them; nuances like these rarely yield to rules alone."),
    ("C1", True, None, "What you've noticed is a genuine tension in English orthography. Convention favours Alex's even after final s, though classical names sometimes take the bare apostrophe. Consistency matters more than the choice itself, and most style guides now recommend the full 's throughout."),
    ("C1", True, None, "The idiom derives from theatre superstition, where wishing luck directly was thought to invite disaster. Similar taboos gave us expressions across European languages. Ironically, performers now say it casually, the ominous origin largely forgotten except by etymologists."),
    ("C1", True, None, "Your instinct is sound: both forms occur, but they distribute differently. Weather verbs take dummy it because rain functions as an unaccusative predicate rather than an agentive one. Whether that explanation helps or hinders, the pattern will become familiar with exposure."),
    ("C1", True, None, "The choice reflects a deeper pattern. English marks institutional allegiance with for and mere location with in, a distinction that has weakened in casual speech. Had the distinction disappeared entirely, your confusion would be justified; as it stands, nuance persists."),
    # ---------------- C1 violations ----------------
    ("C1", False, "below-level: A1-only vocab and syntax", "Hi! I am happy to help you. It is easy. You say in for a big thing and at for a small thing. I like English. It is fun. Do you like English too? English is my favorite subject at school."),
    ("C1", False, "meta-talk", "As an AI language model, I cannot provide personal opinions, but I can offer some perspective on this question. Great question! Let me know if you need anything else."),
    ("C1", False, "A1 syntax: choppy short sentences", "The word is in. Use in for cities. Use at for places. Use on for days. That is the rule. It is easy. Do the exercise now. Good luck!"),
    ("C1", False, "below-level grammar only", "I like English very much. English is good. Prepositions are hard but you can do it! I believe in you. Practice every day and you will be great."),
    ("C1", False, "empty-ish/one sentence + below-level", "Hi! It is in!"),
]


def load_golden():
    return [
        {"level": lv, "expect_adherent": exp, "violation": viol, "text": text}
        for (lv, exp, viol, text) in GOLDEN
    ]


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "golden.json")
    with open(out, "w") as f:
        json.dump(load_golden(), f, indent=2, ensure_ascii=False)
    from collections import Counter
    c = Counter((g["level"], g["expect_adherent"]) for g in load_golden())
    print("golden set:", dict(c))
