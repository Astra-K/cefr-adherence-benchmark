"""OpenRouter harness: run the 180-prompt grid over selected models, score
offline with the IDENTICAL embedded scorer, save JSONL.

- Reads OPENROUTER_API_KEY from env (never committed).
- Fixed sampling (temperature 0.7, top_p 0.8, top_k 20), same prompts as local/Kaggle.
- This stage collects answers only; final_score stays None until judge_saved_answers.py.
- Logs context overflow / API errors SEPARATELY from adherence.
- Resumable: skips rows already present in the output JSONL.
- Spend-capped: stops when estimated spend exceeds SPEND_CAP_USD.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "kaggle_task"))

import cefr_scorer_embedded as emb  # identical scorer module as Kaggle task

from cefr_bench.prompts import bare_prompt, informed_prompt, est_tokens
from cefr_bench.wordlists import get_lists

OUT_DEFAULT = os.path.join(HERE, "..", "results", "openrouter_raw.jsonl")
MODELS_DEFAULT = ["qwen/qwen3.8-27b", "qwen/qwen3.8-flash"]

SPEND_CAP_USD = 15.0
TEMPERATURE = 0.7
MAX_TOKENS_OUT = 512
API = "https://openrouter.ai/api/v1/chat/completions"

# rough per-model pricing USD/M tokens (input, output) for cap estimation
PRICE = {
    "meta-llama/llama-3.2-1b-instruct:free": (0, 0),
    "google/gemma-2-2b-it:free": (0, 0),
    "meta-llama/llama-3.1-8b-instruct": (0.05, 0.05),
    "qwen/qwen-2.5-7b-instruct": (0.05, 0.05),
    "mistralai/mistral-small-3.2-24b-instruct": (0.10, 0.30),
    "google/gemini-2.0-flash-001": (0.10, 0.40),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "anthropic/claude-3.5-haiku": (0.80, 4.00),
    "openai/gpt-4o": (2.50, 10.00),
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
}


def call_openrouter(model, prompt, api_key, max_retries=3):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMPERATURE, "top_p": 0.8, "top_k": 20,
        "reasoning": {"enabled": False},
        "max_tokens": MAX_TOKENS_OUT,
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read())
            usage = data.get("usage", {})
            return {
                "reply": (data.get("choices") or [{}])[0].get("message", {}).get("content", ""),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "error": None,
            }
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}: {e.read()[:200].decode(errors='replace')}"
            if e.code in (429, 500, 502, 503) and attempt < max_retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return {"reply": None, "error": err,
                    "prompt_tokens": None, "completion_tokens": None}
        except Exception as e:  # noqa: BLE001
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return {"reply": None, "error": str(e),
                    "prompt_tokens": None, "completion_tokens": None}


def context_overflow(model, prompt):
    """Known small-context models: informed C1 prompts (~18k tokens) may not fit."""
    limit = MODEL_CONTEXT.get(model, 1_000_000)
    return est_tokens(prompt) > limit


MODEL_CONTEXT = {
    "meta-llama/llama-3.2-1b-instruct:free": 131_072,
    "google/gemma-2-2b-it:free": 8_192,
    "google/gemma-2-9b-it:free": 4_096,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=MODELS_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--cap", type=float, default=SPEND_CAP_USD)
    ap.add_argument("--dry-run", action="store_true",
                    help="estimate cost and grid size, call nothing")
    args = ap.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not args.dry_run and not api_key:
        sys.exit("OPENROUTER_API_KEY not set (read from env only)")

    items = emb.ITEMS
    wl = get_lists()

    # build the full grid
    grid = []
    for model in args.models:
        for it in items:
            for level in ("A1", "B1", "C1"):
                for cond in ("bare", "informed"):
                    grid.append((model, it, level, cond))

    done = set()
    if os.path.exists(args.out) and os.path.getsize(args.out) > 0:
        raise ValueError('Existing API output needs a dataset/protocol audit; use a fresh output path for the frozen pilot')

    # cost estimate
    est_cost = 0.0
    for model, it, level, cond in grid:
        if (model, it["id"], level, cond) in done:
            continue
        if cond == "informed":
            n_in = len(emb.informed_prompt(it["text"], level)) / 4
        else:
            n_in = 80
        pin, pout = PRICE.get(model, (1.0, 2.0))
        est_cost += (n_in * pin + 300 * pout) / 1e6

    print(f"grid: {len(grid)} rows total, {len(grid) - len(done)} to run "
          f"({len(done)} already done)")
    print(f"estimated additional spend: ${est_cost:.2f} (cap ${args.cap:.2f})")
    if args.dry_run:
        return
    if est_cost > args.cap:
        print("estimated spend exceeds cap — trim models and retry")
        return

    spent = 0.0
    with open(args.out, "a") as out:
        for i, (model, it, level, cond) in enumerate(grid):
            key = (model, it["id"], level, cond)
            if key in done:
                continue
            prompt = (informed_prompt(it["text"], level, wl) if cond == "informed"
                      else bare_prompt(it["text"], level))
            if context_overflow(model, prompt):
                out.write(json.dumps({
                    "model": model, "item_id": it["id"], "level": level,
                    "condition": cond, "reply": None,
                    "error": "context_overflow",
                    "prompt_est_tokens": est_tokens(prompt)}) + "\n")
                out.flush()
                continue
            res = call_openrouter(model, prompt, api_key)
            pin, pout = PRICE.get(model, (1.0, 2.0))
            pt = res.get("prompt_tokens") or 0
            ct = res.get("completion_tokens") or 0
            spent += (pt * pin + ct * pout) / 1e6
            out.write(json.dumps({
                "model": model, "item_id": it["id"], "level": level,
                "condition": cond, "prompt_est_tokens": est_tokens(prompt),
                "prompt_tokens": pt, "completion_tokens": ct,
                "reply": res["reply"], "error": res["error"],
                "item_text": it['text'], "question_id": it['question_id'],
                "dataset_sha256": __import__('hashlib').sha256(json.dumps(items, sort_keys=True).encode()).hexdigest(),
                "relevance": None, "final_score": None,
                "status": 'generated_relevance_pending' if not res['error'] else 'generation_error'}) + "\n")
            out.flush()
            if res["error"]:
                print(f"[{i+1}/{len(grid)}] {model} {level}/{cond}: ERROR {res['error'][:80]}")
            if spent > args.cap:
                print(f"spend cap reached (${spent:.2f}) — stopping")
                break
            time.sleep(0.6)  # gentle rate
    print(f"done; est spent ${spent:.2f}")


if __name__ == "__main__":
    main()
