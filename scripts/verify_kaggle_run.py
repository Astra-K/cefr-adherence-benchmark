#!/usr/bin/env python3
"""Verify a downloaded Kaggle CEFR benchmark run and emit compact evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPLETED = "BENCHMARK_TASK_RUN_STATE_COMPLETED"
TERMINAL_RE = re.compile(r"[.!?](?:[\"'”’\)\]\*_`]*)$")


def load_embedded_scorer():
    path = ROOT / "kaggle_task" / "cefr_scorer_embedded.py"
    spec = importlib.util.spec_from_file_location("cefr_scorer_embedded", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import embedded scorer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unwrap_json(value: Any) -> Any:
    for _ in range(4):
        if not isinstance(value, str):
            return value
        value = json.loads(value)
    return value


def role_text(contents: list[dict[str, Any]], role: str) -> str:
    for content in contents:
        if content.get("role") != role:
            continue
        for part in content.get("parts", []):
            if "text" in part:
                return str(part["text"])
    raise ValueError(f"No text for role {role}")


def request_cost_usd(request: dict[str, Any]) -> float:
    metrics = request.get("metrics", {})
    nano = int(metrics.get("inputTokensCostNanodollars") or 0)
    nano += int(metrics.get("outputTokensCostNanodollars") or 0)
    return nano / 1_000_000_000


def build_grid(embedded) -> list[tuple[str, str, str, str]]:
    return [
        (item["id"], item["text"], level, condition)
        for item in embedded.ITEMS
        for level in ("A1", "B1", "C1")
        for condition in ("bare", "informed")
    ]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rows": len(rows),
        "mean_score": round(statistics.mean(row["score"] for row in rows), 4),
        "relevant": sum(row["relevant"] for row in rows),
        "adherent": sum(row["adherent"] for row in rows),
        "relevant_and_adherent": sum(row["relevant_and_adherent"] for row in rows),
        "zero_scores": sum(row["score"] == 0 for row in rows),
        "near_cap": sum(row["near_cap"] for row in rows),
        "nonterminal_near_cap": sum(
            row["near_cap"] and not row["terminal_ending"] for row in rows
        ),
        "short_near_cap": sum(
            row["near_cap"] and row["reply_words"] < 30 for row in rows
        ),
    }


def verify(run_dir: Path, output_dir: Path, expected_rows: int, cap: int) -> dict[str, Any]:
    embedded = load_embedded_scorer()
    grid = build_grid(embedded)
    files = list(run_dir.glob("*.run.json"))
    errors: list[Any] = []
    rows: list[dict[str, Any]] = []
    ids: list[int] = []
    definition = ""

    for path in files:
        match = re.search(r"run_param_id_(\d+)_", path.name)
        if match is None:
            errors.append([path.name, "missing_param_id"])
            continue
        param_id = int(match.group(1))
        ids.append(param_id)
        data = json.loads(path.read_text())
        definition = definition or str(data.get("taskVersion", {}).get("definition", ""))
        state = data.get("state")
        if state != COMPLETED:
            errors.append([param_id, "state", state])
            continue
        if not 0 <= param_id < len(grid):
            errors.append([param_id, "out_of_grid"])
            continue

        item_id, item_text, level, condition = grid[param_id]
        conversations = data.get("conversations", [])
        try:
            main = next(
                conversation
                for conversation in conversations
                if str(conversation.get("id", "")).startswith(
                    "cefr-adherence-benchmark-"
                )
            )
            judge = next(conversation for conversation in conversations if conversation is not main)
            main_request = main["requests"][0]
            judge_request = judge["requests"][0]
            reply = role_text(main_request["contents"], "CONTENT_ROLE_ASSISTANT")
            judge_payload = unwrap_json(
                role_text(judge_request["contents"], "CONTENT_ROLE_ASSISTANT")
            )
            relevant = bool(judge_payload["results"][0]["passed"])
        except Exception as exc:  # evidence parser must record malformed rows
            errors.append([param_id, "parse", type(exc).__name__, str(exc)])
            continue

        # Protobuf JSON omits the scalar default value 0.0. It is safe to decode
        # as zero only after COMPLETED state and independent score recomputation.
        numeric = data.get("results", [{}])[0].get("numericResult") or {}
        stored_score = float(numeric.get("value", 0.0))
        rescored = embedded.score_reply(reply, level, relevant=relevant)
        local_score = float(rescored["combined"])
        parity = round(stored_score, 4) == round(local_score, 4)
        if not parity:
            errors.append([param_id, "parity", stored_score, local_score])

        main_metrics = main_request.get("metrics", {})
        judge_metrics = judge_request.get("metrics", {})
        output_tokens = int(main_metrics.get("outputTokens") or 0)
        reply_clean = reply.rstrip()
        row = {
            "param_id": param_id,
            "item_id": item_id,
            "level": level,
            "condition": condition,
            "score": stored_score,
            "relevant": relevant,
            "adherent": bool(rescored.get("adherent")),
            "relevant_and_adherent": bool(relevant and rescored.get("adherent")),
            "main_input_tokens": int(main_metrics.get("inputTokens") or 0),
            "main_output_tokens": output_tokens,
            "judge_input_tokens": int(judge_metrics.get("inputTokens") or 0),
            "judge_output_tokens": int(judge_metrics.get("outputTokens") or 0),
            "reply_words": len(reply.split()),
            "reply_chars": len(reply),
            "near_cap": output_tokens >= cap - 16,
            "terminal_ending": bool(TERMINAL_RE.search(reply_clean)),
            "score_parity": parity,
            "main_cost_usd": request_cost_usd(main_request),
            "judge_cost_usd": request_cost_usd(judge_request),
        }
        rows.append(row)

    rows.sort(key=lambda row: row["param_id"])
    expected_ids = list(range(expected_rows))
    if sorted(ids) != expected_ids:
        errors.append(["param_ids", sorted(ids), expected_ids])
    if len(files) != expected_rows:
        errors.append(["file_count", len(files), expected_rows])
    if 'reasoning="low"' not in definition:
        errors.append(["definition", "missing reasoning=low"])
    expected_cap_text = f'"max_tokens": {cap}'
    if expected_cap_text not in definition:
        errors.append(["definition", f"missing max_tokens={cap}"])

    breakdowns = [
        {
            "level": level,
            "condition": condition,
            **summarize(
                [
                    row
                    for row in rows
                    if row["level"] == level and row["condition"] == condition
                ]
            ),
        }
        for level in ("A1", "B1", "C1")
        for condition in ("bare", "informed")
    ]
    summary = summarize(rows) if rows else {}
    summary.update(
        {
            "expected_rows": expected_rows,
            "files": len(files),
            "ids_complete": sorted(ids) == expected_ids,
            "completed_states": len(rows),
            "score_parity_rows": sum(row["score_parity"] for row in rows),
            "artifact_cost_usd": round(
                sum(row["main_cost_usd"] + row["judge_cost_usd"] for row in rows),
                9,
            ),
            "main_output_tokens_total": sum(row["main_output_tokens"] for row in rows),
            "main_output_tokens_median": statistics.median(
                row["main_output_tokens"] for row in rows
            ) if rows else None,
            "reply_words_median": statistics.median(row["reply_words"] for row in rows)
            if rows
            else None,
            "task_sha256": hashlib.sha256(
                (ROOT / "kaggle_task" / "cefr_task.py").read_bytes()
            ).hexdigest(),
            "remote_definition_sha256": hashlib.sha256(
                definition.encode("utf-8")
            ).hexdigest() if definition else None,
            "analysis_errors": errors,
        }
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    if rows:
        with (output_dir / "scored.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    with (output_dir / "breakdown.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(breakdowns[0]))
        writer.writeheader()
        writer.writerows(breakdowns)
    payload = {"summary": summary, "breakdowns": breakdowns}
    (output_dir / "verification.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    report = f"""# Kaggle live benchmark verification

