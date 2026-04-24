#!/usr/bin/env python3
"""
git_commit_eval.py — real-world evaluation using git history as labels.

Dogfood uses hand-labeled prompts. Synthetic fixtures use hand-labeled
prompts. The honest gap both share: *we wrote the ground truth*. A
critic could reasonably ask "did you pick prompts where auto_context
happens to win?"

This eval removes that degree of freedom. Queries and targets come
directly from the repo's commit history:

    query   = commit subject (+ body, if short)
    targets = source files changed in that commit

If a developer types a commit message that maps cleanly to its
changed files (which is exactly the well-formed case we're optimizing
for), the ranker should surface those files in its top-K.

Filters applied:
- Skip commits touching > 5 source files (refactors / merges — noisy).
- Skip commits touching 0 source files (docs-only / typo fixes).
- Skip commits where the message is < 15 chars.
- Skip commits where the subject is a version bump / release marker.
- Skip merge commits (2+ parents).
- Only count source-file targets whose paths still exist at HEAD.
- Cap to last N=150 commits by default.

Writes `python/evals/reports/git-commit-eval.md`.

Reproduce:
  python3 python/evals/runners/git_commit_eval.py
  python3 python/evals/runners/git_commit_eval.py --limit 50 --repo /path/to/other/repo
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_DEFAULT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
from autocontext_eval import (                                   # noqa: E402
    build_graph, run_hook, parse_predicted, baseline_naive_filename,
    precision_at_k, recall_at_k, reciprocal_rank, K, SRC_EXTS,
)
from baseline_comparison import (                                # noqa: E402
    baseline_bm25_path, baseline_bm25_symbols,
    baseline_grep_count, baseline_random,
)

REPORT_DEFAULT = os.path.join(
    REPO_DEFAULT, "python", "evals", "reports", "git-commit-eval.md")

# Commit subjects to skip (not informative queries).
SKIP_SUBJECT_RES = [
    re.compile(r"^\s*v?\d+\.\d+(\.\d+)?(\s|$)"),    # v2.6.0, 1.0
    re.compile(r"^\s*release\b", re.I),
    re.compile(r"^\s*bump\b", re.I),
    re.compile(r"^\s*merge\b", re.I),
    re.compile(r"^\s*revert\b", re.I),
    re.compile(r"^\s*wip\b", re.I),
    re.compile(r"^\s*fixup!", re.I),
    re.compile(r"^\s*squash!", re.I),
]


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True, text=True, check=False,
    )


def collect_commits(root, limit):
    """Return list of dicts: {sha, subject, body, files}.

    Format strategy: emit STX (0x02) as record-start marker and NUL
    (0x00) as field separator inside the commit metadata. Filenames
    arrive on their own lines after the pretty format (because of
    --name-only). Records are separated by `\\n\\n` by git default.
    We split on STX so bodies containing arbitrary text don't confuse
    the parser.
    """
    # Git substitutes %x02 / %x00 / %x03 at format time — keeps binary
    # markers out of subprocess argv (which rejects embedded NUL).
    fmt = "%x02%H%x00%s%x00%b%x03"
    proc = _git(root, "log", f"-{limit * 3}",
                "--no-merges", f"--pretty=format:{fmt}",
                "--name-only")
    if proc.returncode != 0:
        return []
    raw = proc.stdout
    commits = []
    # Each record is `\x02<sha>\x00<subject>\x00<body>\x03\n<files>\n\n`
    # Split by the record-start marker STX (0x02).
    records = raw.split("\x02")
    for rec in records:
        rec = rec.strip()
        if not rec:
            continue
        # Split metadata from filenames on ETX (\x03).
        if "\x03" in rec:
            meta, filepart = rec.split("\x03", 1)
        else:
            meta, filepart = rec, ""
        parts = meta.split("\x00", 2)
        if len(parts) < 2:
            continue
        sha = parts[0]
        subject = parts[1] if len(parts) > 1 else ""
        body = parts[2] if len(parts) > 2 else ""
        files = [ln.strip() for ln in filepart.splitlines()
                 if ln.strip() and ("/" in ln or "." in ln)]
        commits.append({
            "sha": sha[:12], "subject": subject.strip(),
            "body": body.strip(), "files": files,
        })
        if len(commits) >= limit * 3:
            break
    return commits


def filter_commit(c, existing_files):
    subject = c["subject"]
    if len(subject) < 15:
        return False, "subject<15"
    for r in SKIP_SUBJECT_RES:
        if r.search(subject):
            return False, "subject-skip"
    src = [f for f in c["files"]
           if any(f.endswith(e) for e in SRC_EXTS) and f in existing_files]
    if not src:
        return False, "no-src-files"
    if len(src) > 5:
        return False, "too-many-files"
    return True, src


def build_query(c):
    subj = c["subject"].strip()
    body = (c["body"] or "").strip()
    # Take first 2 body lines if short (keeps query focused).
    if body:
        body_lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        body_lines = body_lines[:2]
        if sum(len(x) for x in body_lines) < 200:
            return subj + " — " + " ".join(body_lines)
    return subj


def aggregate(rows):
    nn = len(rows) or 1
    return {
        "n": len(rows),
        "p_at_k": sum(r["p_at_k"] for r in rows) / nn,
        "r_at_k": sum(r["r_at_k"] for r in rows) / nn,
        "mrr": sum(r["rr"] for r in rows) / nn,
        "top1": sum(1 for r in rows if r["rr"] == 1.0) / nn,
        "coverage": sum(1 for r in rows if r["predicted"]) / nn,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=REPO_DEFAULT)
    ap.add_argument("--limit", type=int, default=150,
                    help="max commits to evaluate (after filtering)")
    ap.add_argument("--out", default=REPORT_DEFAULT)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    root = os.path.abspath(args.repo)
    print(f"[git-commit-eval] building graph on {root}", file=sys.stderr)
    build_graph(root)

    graph_path = os.path.join(root, ".context-os", "repo-graph.json")
    with open(graph_path) as f:
        graph = json.load(f)
    existing = set((graph.get("files") or {}).keys())
    n_files = len(existing)
    n_syms = len(graph.get("symbol_index") or {})

    commits = collect_commits(root, args.limit)
    cases = []
    skipped = {"subject<15": 0, "subject-skip": 0,
               "no-src-files": 0, "too-many-files": 0}
    for c in commits:
        ok, info = filter_commit(c, existing)
        if not ok:
            skipped[info] = skipped.get(info, 0) + 1
            continue
        cases.append({
            "sha": c["sha"],
            "query": build_query(c),
            "expected": info,
            "subject": c["subject"],
        })
        if len(cases) >= args.limit:
            break

    if not cases:
        print("[git-commit-eval] no eligible commits", file=sys.stderr)
        return 1

    import random as _random
    rng = _random.Random(7)

    methods = [
        ("auto_context",
         lambda q: parse_predicted(run_hook(q, root))),
        ("bm25-symbols",
         lambda q: baseline_bm25_symbols(q, root)),
        ("bm25-path",
         lambda q: baseline_bm25_path(q, root)),
        ("grep-count",
         lambda q: baseline_grep_count(q, root)),
        ("naive-filename",
         lambda q: baseline_naive_filename(q, root)),
        ("random",
         lambda q: baseline_random(q, root, rng)),
    ]
    method_results = {}
    for name, ranker in methods:
        rows = []
        for c in cases:
            predicted = ranker(c["query"])
            rows.append({
                "sha": c["sha"],
                "query": c["query"],
                "expected": c["expected"],
                "predicted": predicted,
                "p_at_k": precision_at_k(predicted, c["expected"], K),
                "r_at_k": recall_at_k(predicted, c["expected"], K),
                "rr": reciprocal_rank(predicted, c["expected"]),
            })
        method_results[name] = {"rows": rows, "agg": aggregate(rows)}

    ac = method_results["auto_context"]["agg"]
    rows = method_results["auto_context"]["rows"]
    gen = datetime.now(timezone.utc).isoformat(timespec="seconds")

    lines = []
    a = lines.append
    a("# auto_context — real-world git-commit eval")
    a("")
    a(f"_Generated {gen} · repo `{os.path.basename(root)}` · "
      f"{n_files} source files, {n_syms} symbols · "
      f"N={len(cases)} eligible commits_")
    a("")
    a("## Why this eval exists")
    a("")
    a("Dogfood and synthetic evals use **hand-labeled** prompts. A")
    a("skeptic can reasonably ask: did the authors pick prompts where")
    a("their ranker wins? This eval removes that degree of freedom.")
    a("")
    a("**Query** = the commit subject (plus short body if informative).  ")
    a("**Ground truth** = the source files that commit changed.")
    a("")
    a("Commits are the purest real-world query: they were written by the")
    a("developer at the moment they knew exactly what they were about to")
    a("change. No eval author ever saw these. If the ranker puts the")
    a("changed file at rank 1, that's a direct model of 'user types their")
    a("intent → Claude opens the right file first'.")
    a("")
    a("Filters applied (see `filter_commit()` for full list):")
    a("- skip commits touching > 5 source files (noisy refactors)")
    a("- skip commits touching 0 source files (docs-only)")
    a("- skip version bumps / merges / reverts / WIP")
    a("- only score targets whose paths still exist at HEAD")
    a("")
    a("## Headline")
    a("")
    a("| Metric | Value |")
    a("|---|---:|")
    a(f"| Commits evaluated | {ac['n']} |")
    a(f"| Precision@3 | **{ac['p_at_k']:.3f}** |")
    a(f"| Recall@3 | **{ac['r_at_k']:.3f}** |")
    a(f"| MRR | **{ac['mrr']:.3f}** |")
    a(f"| Top-1 accuracy | **{ac['top1']:.3f}** |")
    a(f"| Coverage (non-empty) | **{ac['coverage']:.3f}** |")
    a("")
    a("## Baselines on the same commit queries")
    a("")
    a("| Method | P@3 | R@3 | MRR | Top-1 | Coverage |")
    a("|---|---:|---:|---:|---:|---:|")
    order = ["auto_context", "bm25-symbols", "bm25-path", "grep-count",
             "naive-filename", "random"]
    for name in order:
        mr = method_results[name]["agg"]
        mark = "**" if name == "auto_context" else ""
        a(f"| {mark}{name}{mark} | {mark}{mr['p_at_k']:.3f}{mark} "
          f"| {mr['r_at_k']:.3f} | {mark}{mr['mrr']:.3f}{mark} "
          f"| {mr['top1']:.3f} | {mr['coverage']:.3f} |")
    a("")
    a("### Lift over each baseline")
    a("")
    a("| Baseline | auto_context MRR | baseline MRR | ΔMRR | "
      "auto_context Top-1 | baseline Top-1 | ΔTop-1 |")
    a("|---|---:|---:|---:|---:|---:|---:|")
    for name in order[1:]:
        b = method_results[name]["agg"]
        dm = ac["mrr"] - b["mrr"]
        dt = ac["top1"] - b["top1"]
        a(f"| {name} | {ac['mrr']:.3f} | {b['mrr']:.3f} "
          f"| **{dm:+.3f}** | {ac['top1']:.3f} | {b['top1']:.3f} "
          f"| **{dt:+.3f}** |")
    a("")
    a("## Skip accounting (filter transparency)")
    a("")
    a("| Reason | Count |")
    a("|---|---:|")
    for k, v in sorted(skipped.items(), key=lambda x: -x[1]):
        a(f"| {k} | {v} |")
    a("")
    a("## Sample cases (auto_context)")
    a("")
    a("First 10 eligible commits:")
    a("")
    a("| sha | subject | expected | top-1 predicted | RR |")
    a("|---|---|---|---|---:|")
    for r in rows[:10]:
        subj = r["query"].split(" — ")[0]
        if len(subj) > 48:
            subj = subj[:45] + "..."
        exp = ", ".join(f"`{x}`" for x in r["expected"][:2])
        if len(r["expected"]) > 2:
            exp += f" +{len(r['expected']) - 2}"
        pred = f"`{r['predicted'][0]}`" if r["predicted"] else "_(none)_"
        a(f"| `{r['sha']}` | {subj} | {exp} | {pred} | {r['rr']:.2f} |")
    a("")
    a("## Reproduce")
    a("")
    a("```bash")
    a("# Default: last 150 eligible commits from this repo")
    a("python3 python/evals/runners/git_commit_eval.py")
    a("")
    a("# Run against any other repo:")
    a("python3 python/evals/runners/git_commit_eval.py \\")
    a("    --repo /path/to/other/repo --limit 100")
    a("```")
    a("")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {args.out}")
    print(f"git-commit: N={ac['n']} P@3={ac['p_at_k']:.3f} "
          f"MRR={ac['mrr']:.3f} top1={ac['top1']:.3f}")
    if args.json_out:
        with open(args.json_out, "w") as fp:
            json.dump({
                "generated_at": gen,
                "repo": root,
                "n_files": n_files,
                "n_symbols": n_syms,
                "skipped": skipped,
                "methods": {name: {"agg": mr["agg"]}
                            for name, mr in method_results.items()},
            }, fp, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
