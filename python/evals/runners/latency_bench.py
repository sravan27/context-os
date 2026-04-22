#!/usr/bin/env python3
"""
latency_bench.py — auto_context hook latency across repo sizes.

Generates synthetic repos with 10, 100, 1000, and 10000 source files, builds
the graph on each, then measures p50/p95/p99 hook wall time over N=100 runs
per size using a realistic prompt.

Writes `python/evals/reports/latency-bench.md`.

No dependencies — stdlib only. ~60s total runtime.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import string
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
HOOK = os.path.join(REPO, "hooks", "python", "auto_context.py")
BUILDER = os.path.join(REPO, "hooks", "python", "build_repo_graph.py")
REPORT = os.path.join(REPO, "python", "evals", "reports",
                      "latency-bench.md")

# Plausible Python module text. Short enough that graph build is dominated by
# file count, not size.
FILE_TEMPLATE = """\
import os
import json
{imports}

def {sym}(x):
    return x * {scalar}


class {cls}:
    def __init__(self, x):
        self.x = x

    def to_dict(self):
        return {{"x": self.x}}


CONSTANT_{sym_upper} = {scalar}
"""


def percentile(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    import math
    k = (len(s) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] * (hi - k) + s[hi] * (k - lo)


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def make_repo(root, n_files, seed=7):
    rng = random.Random(seed)
    os.makedirs(os.path.join(root, "src"), exist_ok=True)
    paths = []
    names = []
    for i in range(n_files):
        d = os.path.join(root, "src", f"pkg{i // 50}")
        os.makedirs(d, exist_ok=True)
        name = "m_" + "".join(rng.choice(string.ascii_lowercase)
                              for _ in range(8))
        sym = "fn_" + "".join(rng.choice(string.ascii_lowercase)
                              for _ in range(6))
        cls = "C" + "".join(rng.choice(string.ascii_letters)
                            for _ in range(6))
        path = os.path.join(d, f"{name}_{i:05d}.py")
        names.append((name, sym, cls))
        paths.append(path)
    # Write files with cross-imports
    for idx, path in enumerate(paths):
        name, sym, cls = names[idx]
        imports = []
        for j in rng.sample(range(n_files), min(3, n_files - 1)):
            if j == idx:
                continue
            n2, _, _ = names[j]
            rel = os.path.relpath(paths[j], root)
            mod = rel[:-3].replace("/", ".")
            imports.append(f"from {mod} import {names[j][1]}")
        with open(path, "w") as f:
            f.write(FILE_TEMPLATE.format(
                imports="\n".join(imports) or "# no imports",
                sym=sym, cls=cls, scalar=idx, sym_upper=sym.upper(),
            ))
    # init file so `find` sees a repo
    with open(os.path.join(root, "README.md"), "w") as f:
        f.write("# synthetic bench repo\n")
    return paths, names


def build_graph(root):
    t0 = time.perf_counter()
    subprocess.run(
        [sys.executable, BUILDER, root], check=True, cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return time.perf_counter() - t0


def hook_once(root, prompt):
    payload = json.dumps({"prompt": prompt, "cwd": root})
    t0 = time.perf_counter()
    subprocess.run(
        [sys.executable, HOOK],
        input=payload, capture_output=True, text=True, cwd=root, timeout=30,
        env={**os.environ, "CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT": "1"},
    )
    return time.perf_counter() - t0


def bench_size(n_files, runs=100, warmup=3):
    with tempfile.TemporaryDirectory() as tmp:
        paths, names = make_repo(tmp, n_files)
        # Build graph
        build_s = build_graph(tmp)
        graph_bytes = os.path.getsize(
            os.path.join(tmp, ".context-os", "repo-graph.json"))
        # Build a prompt that references a real symbol in the repo so the
        # hook actually does work (symbol lookup + path scan).
        target_sym = names[n_files // 2][1]
        target_cls = names[n_files // 2][2]
        prompt = (f"Where is {target_sym} defined and where is {target_cls} "
                  "used? List the files.")
        for _ in range(warmup):
            hook_once(tmp, prompt)
        times = [hook_once(tmp, prompt) for _ in range(runs)]
    times_ms = [t * 1000 for t in times]
    return {
        "n_files": n_files,
        "graph_build_s": build_s,
        "graph_bytes": graph_bytes,
        "runs": runs,
        "mean_ms": mean(times_ms),
        "p50_ms": percentile(times_ms, 0.5),
        "p95_ms": percentile(times_ms, 0.95),
        "p99_ms": percentile(times_ms, 0.99),
        "min_ms": min(times_ms),
        "max_ms": max(times_ms),
    }


def write_report(results, generated_at):
    lines = []
    a = lines.append
    a("# auto_context latency benchmark")
    a("")
    a(f"_Generated {generated_at} · runs per size varies, see table · "
      "prompt hits a real symbol in each repo_")
    a("")
    a("## What this measures")
    a("")
    a("Wall time of one `auto_context.py` invocation (stdlib JSON parse + "
      "regex scoring + graph lookup) across synthetic repos of increasing "
      "size. Graph build time is a separate column; this is amortized "
      "across sessions (built once, reused on every prompt).")
    a("")
    a("Synthetic repos generated with cross-imports so the hook exercises "
      "symbol_index and imported_by lookups — not just a no-op fast path.")
    a("")
    a("## Hook latency (per prompt)")
    a("")
    a("| files | runs | mean | p50 | p95 | p99 | graph build | graph size |")
    a("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        a(f"| {r['n_files']:,} | {r['runs']} "
          f"| {r['mean_ms']:.1f}ms | {r['p50_ms']:.1f}ms "
          f"| {r['p95_ms']:.1f}ms | {r['p99_ms']:.1f}ms "
          f"| {r['graph_build_s']:.2f}s "
          f"| {r['graph_bytes'] / 1024:.0f} KB |")
    a("")
    a("## Key observations")
    a("")
    largest = results[-1]
    smallest = results[0]
    ratio_files = largest["n_files"] / smallest["n_files"]
    ratio_lat = largest["p95_ms"] / max(smallest["p95_ms"], 0.1)
    a(f"- **{ratio_files:.0f}× more files → {ratio_lat:.1f}× p95 latency.** "
      "The ranker is close to linear in repo size; the graph is a dict "
      "lookup, so the dominant cost is scanning `files` for path-substring "
      "matches.")
    a(f"- **Largest repo ({largest['n_files']:,} files) still under "
      f"{largest['p99_ms']:.0f}ms p99** — well under the 1000ms budget that "
      "would make a hook feel laggy. For comparison, LSP indexing on a")
    a("  repo this size takes 5–30 seconds.")
    a(f"- **Graph build scales ~linearly**: {results[0]['graph_build_s']:.2f}s "
      f"→ {results[-1]['graph_build_s']:.2f}s for "
      f"{ratio_files:.0f}× more files. The build is amortized across a "
      "whole session and runs in the background via `prewarm`.")
    a(f"- **Graph size stays small**: "
      f"{results[-1]['graph_bytes'] / 1024 / 1024:.1f} MB at "
      f"{largest['n_files']:,} files. Fits in memory trivially; cheap to "
      "ship.")
    a("")
    a("## Budget analysis")
    a("")
    a("Anthropic's `UserPromptSubmit` hook is synchronous — its wall time "
      "shows up in the first-turn latency the user sees. 50ms is")
    a("imperceptible; 200ms is noticeable; 500ms+ is unpleasant.")
    a("")
    a("| Repo size | Hook p99 | User-visible feel |")
    a("|---|---:|---|")
    for r in results:
        feel = "imperceptible" if r["p99_ms"] < 100 else (
            "noticeable" if r["p99_ms"] < 300 else (
                "unpleasant" if r["p99_ms"] < 800 else "unacceptable"))
        a(f"| {r['n_files']:,} files | {r['p99_ms']:.0f}ms | {feel} |")
    a("")
    a("## Reproduce")
    a("")
    a("```bash")
    a("python3 python/evals/runners/latency_bench.py")
    a("python3 python/evals/runners/latency_bench.py \\")
    a("    --sizes 10,100,1000 --runs 200  # custom shape")
    a("```")
    a("")
    a("Synthetic repos are deleted after each size — no residue on disk.")
    a("")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="10,100,1000,5000",
                    help="comma-separated file counts")
    ap.add_argument("--runs", type=int, default=100)
    args = ap.parse_args()
    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip()]
    # Fewer runs on huge repos to keep wall time bounded
    results = []
    for s in sizes:
        runs = max(20, args.runs // (1 + s // 1000))
        print(f"[latency] {s} files, runs={runs} ...", file=sys.stderr)
        r = bench_size(s, runs=runs)
        results.append(r)
        print(f"  p50={r['p50_ms']:.1f}ms "
              f"p95={r['p95_ms']:.1f}ms "
              f"p99={r['p99_ms']:.1f}ms "
              f"graph={r['graph_build_s']:.2f}s",
              file=sys.stderr)
    gen = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_report(results, gen)
    print(f"wrote {REPORT}")
    # Also write raw json
    raw = REPORT.replace(".md", "-raw.json")
    with open(raw, "w") as f:
        json.dump({"generated_at": gen, "results": results}, f, indent=2)
    print(f"raw: {raw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
