#!/usr/bin/env python3
"""
autocontext_eval.py — precision/recall/MRR benchmark for auto_context.py.

Pipeline:
  1. For each fixture (python, typescript, rust):
     - Build repo-graph on the fixture root.
     - For each hand-labeled prompt, pipe stdin JSON into auto_context.py.
     - Parse the emitted `<context-os:autocontext>` block for predicted files.
     - Compute per-prompt precision@3, recall@3, reciprocal rank (MRR).
  2. Optionally run `--baseline naive-filename` mode that ranks files purely
     by prompt-token substring overlap with the basename — establishes the
     trivial floor that auto_context must beat.
  3. Write per-fixture + aggregate markdown report.
  4. Exit non-zero if aggregate P@3 < threshold or MRR < threshold.

Zero-dep stdlib. Safe to run in CI.

Usage:
  python3 python/evals/runners/autocontext_eval.py
  python3 python/evals/runners/autocontext_eval.py --baseline naive-filename
  python3 python/evals/runners/autocontext_eval.py --fixture python   # only one
  python3 python/evals/runners/autocontext_eval.py --json              # machine-readable
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
PROMPTS = os.path.join(REPO_ROOT, "python", "evals", "autocontext_prompts.json")
BUILDER = os.path.join(REPO_ROOT, "hooks", "python", "build_repo_graph.py")
HOOK = os.path.join(REPO_ROOT, "hooks", "python", "auto_context.py")
REPORT_DIR = os.path.join(REPO_ROOT, "python", "evals", "reports")
REPORT = os.path.join(REPORT_DIR, "autocontext-eval.md")

K = 3  # top-K for precision/recall
SRC_EXTS = (".py", ".rs", ".js", ".ts", ".tsx", ".jsx", ".go", ".mjs", ".cjs")
FILE_RE = re.compile(
    r"`([A-Za-z0-9_\-/]+(?:\.[A-Za-z0-9_\-]+)*\.[A-Za-z]{1,5})(?::\d+)?`"
)
STOP = {
    "the", "a", "an", "to", "of", "and", "or", "in", "on", "for", "by",
    "with", "is", "are", "be", "so", "that", "this", "it", "at", "as",
    "from", "into", "per", "via", "not", "can", "should", "would", "could",
    "add", "make", "use", "using", "via", "new", "also", "then", "if",
    "when", "where", "which", "what", "who", "how", "does", "do", "did",
    "file", "files", "code", "codebase",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _is_path(s):
    return "/" in s and s.endswith(SRC_EXTS)


def build_graph(fixture):
    subprocess.run(
        [sys.executable, BUILDER, fixture],
        check=True, cwd=fixture,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def run_hook(prompt, fixture):
    event = json.dumps({
        "prompt": prompt,
        "session_id": "eval",
        "cwd": fixture,
    })
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=event, capture_output=True, text=True,
        cwd=fixture, timeout=10,
        env={**os.environ, "CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT": "1"},
    )
    return proc.stdout


def parse_predicted(block):
    if not block:
        return []
    predicted, seen = [], set()
    for m in FILE_RE.finditer(block):
        path = m.group(1)
        if not _is_path(path):
            continue
        if path not in seen:
            seen.add(path)
            predicted.append(path)
    return predicted


def tokenize(text):
    return [
        t.lower() for t in TOKEN_RE.findall(text)
        if t.lower() not in STOP and len(t) > 1
    ]


def baseline_naive_filename(prompt, fixture):
    """Rank files by how many prompt tokens appear in the basename (lowercased).
    Tie-break: shorter path first (more specific). Walks fixture source tree
    directly — does NOT use auto_context or the repo graph.
    """
    tokens = set(tokenize(prompt))
    if not tokens:
        return []
    scored = []
    for dirpath, dirnames, filenames in os.walk(fixture):
        dirnames[:] = [
            d for d in dirnames
            if d not in {"node_modules", "target", "dist", ".git",
                         ".context-os", "__pycache__", ".venv"}
            and not d.startswith(".")
        ]
        for fn in filenames:
            if not fn.endswith(SRC_EXTS):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), fixture)
            base = os.path.splitext(os.path.basename(fn))[0].lower()
            # split basename on non-alnum to get tokens (handles camelCase
            # via explicit splits on _, - and retains whole name too)
            base_tokens = set(re.split(r"[_\-.]", base)) | {base}
            # also include camelCase split
            for chunk in re.split(r"[_\-.]", base):
                base_tokens.update(
                    re.findall(r"[a-z]+|[A-Z][a-z]*", chunk)
                )
            base_tokens = {t.lower() for t in base_tokens if t}
            score = len(tokens & base_tokens)
            if score > 0:
                scored.append((score, -len(rel), rel))
    scored.sort(reverse=True)
    return [rel for _, _, rel in scored]


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


def eval_fixture(fix_id, fix_root_abs, prompts, mode):
    build_graph(fix_root_abs)
    rows = []
    for p in prompts:
        if mode == "auto_context":
            predicted = parse_predicted(run_hook(p["prompt"], fix_root_abs))
        elif mode == "naive-filename":
            predicted = baseline_naive_filename(p["prompt"], fix_root_abs)
        else:
            raise ValueError(f"unknown mode: {mode}")
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
    n = len(rows) or 1
    return {
        "id": fix_id,
        "mode": mode,
        "n": len(rows),
        "precision_at_k": sum(r["p_at_k"] for r in rows) / n,
        "recall_at_k": sum(r["r_at_k"] for r in rows) / n,
        "mrr": sum(r["rr"] for r in rows) / n,
        "coverage": sum(1 for r in rows if r["predicted"]) / n,
        "rows": rows,
    }


def aggregate(fixture_results):
    all_rows = [r for f in fixture_results for r in f["rows"]]
    n = len(all_rows) or 1
    return {
        "n": len(all_rows),
        "precision_at_k": sum(r["p_at_k"] for r in all_rows) / n,
        "recall_at_k": sum(r["r_at_k"] for r in all_rows) / n,
        "mrr": sum(r["rr"] for r in all_rows) / n,
        "coverage": sum(1 for r in all_rows if r["predicted"]) / n,
    }


def write_report(auto_results, auto_agg, baseline_results, baseline_agg,
                 generated_at):
    os.makedirs(REPORT_DIR, exist_ok=True)
    lines = [
        "# auto_context eval",
        "",
        f"_Generated {generated_at} · K={K} · "
        f"N={auto_agg['n']} prompts across {len(auto_results)} fixtures_",
        "",
        "## Aggregate (auto_context)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Precision@{K} | **{auto_agg['precision_at_k']:.3f}** |",
        f"| Recall@{K} | **{auto_agg['recall_at_k']:.3f}** |",
        f"| MRR | **{auto_agg['mrr']:.3f}** |",
        f"| Coverage (non-empty) | {auto_agg['coverage']:.3f} |",
        "",
    ]

    if baseline_results:
        lines += [
            "## Baseline vs auto_context (lift)",
            "",
            "Baseline = naive filename substring match. Ranks files purely by "
            "how many prompt tokens appear in the filename — no graph, no "
            "import traversal, no hot-file boost. This is the floor any "
            "useful static RAG must clear.",
            "",
            "| Fixture | Baseline P@3 | auto_context P@3 | Δ | Baseline MRR | auto_context MRR | Δ |",
            "|---|---|---|---|---|---|---|",
        ]
        auto_by_id = {r["id"]: r for r in auto_results}
        for b in baseline_results:
            a = auto_by_id[b["id"]]
            dp = a["precision_at_k"] - b["precision_at_k"]
            dm = a["mrr"] - b["mrr"]
            lines.append(
                f"| {b['id']} | {b['precision_at_k']:.3f} | "
                f"{a['precision_at_k']:.3f} | **{dp:+.3f}** | "
                f"{b['mrr']:.3f} | {a['mrr']:.3f} | **{dm:+.3f}** |"
            )
        dp = auto_agg["precision_at_k"] - baseline_agg["precision_at_k"]
        dm = auto_agg["mrr"] - baseline_agg["mrr"]
        lines.append(
            f"| **aggregate** | **{baseline_agg['precision_at_k']:.3f}** | "
            f"**{auto_agg['precision_at_k']:.3f}** | **{dp:+.3f}** | "
            f"**{baseline_agg['mrr']:.3f}** | **{auto_agg['mrr']:.3f}** | "
            f"**{dm:+.3f}** |"
        )
        lines.append("")

    lines += [
        "## Per-fixture (auto_context)",
        "",
        "| Fixture | N | P@3 | R@3 | MRR | Coverage |",
        "|---|---|---|---|---|---|",
    ]
    for f in auto_results:
        lines.append(
            f"| {f['id']} | {f['n']} | {f['precision_at_k']:.3f} | "
            f"{f['recall_at_k']:.3f} | {f['mrr']:.3f} | "
            f"{f['coverage']:.3f} |"
        )
    lines.append("")

    lines += ["## Per-prompt (auto_context)", ""]
    for f in auto_results:
        lines.append(f"### fixture: {f['id']}")
        lines.append("")
        lines.append("| id | P@K | R@K | RR | predicted (top-K) |")
        lines.append("|---|---|---|---|---|")
        for r in f["rows"]:
            preview = ", ".join(
                f"`{x}`" for x in r["predicted"][:K]
            ) or "_(none)_"
            lines.append(
                f"| {r['id']} | {r['p_at_k']:.2f} | {r['r_at_k']:.2f} | "
                f"{r['rr']:.2f} | {preview} |"
            )
        lines.append("")

    lines += [
        "## Fixtures",
        "",
        "Three parallel mini web-apps: `python`, `typescript`, `rust`. Each "
        "has the same module layout — auth/api/config/db/utils — with "
        "cross-module imports the graph builder must resolve per language. "
        "Ground truth hand-labeled: for each prompt, which files a "
        "competent engineer would open first.",
        "",
        "Prompts: `python/evals/autocontext_prompts.json`. "
        "Runner: `python/evals/runners/autocontext_eval.py`.",
        "",
        "Precision@K = fraction of top-K predicted files that are in expected.",
        "Recall@K = fraction of expected files present in top-K predicted.",
        "MRR = mean of 1/rank of first correct prediction (0 if none in top-K).",
        "",
    ]

    with open(REPORT, "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold-precision", type=float, default=0.55)
    ap.add_argument("--threshold-mrr", type=float, default=0.60)
    ap.add_argument("--fixture", default=None,
                    help="Only run this fixture id (python|typescript|rust).")
    ap.add_argument("--baseline", default=None, choices=["naive-filename"],
                    help="Also run a baseline for comparison + lift table.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    with open(PROMPTS) as f:
        spec = json.load(f)

    fixtures = spec["fixtures"]
    if args.fixture:
        fixtures = [x for x in fixtures if x["id"] == args.fixture]
        if not fixtures:
            sys.stderr.write(f"no fixture '{args.fixture}'\n")
            return 2

    auto_results = []
    for fx in fixtures:
        fix_root = os.path.join(REPO_ROOT, fx["root"])
        auto_results.append(
            eval_fixture(fx["id"], fix_root, spec["prompts"][fx["id"]],
                         "auto_context")
        )
    auto_agg = aggregate(auto_results)

    baseline_results, baseline_agg = None, None
    if args.baseline == "naive-filename":
        baseline_results = []
        for fx in fixtures:
            fix_root = os.path.join(REPO_ROOT, fx["root"])
            baseline_results.append(
                eval_fixture(fx["id"], fix_root, spec["prompts"][fx["id"]],
                             "naive-filename")
            )
        baseline_agg = aggregate(baseline_results)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_report(auto_results, auto_agg, baseline_results, baseline_agg,
                 generated_at)

    if args.json:
        out = {
            "generated_at": generated_at,
            "k": K,
            "auto_context": {
                "aggregate": auto_agg,
                "per_fixture": [
                    {k: v for k, v in f.items() if k != "rows"}
                    for f in auto_results
                ],
            },
        }
        if baseline_results:
            out["baseline"] = {
                "aggregate": baseline_agg,
                "per_fixture": [
                    {k: v for k, v in f.items() if k != "rows"}
                    for f in baseline_results
                ],
            }
        print(json.dumps(out, indent=2))
    else:
        line = (
            f"auto_context · N={auto_agg['n']} · "
            f"P@{K}={auto_agg['precision_at_k']:.3f} · "
            f"R@{K}={auto_agg['recall_at_k']:.3f} · "
            f"MRR={auto_agg['mrr']:.3f} · "
            f"coverage={auto_agg['coverage']:.3f}"
        )
        print(line)
        if baseline_agg:
            dp = auto_agg["precision_at_k"] - baseline_agg["precision_at_k"]
            dm = auto_agg["mrr"] - baseline_agg["mrr"]
            print(
                f"baseline   · P@{K}={baseline_agg['precision_at_k']:.3f} · "
                f"MRR={baseline_agg['mrr']:.3f}  "
                f"(lift: P@{K}={dp:+.3f}, MRR={dm:+.3f})"
            )
        print(f"report: {os.path.relpath(REPORT, REPO_ROOT)}")

    fail = []
    if auto_agg["precision_at_k"] < args.threshold_precision:
        fail.append(
            f"P@{K}={auto_agg['precision_at_k']:.3f} < "
            f"{args.threshold_precision}"
        )
    if auto_agg["mrr"] < args.threshold_mrr:
        fail.append(f"MRR={auto_agg['mrr']:.3f} < {args.threshold_mrr}")
    if fail:
        sys.stderr.write("FAIL: " + "; ".join(fail) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
