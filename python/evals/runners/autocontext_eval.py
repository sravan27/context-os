#!/usr/bin/env python3
"""
autocontext_eval.py — precision/recall/MRR benchmark for auto_context.py.

Pipeline:
  1. Build repo-graph on the fixture (python/evals/autocontext_fixture).
  2. For each hand-labeled prompt, pipe stdin JSON into auto_context.py.
  3. Parse the emitted `<context-os:autocontext>` block for predicted files.
  4. Compute per-prompt precision@3, recall@3, reciprocal rank (MRR).
  5. Write markdown report to python/evals/reports/autocontext-eval.md.
  6. Exit non-zero if P@3 < threshold (default 0.60) or MRR < 0.60.

Zero-dep stdlib. Safe to run in CI.

Usage:
  python3 python/evals/runners/autocontext_eval.py
  python3 python/evals/runners/autocontext_eval.py --threshold 0.7
  python3 python/evals/runners/autocontext_eval.py --json   # machine-readable
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
FIXTURE = os.path.join(REPO_ROOT, "python", "evals", "autocontext_fixture")
PROMPTS = os.path.join(REPO_ROOT, "python", "evals", "autocontext_prompts.json")
BUILDER = os.path.join(REPO_ROOT, "hooks", "python", "build_repo_graph.py")
HOOK = os.path.join(REPO_ROOT, "hooks", "python", "auto_context.py")
REPORT_DIR = os.path.join(REPO_ROOT, "python", "evals", "reports")
REPORT = os.path.join(REPORT_DIR, "autocontext-eval.md")

K = 3  # top-K for precision/recall
# Extract `path/to/file.ext[:lineno]` tokens. Must contain `/` (real path, not
# dotted module name) AND end in a recognized source extension.
SRC_EXTS = (".py", ".rs", ".js", ".ts", ".tsx", ".jsx", ".go", ".mjs", ".cjs")
FILE_RE = re.compile(
    r"`([A-Za-z0-9_\-/]+(?:\.[A-Za-z0-9_\-]+)*\.[A-Za-z]{1,5})(?::\d+)?`"
)


def _is_path(s):
    return "/" in s and s.endswith(SRC_EXTS)


def build_graph():
    """Rebuild graph inside the fixture so path keys match expected_files."""
    subprocess.run(
        [sys.executable, BUILDER, FIXTURE],
        check=True, cwd=FIXTURE,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def run_hook(prompt):
    event = json.dumps({
        "prompt": prompt,
        "session_id": "eval",
        "cwd": FIXTURE,
    })
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=event, capture_output=True, text=True,
        cwd=FIXTURE, timeout=10,
        env={**os.environ, "CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT": "1"},
    )
    return proc.stdout


def parse_predicted(block):
    """Parse ordered, de-duped file paths from the hook's output block."""
    if not block:
        return []
    predicted = []
    seen = set()
    for m in FILE_RE.finditer(block):
        path = m.group(1)
        if not _is_path(path):
            continue
        if path not in seen:
            seen.add(path)
            predicted.append(path)
    return predicted


def precision_at_k(predicted, expected, k):
    if not predicted:
        return 0.0
    top = predicted[:k]
    hits = sum(1 for p in top if p in expected)
    return hits / min(k, len(top))


def recall_at_k(predicted, expected, k):
    if not expected:
        return 0.0
    top = set(predicted[:k])
    hits = sum(1 for e in expected if e in top)
    return hits / len(expected)


def reciprocal_rank(predicted, expected):
    for i, p in enumerate(predicted, 1):
        if p in expected:
            return 1.0 / i
    return 0.0


