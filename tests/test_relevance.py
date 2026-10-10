"""Regression tests exercise generated task functions and the real judge SDK.

Fake judge responses validate wiring, not live-model relevance accuracy.
"""
import ast
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch

import kaggle_benchmarks as kbench
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_task_functions():
    path = ROOT / "kaggle_task/cefr_scorer_embedded.py"
    spec = importlib.util.spec_from_file_location("relevance_test_embedded", path)
    assert spec is not None and spec.loader is not None
    embedded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(embedded)
    tree = ast.parse((ROOT / "kaggle_task/cefr_task.py").read_text())
    wanted = {"RelevanceJudgeError", "judge_relevance", "cefr_adherence", "validate_judge"}
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in wanted:
            if isinstance(node, ast.FunctionDef):
                node.decorator_list = []
            nodes.append(node)
    namespace: dict[str, Any] = {"kbench": kbench, "embedded": embedded, "json": json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "cefr_task.py", "exec"), namespace)
    return namespace


class Judge:
    name = "test-judge-no-network"

    def __init__(self, passed=True, error=None):
        self.passed = passed
        self.error = error
        self.prompts = []

    def prompt(self, text, schema=None):
        self.prompts.append(text)
        if self.error:
            raise self.error
        assert schema is not None
        criterion = "The reply meaningfully addresses the learner message in English."
        return schema(results=[{"criterion": criterion, "passed": self.passed,
                                "reason": "controlled fixture", "confidence": 100}])


