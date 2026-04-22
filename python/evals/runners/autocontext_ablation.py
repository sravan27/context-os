#!/usr/bin/env python3
"""
autocontext_ablation.py — Signal ablation study for auto_context.

For each ranker signal, we disable it (via `CONTEXT_OS_AUTOCONTEXT_ABLATE`)
and re-run the offline eval against the same 32 hand-labeled prompts. The
delta in Precision@3 / MRR / Coverage tells us which signals matter, and
by how much.

This is how we answer the question "is the hot-file boost actually pulling
its weight?" without arguing from first principles.

Writes `python/evals/reports/autocontext-ablation.md`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
from autocontext_eval import (                                   # noqa: E402
    eval_fixture, aggregate, PROMPTS,
)

REPORT = os.path.join(REPO, "python", "evals", "reports",
                      "autocontext-ablation.md")

# Signals in the ranker, each identified by the token the hook understands.
# Display name + short description for the report.
SIGNALS = [
    ("symbol_exact",
     "Exact symbol match",
     "A token from the prompt equals a known function/class/const name "
     "(score +10)."),
    ("symbol_ci",
     "Case-insensitive symbol",
     "Same as above but case-folded (score +8, only fires when exact "
     "misses)."),
    ("path_exact",
     "Exact path / basename",
     "A token equals the path, ends with `/basename`, or is a path "
     "substring that includes a `/` (score +8)."),
    ("path_substr",
     "Path substring",
     "Token ≥5 chars appears anywhere in the file path (score +3)."),
    ("import",
     "Import traversal",
     "Token matches an imported module name; surfaces importers (score "
     "+5 per importer, capped at 3)."),
    ("hot",
     "Hot-file boost",
     "Boost files with high 90-day git touch counts (score +2)."),
    ("test_penalty",
     "Test-file penalty",
     "Down-weight `tests/test_*.py`, `*.spec.ts`, etc. unless the prompt "
     "asks about testing (score −3)."),
    ("hub_penalty",
     "Hub-file penalty",
     "Down-weight `mod.rs` / `__init__.py` / `index.ts` / `models.py` / "
     "`lib.rs` when not named in the prompt (score −2)."),
]


def load_fixtures_and_prompts():
    with open(PROMPTS) as f:
        cfg = json.load(f)
    fixtures = cfg.get("fixtures") or []
    by_fix = cfg.get("prompts") or {}
    out = []
    for fx in fixtures:
        fx_id = fx["id"]
        root_rel = fx["root"]
        root = os.path.join(REPO, root_rel)
        prompts = by_fix.get(fx_id) or []
        out.append((fx_id, root, prompts))
    return out


def run_eval(ablate, fixtures):
    env = os.environ.copy()
    env["CONTEXT_OS_AUTOCONTEXT_ABLATE"] = ",".join(ablate)
    # The eval runner uses subprocess.run with `env=` passed through; we need
    # to fork a subprocess so the env propagates. Easier: just spawn a new
    # python process that calls eval_fixture directly via a tiny driver.
    fx_results = []
    for (fx_id, root, prompts) in fixtures:
        if not prompts:
            continue
        payload = json.dumps({
            "fixture_id": fx_id,
            "fixture_root": root,
            "prompts": prompts,
        })
        out = subprocess.check_output(
            [sys.executable, os.path.join(HERE, "_ablation_child.py")],
            input=payload, text=True, env=env,
        )
        fx_results.append(json.loads(out))
    agg = aggregate(fx_results)
    return fx_results, agg


def write_report(baseline, ablations, generated_at):
    lines = []
    a = lines.append
    a("# auto_context — ranker ablation study")
    a("")
    a(f"_Generated {generated_at} · "
      f"prompts N={baseline['agg']['n']} across {len(baseline['per'])} "
      "fixtures_")
    a("")
    a("## Why this exists")
    a("")
    a("The ranker is 8 independent signals (6 positive, 2 negative). This "
      "study turns each one off and reruns the whole eval so we can see "
      "the per-signal contribution. Signals that barely move the numbers "
      "are candidates for removal (simpler is better); signals that move "
      "them a lot are load-bearing and must stay.")
    a("")
    a("Ablation = disable one signal only, keep the other 7 on. Reported "
      "deltas are `(ablated − full)` — a negative number means disabling "
      "that signal *hurt* (the signal was helping).")
    a("")
    a("## Headline")
    a("")
    a("Full ranker (all 8 signals):")
    a("")
    a("| Metric | Value |")
    a("|---|---:|")
    a(f"| Precision@3 | **{baseline['agg']['precision_at_k']:.3f}** |")
    a(f"| Recall@3 | **{baseline['agg']['recall_at_k']:.3f}** |")
    a(f"| MRR | **{baseline['agg']['mrr']:.3f}** |")
    a(f"| Coverage | **{baseline['agg']['coverage']:.3f}** |")
    a("")
    a("## Per-signal contribution")
    a("")
    a("Each row shows what happens when that ONE signal is disabled while")
    a("the rest stay on. Negative Δ = disabling hurts = signal is load-")
    a("bearing.")
    a("")
    a("| Signal | P@3 | ΔP@3 | MRR | ΔMRR | Coverage | ΔCov |")
    a("|---|---:|---:|---:|---:|---:|---:|")
    for key, name, _desc in SIGNALS:
        ab = ablations[key]
        dp = ab["agg"]["precision_at_k"] - baseline["agg"]["precision_at_k"]
        dm = ab["agg"]["mrr"] - baseline["agg"]["mrr"]
        dc = ab["agg"]["coverage"] - baseline["agg"]["coverage"]
        a(f"| {name} | {ab['agg']['precision_at_k']:.3f} | **{dp:+.3f}** "
          f"| {ab['agg']['mrr']:.3f} | **{dm:+.3f}** "
          f"| {ab['agg']['coverage']:.3f} | **{dc:+.3f}** |")
    a("")
    a("## Per-signal notes")
    a("")
    for key, name, desc in SIGNALS:
        ab = ablations[key]
        dm = ab["agg"]["mrr"] - baseline["agg"]["mrr"]
        a(f"### {name} (`{key}`)")
        a("")
        a(desc)
        a("")
        a(f"Disabling this signal changes MRR by **{dm:+.3f}**.")
        # Per-fixture breakdown
        a("")
        a("| Fixture | P@3 | MRR | Coverage |")
        a("|---|---:|---:|---:|")
        for f in ab["per"]:
            a(f"| {f['id']} | {f['precision_at_k']:.3f} "
              f"| {f['mrr']:.3f} | {f['coverage']:.3f} |")
        a("")
    a("## Interpretation")
    a("")
    a("- Signals that move MRR by ≥0.05 are load-bearing. Removing them is")
    a("  a regression.")
    a("- Signals that barely move the numbers (<0.01) are either redundant")
    a("  (their evidence is captured by another signal) or rare on this")
    a("  fixture set. They may still matter on bigger repos — we keep them")
    a("  if the cost of evaluating them is near-zero.")
    a("- A positive delta (disabling helps) means the signal is *hurting*")
    a("  on this eval. Investigate — either the weight is wrong or the")
    a("  signal fires on pathological cases.")
    a("")
    a("## Reproduce")
    a("")
    a("```bash")
    a("python3 python/evals/runners/autocontext_ablation.py")
    a("```")
    a("")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))
    return REPORT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=None,
                    help="also emit machine-readable JSON")
    args = ap.parse_args()

    fixtures = load_fixtures_and_prompts()

    # Baseline: all signals on.
    base_per, base_agg = run_eval([], fixtures)
    baseline = {"per": base_per, "agg": base_agg}

    # Per-signal ablation.
    ablations = {}
    for key, _name, _desc in SIGNALS:
        print(f"[ablation] disabling {key} ...", file=sys.stderr)
        per, agg = run_eval([key], fixtures)
        ablations[key] = {"per": per, "agg": agg}

    gen = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = write_report(baseline, ablations, gen)
    print(f"wrote {out}")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump({
                "generated_at": gen,
                "baseline": baseline,
                "ablations": ablations,
            }, f, indent=2)
        print(f"wrote {args.json_out}")

    # Summary
    print("\nheadline:")
    print(f"  full P@3 {base_agg['precision_at_k']:.3f} · "
          f"MRR {base_agg['mrr']:.3f}")
    for key, name, _desc in SIGNALS:
        ab = ablations[key]
        dm = ab["agg"]["mrr"] - base_agg["mrr"]
        marker = "load-bearing" if dm < -0.03 else (
            "marginal" if dm < 0 else "noise-or-hurts")
        print(f"  disable {key:14s}  ΔMRR {dm:+.3f}  ({marker})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