def evaluate():
    with open(PROMPTS) as f:
        spec = json.load(f)

    build_graph()

    rows = []
    for p in spec["prompts"]:
        predicted = parse_predicted(run_hook(p["prompt"]))
        expected = p["expected_files"]
        rows.append({
            "id": p["id"],
            "prompt": p["prompt"],
            "expected": expected,
            "predicted": predicted,
            "p_at_k": precision_at_k(predicted, expected, K),
            "r_at_k": recall_at_k(predicted, expected, K),
            "rr": reciprocal_rank(predicted, expected),
        })

    n = len(rows)
    mean_p = sum(r["p_at_k"] for r in rows) / n if n else 0.0
    mean_r = sum(r["r_at_k"] for r in rows) / n if n else 0.0
    mrr = sum(r["rr"] for r in rows) / n if n else 0.0
    coverage = sum(1 for r in rows if r["predicted"]) / n if n else 0.0

    return {
        "n": n,
        "precision_at_k": mean_p,
        "recall_at_k": mean_r,
        "mrr": mrr,
        "coverage": coverage,
        "k": K,
        "rows": rows,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_report(result):
    os.makedirs(REPORT_DIR, exist_ok=True)
    lines = [
        "# auto_context eval",
        "",
        f"_Generated {result['generated_at']} · K={result['k']} · "
        f"N={result['n']} prompts_",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Precision@{result['k']} | **{result['precision_at_k']:.3f}** |",
        f"| Recall@{result['k']} | **{result['recall_at_k']:.3f}** |",
        f"| MRR | **{result['mrr']:.3f}** |",
        f"| Coverage (non-empty) | {result['coverage']:.3f} |",
        "",
        "Precision@K = fraction of top-K predicted files that are in expected.",
        "Recall@K = fraction of expected files present in top-K predicted.",
        "MRR = mean of 1/rank of first correct prediction (0 if none in top-K).",
        "",
        "## Per-prompt",
        "",
        "| id | P@K | R@K | RR | predicted (top-K) |",
        "|---|---|---|---|---|",
    ]
    for r in result["rows"]:
        preview = ", ".join(f"`{x}`" for x in r["predicted"][:K]) or "_(none)_"
        lines.append(
            f"| {r['id']} | {r['p_at_k']:.2f} | {r['r_at_k']:.2f} | "
            f"{r['rr']:.2f} | {preview} |"
        )
    lines.append("")
    lines.append("## Fixture")
    lines.append("")
    lines.append(
        "Realistic mini web-app: auth (login/session/middleware), api "
        "(router/rate_limit), config (settings/database), db "
        "(models/migrations/queries), utils (crypto/email/logging), "
        "plus importer-edge tests. 13 source files, 5 test files, ~30 "
        "symbols, genuine cross-file imports."
    )
    lines.append("")
    lines.append(
        "Ground truth was hand-labeled by enumerating which files a "
        "competent engineer would open first for each task. See "
        "`python/evals/autocontext_prompts.json`."
    )
    lines.append("")
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold-precision", type=float, default=0.60)
    ap.add_argument("--threshold-mrr", type=float, default=0.60)
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON to stdout.")
    args = ap.parse_args()

    result = evaluate()
    write_report(result)

    if args.json:
        # Strip per-row for compactness in CI logs.
        compact = {k: v for k, v in result.items() if k != "rows"}
        print(json.dumps(compact, indent=2))
    else:
        print(f"auto_context eval · N={result['n']} · "
              f"P@{K}={result['precision_at_k']:.3f} · "
              f"R@{K}={result['recall_at_k']:.3f} · "
              f"MRR={result['mrr']:.3f} · "
              f"coverage={result['coverage']:.3f}")
        print(f"report: {os.path.relpath(REPORT, REPO_ROOT)}")

    # CI gates
    fail = []
    if result["precision_at_k"] < args.threshold_precision:
        fail.append(
            f"P@{K}={result['precision_at_k']:.3f} < "
            f"{args.threshold_precision}"
        )
    if result["mrr"] < args.threshold_mrr:
        fail.append(f"MRR={result['mrr']:.3f} < {args.threshold_mrr}")
    if fail:
        sys.stderr.write("FAIL: " + "; ".join(fail) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
