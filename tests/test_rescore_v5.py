"""Regression coverage for the parity-fixed v5 export."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rescore_v5_parity", ROOT / "scripts" / "rescore_v5_parity.py"
)
assert SPEC is not None
rescore = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(rescore)


def test_build_out_row_accepts_gate_failed_reply():
    row = {
        "key": "gate-fail",
        "model": "test-model",
        "level": "A1",
        "condition": "bare",
        "reply": "Only one sentence.",
        "relevance": True,
        "score": {"combined": 0.0},
    }

    exported = rescore.build_out_row(row)

    assert exported["new_combined_v5"] == 0.0
    assert exported["vocab"] is None
    assert exported["n_sentences"] == 1
