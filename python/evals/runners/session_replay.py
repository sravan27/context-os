#!/usr/bin/env python3
"""
session_replay.py — deterministic token-savings proxy for auto_context.

Question: does auto_context actually save tokens on realistic "find + read"
flows, vs the naive approach of globbing, grepping, then reading files one
by one until you hit the relevant one?

Approach (deterministic, no real Claude calls):
  For each hand-labeled prompt:
    - without_auto_context: simulate Claude doing 1 Glob + 1 Grep + reading
      files in baseline (naive filename match) order until the first expected
      file is read.
    - with_auto_context: emit the auto_context block (cost = tokens of the
      block itself), then read files in the hook's predicted order until the
      first expected file is read.
  Token accounting:
    - Glob result: fixed 200 tok (list of fixture source files).
    - Grep result: fixed 500 tok (assume a handful of matching line hits).
    - Read result: file line count × 8 tok/line (rough industry heuristic).
    - auto_context block: measured exactly from the hook's stdout.
  Worst-case (no expected file found): read whole fixture (upper bound on
  cost in the without path).

Emits a markdown report comparing total tokens "read to answer" with and
without auto_context, plus per-prompt breakdown. Writes to
python/evals/reports/session-replay.md.

Zero-dep stdlib. Runs in a few seconds.
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
HOOK = os.path.join(REPO_ROOT, "hooks", "python", "auto_context.py")
BUILDER = os.path.join(REPO_ROOT, "hooks", "python", "build_repo_graph.py")
REPORT_DIR = os.path.join(REPO_ROOT, "python", "evals", "reports")
REPORT = os.path.join(REPORT_DIR, "session-replay.md")

SRC_EXTS = (".py", ".rs", ".js", ".ts", ".tsx", ".jsx", ".go", ".mjs", ".cjs")
FILE_RE = re.compile(
    r"`([A-Za-z0-9_\-/]+(?:\.[A-Za-z0-9_\-]+)*\.[A-Za-z]{1,5})(?::\d+)?`"
)
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
STOP = {
    "the", "a", "an", "to", "of", "and", "or", "in", "on", "for", "by",
    "with", "is", "are", "be", "so", "that", "this", "it", "at", "as",
    "from", "into", "per", "via", "not", "can", "should", "would", "could",
    "add", "make", "use", "using", "new", "also", "then", "if", "when",
    "where", "which", "what", "who", "how", "does", "do", "did", "file",
    "files", "code", "codebase",
}

# Token-cost model (deterministic, documented in report header).
GLOB_TOK = 200
GREP_TOK = 500
TOK_PER_LINE = 8


def _is_path(s):
    return "/" in s and s.endswith(SRC_EXTS)


def tokenize(text):
    return [
        t.lower() for t in TOKEN_RE.findall(text)
        if t.lower() not in STOP and len(t) > 1
    ]


def walk_sources(fixture):
    out = []
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
            out.append(rel)
    return out


def file_lines(fixture, rel):
    try:
        with open(os.path.join(fixture, rel), "r",
                  encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def read_cost(fixture, rel):
    return file_lines(fixture, rel) * TOK_PER_LINE


def build_graph(fixture):
    subprocess.run(
        [sys.executable, BUILDER, fixture],
        check=True, cwd=fixture,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def run_hook_block(prompt, fixture):
    event = json.dumps({
        "prompt": prompt, "session_id": "replay", "cwd": fixture,
    })
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=event, capture_output=True, text=True,
        cwd=fixture, timeout=10,
        env={**os.environ, "CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT": "1"},
    )
    return proc.stdout or ""


def parse_predicted(block):
    predicted, seen = [], set()
    for m in FILE_RE.finditer(block):
        path = m.group(1)
        if _is_path(path) and path not in seen:
            seen.add(path)
            predicted.append(path)
    return predicted


def approx_tokens(text):
    # Rough but stable: whitespace tokens × 1.3 approximates BPE count.
    if not text:
        return 0
    return int(len(text.split()) * 1.3)


def baseline_order(prompt, fixture):
    """Order files by naive filename token overlap with the prompt.
    Files with 0 overlap still appear in a deterministic fallback order
    (alphabetical) — Claude would eventually resort to enumerating."""
    tokens = set(tokenize(prompt))
    files = walk_sources(fixture)
    scored = []
    for rel in files:
        base = os.path.splitext(os.path.basename(rel))[0].lower()
        pieces = set(re.split(r"[_\-.]", base)) | {base}
        for chunk in re.split(r"[_\-.]", base):
            pieces.update(re.findall(r"[a-z]+|[A-Z][a-z]*", chunk))
        pieces = {p.lower() for p in pieces if p}
        overlap = len(tokens & pieces)
        scored.append((-overlap, len(rel), rel))
    scored.sort()
    return [rel for _, _, rel in scored]


def tokens_to_answer_without(prompt, fixture, expected):
    total = GLOB_TOK + GREP_TOK
    reads = []
    for rel in baseline_order(prompt, fixture):
        total += read_cost(fixture, rel)
        reads.append(rel)
        if rel in expected:
            return total, reads, True
    return total, reads, False  # never hit


def tokens_to_answer_with(prompt, fixture, expected):
    block = run_hook_block(prompt, fixture)
    block_cost = approx_tokens(block)
    predicted = parse_predicted(block)
    total = block_cost
    reads = []
    for rel in predicted:
        total += read_cost(fixture, rel)
        reads.append(rel)
        if rel in expected:
            return total, reads, True, block_cost
    # Fall through to baseline if auto_context's top-K all miss.
    for rel in baseline_order(prompt, fixture):
        if rel in reads:
            continue
        # Simulate Glob+Grep after auto_context failed to pinpoint.
        if len(reads) == len(predicted):  # pay the detection cost once
            total += GLOB_TOK + GREP_TOK
        total += read_cost(fixture, rel)
        reads.append(rel)
        if rel in expected:
            return total, reads, True, block_cost
    return total, reads, False, block_cost


def replay():
    with open(PROMPTS) as f:
        spec = json.load(f)

    per_prompt = []
    for fx in spec["fixtures"]:
        fix_root = os.path.join(REPO_ROOT, fx["root"])
        build_graph(fix_root)
        for p in spec["prompts"][fx["id"]]:
            exp = p["expected_files"]
            w_tok, w_reads, w_hit = tokens_to_answer_without(
                p["prompt"], fix_root, exp
            )
            a_tok, a_reads, a_hit, block_cost = tokens_to_answer_with(
                p["prompt"], fix_root, exp
            )
            per_prompt.append({
                "fixture": fx["id"],
                "id": p["id"],
                "without_tok": w_tok,
                "without_reads": len(w_reads),
                "without_hit": w_hit,
                "with_tok": a_tok,
                "with_reads": len(a_reads),
                "with_hit": a_hit,
                "block_cost": block_cost,
                "savings_tok": w_tok - a_tok,
                "savings_pct": (
                    (w_tok - a_tok) / w_tok if w_tok > 0 else 0.0
                ),
            })

    return per_prompt


def write_report(rows):
    os.makedirs(REPORT_DIR, exist_ok=True)
    n = len(rows) or 1
    total_without = sum(r["without_tok"] for r in rows)
    total_with = sum(r["with_tok"] for r in rows)
    median_without = sorted(r["without_tok"] for r in rows)[n // 2]
    median_with = sorted(r["with_tok"] for r in rows)[n // 2]
    median_savings_pct = sorted(r["savings_pct"] for r in rows)[n // 2]
    mean_block = sum(r["block_cost"] for r in rows) / n
    wins = sum(1 for r in rows if r["with_tok"] < r["without_tok"])
    first_read_hits = sum(
        1 for r in rows if r["with_reads"] == 1 and r["with_hit"]
    )

    gen = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Session-replay token savings",
        "",
        f"_Generated {gen} · N={n} prompts across 3 fixtures_",
        "",
        "## What this measures",
        "",
        "Tokens Claude would burn on the \"find + read\" portion of each "
        "task, with vs without `auto_context`. Deterministic simulator — no "
        "live model calls — so the numbers are reproducible in CI.",
        "",
        "### Cost model",
        "",
        f"- Glob call result: {GLOB_TOK} tok (fixed)",
        f"- Grep call result: {GREP_TOK} tok (fixed)",
        f"- File read: file line count × {TOK_PER_LINE} tok/line",
        "- auto_context block: exact token count of the emitted block "
        "(whitespace-split × 1.3)",
        "",
        "### Strategies",
        "",
        "- **without**: Glob + Grep, then read files in naive-filename "
        "match order until the first ground-truth file is read.",
        "- **with**: emit `auto_context` block, read files in predicted "
        "order until the first ground-truth file is read. If all top-K "
        "miss, fall back to the naive flow (paying Glob+Grep then).",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total tokens (without) | **{total_without:,}** |",
        f"| Total tokens (with auto_context) | **{total_with:,}** |",
        f"| Total savings | **{total_without - total_with:,} tok "
        f"({(total_without - total_with) / max(total_without, 1):.1%})** |",
        f"| Median tokens (without) | {median_without:,} |",
        f"| Median tokens (with) | {median_with:,} |",
        f"| Median savings per prompt | **{median_savings_pct:.1%}** |",
        f"| Mean auto_context block cost | {mean_block:.0f} tok |",
        f"| Prompts where with < without | **{wins}/{n}** |",
        f"| Prompts answered on first read (with) | **{first_read_hits}/{n}** |",
        "",
        "## Per-prompt",
        "",
        "| fixture | id | without (tok, reads) | with (tok, reads) | savings |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['fixture']} | {r['id']} | "
            f"{r['without_tok']:,} ({r['without_reads']}) | "
            f"{r['with_tok']:,} ({r['with_reads']}) | "
            f"**{r['savings_tok']:+,} ({r['savings_pct']:+.1%})** |"
        )
    lines.append("")
    lines += [
        "## Caveats",
        "",
        "- Simulated reads consume the whole file (matches current Claude "
        "Read default).",
        "- Fixtures are small — absolute numbers are smaller than real "
        "repos, but the relative gap is the point.",
        "- Worst case counted assumes Claude eventually reads every fixture "
        "file; in practice it would stop sooner.",
        "",
    ]
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold-wins", type=float, default=0.50,
                    help="Fail if fraction of prompts where auto_context "
                         "saves tokens is below this.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = replay()
    write_report(rows)

    n = len(rows) or 1
    total_without = sum(r["without_tok"] for r in rows)
    total_with = sum(r["with_tok"] for r in rows)
    wins = sum(1 for r in rows if r["with_tok"] < r["without_tok"])
    win_rate = wins / n

    if args.json:
        print(json.dumps({
            "n": n,
            "total_without": total_without,
            "total_with": total_with,
            "total_savings_pct": (total_without - total_with)
            / max(total_without, 1),
            "win_rate": win_rate,
        }, indent=2))
    else:
        print(
            f"replay · N={n} · without={total_without:,} tok · "
            f"with={total_with:,} tok · "
            f"savings={(total_without - total_with) / max(total_without, 1):.1%} · "
            f"wins={wins}/{n}"
        )
        print(f"report: {os.path.relpath(REPORT, REPO_ROOT)}")

    if win_rate < args.threshold_wins:
        sys.stderr.write(
            f"FAIL: win_rate={win_rate:.2%} < {args.threshold_wins:.2%}\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