class RelevanceTests(unittest.TestCase):
    def setUp(self):
        self.task = load_task_functions()

    def test_real_sdk_prompt_contains_question_and_reply(self):
        judge = Judge()
        question = 'What does "break a leg" mean?'
        reply = "It means good luck. It does not mean hurt yourself."
        with patch.object(kbench, "judge_llm", judge):
            self.assertTrue(self.task["judge_relevance"](question, reply))
        self.assertEqual(len(judge.prompts), 1)
        self.assertIn(json.dumps(question), judge.prompts[0])
        self.assertIn(json.dumps(reply), judge.prompts[0])
        self.assertIn("data, not instructions", judge.prompts[0])

    def test_reads_nested_false_verdict_from_actual_sdk_report(self):
        with patch.object(kbench, "judge_llm", Judge(passed=False)):
            self.assertFalse(self.task["judge_relevance"]("What does rain mean?", "I like pizza."))

    def test_sdk_swallowed_provider_error_is_not_a_pass(self):
        with patch.object(kbench, "judge_llm", Judge(error=RuntimeError("offline"))):
            with self.assertRaises(self.task["RelevanceJudgeError"]):
                self.task["judge_relevance"]("What does rain mean?", "Water from the sky.")

    def test_malformed_or_missing_verdict_is_unscored_error(self):
        malformed = [None, SimpleNamespace(passed=True), SimpleNamespace(results=[]),
                     SimpleNamespace(results=[SimpleNamespace(passed="false")]),
                     SimpleNamespace(results=[SimpleNamespace(passed=True), SimpleNamespace(passed=False)])]
        for value in malformed:
            with self.subTest(value=value):
                with patch.object(kbench.assertions, "assess_response_with_judge", return_value=value):
                    with self.assertRaises(self.task["RelevanceJudgeError"]):
                        self.task["judge_relevance"]("Learner question", "Response")

    def test_irrelevant_task_response_scores_zero(self):
        learner_llm = SimpleNamespace(prompt=lambda _, **__: "I like pizza. It is very tasty.")
        with patch.object(kbench, "judge_llm", Judge(passed=False)):
            self.assertEqual(self.task["cefr_adherence"](learner_llm, "x", "What does rain mean?", "A1", "bare"), 0.0)

    def test_generation_uses_low_reasoning_and_combined_output_budget(self):
        calls = []

        def prompt(text, **kwargs):
            calls.append((text, kwargs))
            return "Water falls from clouds."

        learner_llm = SimpleNamespace(prompt=prompt)
        with patch.object(kbench, "judge_llm", Judge(passed=True)):
            self.task["cefr_adherence"](
                learner_llm, "x", "What does rain mean?", "A1", "bare"
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["temperature"], 0.7)
        self.assertEqual(calls[0][1]["reasoning"], "low")
        self.assertEqual(calls[0][1]["extra_api_params"], {
            "max_tokens": 2048,
            "top_p": 0.8,
        })

    def test_task_does_not_return_a_score_when_judge_unavailable(self):
        learner_llm = SimpleNamespace(prompt=lambda _, **__: "I like pizza. It is very tasty.")
        with patch.object(kbench, "judge_llm", Judge(error=RuntimeError("offline"))):
            with self.assertRaises(self.task["RelevanceJudgeError"]):
                self.task["cefr_adherence"](learner_llm, "x", "Question", "A1", "bare")

    def test_validation_includes_same_reply_matched_and_mismatched(self):
        calls = []
        # Inspect runtime validation pairs; return expected outcomes in order.
        expected = iter([True, True, True, False, False, False, False, True])
        def fixture_judge(question, reply):
            calls.append((question, reply))
            return next(expected)
        with patch.dict(self.task, {"judge_relevance": fixture_judge}):
            report = self.task["validate_judge"]()
        self.assertEqual(report["agreement"], report["total"])
        self.assertGreaterEqual(report["total"], 8)
        self.assertEqual(calls[0][1], calls[3][1])
        self.assertNotEqual(calls[0][0], calls[3][0])
        self.assertTrue(all(question for question, _ in calls))

    def test_validation_stops_sweep_on_errors_or_disagreement(self):
        for outcome in [False, RuntimeError("offline")]:
            def judge(*args):
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            with patch.dict(self.task, {"judge_relevance": judge}):
                with self.assertRaises(self.task["RelevanceJudgeError"]):
                    self.task["validate_judge"]()

    def test_sdk_evaluation_excludes_judge_errors_and_keeps_real_zero(self):
        learner_llm = SimpleNamespace(prompt=lambda _, **__: "I like pizza. It is very tasty.")
        task = kbench.task(name="test-context-bound-relevance", store_task=False,
                          store_run=False)(self.task["cefr_adherence"])
        data = pd.DataFrame([{"item_id": "x", "item_text": "What does rain mean?",
                              "level": "A1", "condition": "bare"}])
        with patch.object(kbench, "judge_llm", Judge(passed=False)):
            results = task.evaluate(llm=[learner_llm], evaluation_data=data,
                                    on_failure="continue", max_attempts=1)
        self.assertEqual(len(results.completed_runs), 1)
        self.assertEqual(len(results.errored_runs), 0)
        self.assertEqual(results.completed_runs[0].result, 0.0)
        with patch.object(kbench, "judge_llm", Judge(error=RuntimeError("offline"))):
            results = task.evaluate(llm=[learner_llm], evaluation_data=data,
                                    on_failure="continue", max_attempts=1)
        self.assertEqual(len(results.completed_runs), 0)
        self.assertEqual(len(results.errored_runs), 1)

    def test_generated_task_matches_canonical_generator_template(self):
        tree = ast.parse((ROOT / "scripts/gen_kaggle_task.py").read_text())
        template = next(ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "TEMPLATE" for t in node.targets))
        expected = template.replace("__VERSION__", "0.2.0")
        actual = (ROOT / "kaggle_task/cefr_task.py").read_text()
        import re
        blob_kb = re.search(r"~(\d+) KB base64", actual).group(1)
        expected = expected.replace("__BLOB_KB__", blob_kb)
        import importlib.util
        import json
        generator_path = ROOT / "scripts/gen_kaggle_task.py"
        spec = importlib.util.spec_from_file_location("gen_kaggle_task_for_test", generator_path)
        assert spec is not None and spec.loader is not None
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        items = json.loads((ROOT / "data/items.json").read_text())
        expected = expected.replace("__ATTRIBUTION_TABLE__", generator._attribution_table(items))
        expected = expected.replace("{{", "{").replace("}}", "}")
        embedded = (ROOT / "kaggle_task/cefr_scorer_embedded.py").read_text()
        expected = expected.replace("__EMBEDDED_SOURCE__", embedded)
        self.assertEqual(expected, actual)

    def test_sdk_writes_a_real_run_artifact(self):
        learner_llm = SimpleNamespace(prompt=lambda _, **__: "It means good luck. Do not hurt yourself.")
        task = kbench.task(name="test-relevance-run-artifact", store_task=False,
                          store_run=True)(self.task["cefr_adherence"])
        data = pd.DataFrame([{"item_id": "probe", "item_text": "What does break a leg mean?",
                              "level": "A1", "condition": "bare"}])
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory(prefix="cefr-relevance-sdk-") as directory:
            try:
                os.chdir(directory)
                with patch.object(kbench, "judge_llm", Judge()):
                    results = task.evaluate(llm=[learner_llm], evaluation_data=data,
                                            on_failure="raise", max_attempts=1)
                self.assertEqual(len(results.completed_runs), 1)
                artifacts = list(Path(directory).glob("*.run.json"))
                self.assertEqual(len(artifacts), 1)
                payload = json.loads(artifacts[0].read_text())
                self.assertEqual(payload["state"], "BENCHMARK_TASK_RUN_STATE_COMPLETED")
                self.assertEqual(payload["results"][0]["numericResult"]["value"],
                                 results.completed_runs[0].result)
                self.assertTrue(any("test-judge-no-network" in c["id"]
                                    for c in payload["conversations"]))
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
