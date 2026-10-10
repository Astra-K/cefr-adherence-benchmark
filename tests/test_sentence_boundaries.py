"""Quoted sentence boundaries must work in native and Kaggle scorers."""
import importlib.util
from pathlib import Path
import sys
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cefr_bench.tokenise import split_sentences


def embedded():
    spec = importlib.util.spec_from_file_location('sentence_test_embedded', ROOT/'kaggle_task/cefr_scorer_embedded.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('text,expected', [
    ('Say "cities." The next sentence follows.', ['Say "cities."', 'The next sentence follows.']),
    ('Say “cities.” The next sentence follows.', ['Say “cities.”', 'The next sentence follows.']),
    ('She said \'Go!\' Then she left.', ["She said 'Go!'", 'Then she left.']),
    ('It ended (like this.) The next follows.', ['It ended (like this.)', 'The next follows.']),
    ('He said "Go!"\nThen she left.', ['He said "Go!"', 'Then she left.']),
    ('An ordinary sentence. Another follows!', ['An ordinary sentence.', 'Another follows!']),
    ('Use "populace" as a noun, not an adjective.', ['Use "populace" as a noun, not an adjective.']),
])
def test_quoted_boundaries(text, expected):
    assert split_sentences(text) == expected
    assert embedded().split_sentences(text) == expected


def test_saved_c1_reply_no_longer_wrongly_fails_sentence_gate():
    text = ('The word "populace" is actually a noun, so you cannot use it as an adjective to modify "cities." '
            'The correct form you need is "populated," as in "the most populated cities." '
            'Your correspondent likely made a mistake, or perhaps they meant to say "the most populous cities," '
            'which is the proper adjectival form derived from the root word "populus." '
            'Therefore, you should avoid using "populace" in that specific sentence structure.')
    assert len(split_sentences(text)) == 4
    score = embedded().score_reply(text, 'C1')
    assert score['n_sentences'] == 4
    assert 'gate_fail' not in score['flags']