- Rows: **{summary.get('rows', 0)}/{expected_rows}**
- Mean score: **{summary.get('mean_score', 'n/a')}**
- Relevant: **{summary.get('relevant', 0)}/{expected_rows}**
- Relevant and adherent: **{summary.get('relevant_and_adherent', 0)}/{expected_rows}**
- Score parity: **{summary.get('score_parity_rows', 0)}/{expected_rows}**
- Near combined {cap}-token cap: **{summary.get('near_cap', 0)}/{expected_rows}**
- Non-terminal endings near cap: **{summary.get('nonterminal_near_cap', 0)}/{expected_rows}**
- Short answers near cap: **{summary.get('short_near_cap', 0)}/{expected_rows}**
- Artifact-accounted cost: **${summary.get('artifact_cost_usd', 0):.6f}**
- Task SHA-256: `{summary.get('task_sha256', '')}`
- Verification errors: **{len(errors)}**

Near-cap counts are diagnostics, not automatic proof of truncation because the downloaded schema omits provider finish reasons. Inspect every flagged ending before publication.
"""
    (output_dir / "REPORT.md").write_text(report)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--expected-rows", type=int, default=180)
    parser.add_argument("--cap", type=int, default=1024)
    args = parser.parse_args()
    payload = verify(args.run_dir, args.output_dir, args.expected_rows, args.cap)
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 1 if payload["summary"]["analysis_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
