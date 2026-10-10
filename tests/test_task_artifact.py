"""Publication artifact tests for the generated Kaggle task."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_task_has_no_database_hostile_giant_lines():
    """Keep generated notebook cells away from backend text-column limits."""
    lines = (ROOT / "kaggle_task" / "cefr_task.py").read_text().splitlines()
    assert max(map(len, lines)) <= 1_000


def test_task_evaluate_receives_an_iterable_of_models():
    """SDK 0.6.1 requires an iterable even when evaluating one model."""
    path = ROOT / "kaggle_task" / "cefr_task.py"
    import ast

    tree = ast.parse(path.read_text())
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "evaluate"
    ]
    assert len(calls) == 1
    llm_keyword = next(keyword for keyword in calls[0].keywords if keyword.arg == "llm")
    assert isinstance(llm_keyword.value, ast.List)
    assert len(llm_keyword.value.elts) == 1
    max_attempts = next(keyword for keyword in calls[0].keywords if keyword.arg == "max_attempts")
    assert isinstance(max_attempts.value, ast.Constant)
    assert max_attempts.value.value == 1


def test_task_embeds_complete_visible_attribution_ledger():
    """The standalone notebook must not depend on an external notice file."""
    import json

    task_text = (ROOT / "kaggle_task" / "cefr_task.py").read_text()
    items = json.loads((ROOT / "data" / "items.json").read_text())
    assert "https://www.gnu.org/licenses/agpl-3.0.html" in task_text
    assert "Original title prepended" in task_text
    for item in items:
        assert item["id"] in task_text
        assert item["link"] in task_text
        assert item["license_url"] in task_text
        assert item["author"]["name"] in task_text
        assert item["author"]["url"] in task_text


def test_task_executes_when_it_is_the_only_project_file(tmp_path):
    """The file passed to `kaggle b t push -f` must not import repo siblings."""
    task = tmp_path / "cefr_task.py"
    task.write_bytes((ROOT / "kaggle_task" / "cefr_task.py").read_bytes())
    runner = tmp_path / "check_task.py"
    runner.write_text(
        """import ast
from pathlib import Path

path = Path('cefr_task.py')
tree = ast.parse(path.read_text())
kept = []
for node in tree.body:
    # Do not call the live judge or start the 180-row model sweep in this test.
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        fn = node.value.func
        if isinstance(fn, ast.Name) and fn.id == 'validate_judge':
            continue
        if isinstance(fn, ast.Attribute) and fn.attr == 'evaluate':
            continue
    kept.append(node)
namespace = {'__name__': 'isolated_kaggle_task'}
exec(compile(ast.Module(body=kept, type_ignores=[]), str(path), 'exec'), namespace)
assert len(namespace['ITEMS']) == 30
assert len(namespace['EVAL_DATA']) == 180
assert callable(namespace['cefr_adherence'])
print('isolated_task=PASS')
"""
    )
    completed = subprocess.run(
        [sys.executable, str(runner)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "isolated_task=PASS" in completed.stdout
