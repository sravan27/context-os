#!/usr/bin/env python3
"""
ranker_floor.py — regression gate for the auto_context ranker.

Runs the offline + dogfood + baseline-comparison evals and asserts
minimum MRR / P@3 / top-1 floors. Exits non-zero if any floor is
breached, so CI fails before a regression ships.

Rationale
---------
Retrieval quality is the single metric that justifies this project's
existence. Any PR that touches `auto_context.py`, `build_repo_graph.py`,
or the ranker weights gets gated on this file. Floors are set ~5%
below the latest green numbers to absorb expected noise from stdlib
dict-order changes and Python version drift, while catching any
material regression in a single run.

Thresholds (CI-enforced)
------------------------
Synthetic offline (3 languages, 32 hand-labeled prompts):
    MRR   ≥ 0.920     (current: 0.969)
    P@3   ≥ 0.640     (current: 0.703)

Dogfood (this repo, 15 real-developer prompts):
    MRR   ≥ 0.720     (current: 0.789)
    top-1 ≥ 0.580     (current: 0.667)

Baseline margin (must still beat every lexical baseline):
    auto_context MRR - bm25-symbols MRR   ≥ +0.060
    auto_context MRR - naive-filename MRR ≥ +0.300
    auto_context MRR - random MRR         ≥ +0.500

If any of these fail, the CI step red-lines with a unified diff so
the failing metric is obvious.

Reproduce locally:
    python3 python/evals/runners/ranker_floor.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Dict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
REPORTS = os.path.join(REPO, "python", "evals", "reports")

FLOORS = {
    "synthetic": {
        "mrr": 0.920,
        "p_at_k": 0.640,
    },
    "dogfood": {
        "mrr": 0.720,
        "top1": 0.580,
    },
    "baseline_margin": {
        "bm25-symbols": 0.060,
        "naive-filename": 0.300,
        "random": 0.500,
    },
}


def _run(cmd):
    rc = subprocess.run(cmd, cwd=REPO, check=False).returncode
    if rc != 0:
        print(f"[ranker_floor] eval failed: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(rc)


def _run_json(cmd, out_path):
    """Run an eval with --json-out and return parsed dict."""
    rc = subprocess.run(cmd + ["--json-out", out_path],
                        cwd=REPO, check=False).returncode
    if rc != 0:
        print(f"[ranker_floor] eval failed: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(rc)
    with open(out_path) as f:
        return json.load(f)


def _assert(label, actual, floor, comparator=">=", fails=None):
    passed = (actual >= floor) if comparator == ">=" else (actual <= floor)
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {label:42s}  actual={actual:.3f}  "
          f"floor={floor:.3f}")
    if not passed:
        fails.append(f"{label}: {actual:.3f} < {floor:.3f}")


def main() -> int:
    fails = []
    print("[ranker_floor] running evals...")

    # 1. Synthetic + baseline comparison (one runner produces both).
    base_out = os.path.join(REPORTS, "_ranker_floor_baseline.json")
    dog_out = os.path.join(REPORTS, "_ranker_floor_dogfood.json")

    # Re-run the offline + baseline eval with JSON output.
    _ = _run_json(
        ["python3", "python/evals/runners/baseline_comparison.py"],
        base_out,
    )
    base = json.load(open(base_out))
    dog = _run_json(
        ["python3", "python/evals/runners/dogfood_eval.py"], dog_out,
    )

    # 2. Check synthetic floors (auto_context aggregated across fixtures).
    print("\n[synthetic] offline retrieval (Python + TS + Rust fixtures)")
    ac = base["results"]["auto_context"]["agg"]
    synth_mrr = ac["mrr"]
    synth_pak = ac["precision_at_k"]
    _assert("synthetic MRR", synth_mrr,
            FLOORS["synthetic"]["mrr"], fails=fails)
    _assert("synthetic P@3", synth_pak,
            FLOORS["synthetic"]["p_at_k"], fails=fails)

    # 3. Check dogfood floors.
    print("\n[dogfood] this repo, 15 real-developer prompts")
    dog_ac = dog["methods"]["auto_context"]["agg"]
    _assert("dogfood MRR", dog_ac["mrr"],
            FLOORS["dogfood"]["mrr"], fails=fails)
    _assert("dogfood top-1", dog_ac["top1"],
            FLOORS["dogfood"]["top1"], fails=fails)

    # 4. Baseline margin — must still beat the lexical zoo (synthetic).
    print("\n[margin] auto_context vs lexical baselines (synthetic)")
    for bname, floor in FLOORS["baseline_margin"].items():
        bvals = base["results"].get(bname)
        if not bvals:
            continue
        b_mrr = bvals["agg"]["mrr"]
        delta = synth_mrr - b_mrr
        _assert(f"MRR lift over {bname}", delta, floor, fails=fails)

    # 5. Dogfood baseline margin — must beat bm25-symbols on real-repo
    #    prompts (not just synthetic).
    print("\n[margin] dogfood — real-repo prompts")
    dog_bm = dog["methods"].get("bm25-symbols", {}).get("agg", {})
    if dog_bm:
        delta = dog_ac["mrr"] - dog_bm["mrr"]
        _assert("dogfood MRR lift over bm25-symbols",
                delta, 0.080, fails=fails)

    # Cleanup intermediates.
    for p in (base_out, dog_out):
        try:
            os.remove(p)
        except OSError:
            pass

    print("\n" + "=" * 60)
    if fails:
        print(f"[ranker_floor] {len(fails)} FLOOR(S) BREACHED:")
        for f in fails:
            print(f"  - {f}")
        print("\nFix the ranker or (if intentional) lower the floor in")
        print("python/evals/runners/ranker_floor.py and document why in")
        print("the commit message.")
        return 2
    print("[ranker_floor] all floors held. retrieval quality OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
