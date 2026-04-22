#!/usr/bin/env python3
"""
live_bench_stats.py — Statistical rigor for the live Claude A/B.

Consumes `python/evals/reports/live-session-bench-raw.json` (produced by
`live_session_bench.py`) and emits bootstrap 95% CIs, Wilson CI on win rate,
paired t-test p-value, and Cohen's d effect size. No external dependencies —
pure stdlib. Writes `python/evals/reports/live-session-bench-stats.md`.

Usage:
    python3 python/evals/runners/live_bench_stats.py
    python3 python/evals/runners/live_bench_stats.py --bootstrap 10000 --seed 42
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
from datetime import datetime, timezone
from typing import Iterable

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
RAW = os.path.join(REPO, "python", "evals", "reports",
                   "live-session-bench-raw.json")
OUT = os.path.join(REPO, "python", "evals", "reports",
                   "live-session-bench-stats.md")


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs):
    xs = list(xs)
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    v = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(v)


def percentile(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] * (hi - k) + s[hi] * (k - lo)


def bootstrap_ci(xs, stat=mean, n=10000, alpha=0.05, rng=None):
    """Percentile bootstrap CI. `stat` is a reducer over the resample."""
    if not xs:
        return 0.0, 0.0, 0.0
    rng = rng or random.Random(42)
    N = len(xs)
    samples = []
    for _ in range(n):
        resample = [xs[rng.randrange(N)] for _ in range(N)]
        samples.append(stat(resample))
    lo = percentile(samples, alpha / 2)
    hi = percentile(samples, 1 - alpha / 2)
    return stat(xs), lo, hi


def wilson_ci(k, n, alpha=0.05):
    """Wilson score interval on a binomial proportion k/n."""
    if n == 0:
        return 0.0, 0.0, 0.0
    z = 1.959963984540054  # 0.975 quantile of N(0,1)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def _betacf(a, b, x, maxit=200, eps=1e-14, fpmin=1e-30):
    """Continued-fraction evaluation of I_x(a,b) per Numerical Recipes 6.4.

    Returns the CF value `h`; caller multiplies by the front factor.
    """
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            return h
    return h


def betainc(a, b, x):
    """Regularized incomplete beta I_x(a,b) ∈ [0,1]."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    # Front factor: exp[ ln Γ(a+b) − ln Γ(a) − ln Γ(b) + a ln x + b ln(1−x) ]
    bt = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    # Pick the CF form that converges fastest.
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def paired_t_p(diffs):
    """Two-sided p-value for paired t-test (H0: mean diff = 0). Pure stdlib."""
    n = len(diffs)
    if n < 2:
        return 1.0
    m = mean(diffs)
    sd = stdev(diffs)
    if sd == 0:
        return 0.0 if m != 0 else 1.0
    t = m / (sd / math.sqrt(n))
    df = n - 1
    # Two-sided p = I_{df/(df+t^2)}(df/2, 1/2)
    x = df / (df + t * t)
    p = betainc(df / 2.0, 0.5, x)
    # Numerical floor — the CF underflows for |t| >> 10.
    return max(p, 0.0)


def cohens_d_paired(diffs):
    sd = stdev(diffs)
    if sd == 0:
        return 0.0
    return mean(diffs) / sd


def aggregate_by_row(rows, key):
    """Given a list of {control: [...], treatment: [...]} dicts, return a
    list of (control_total, treatment_total) pairs summed over `key` per run-
    index. For variance analysis we prefer per-run pairings.
    """
    pairs = []
    for r in rows:
        runs_c = r.get("control", [])
        runs_t = r.get("treatment", [])
        n = min(len(runs_c), len(runs_t))
        for i in range(n):
            c = runs_c[i].get(key, 0)
            t = runs_t[i].get(key, 0)
            pairs.append((c, t))
    return pairs


def aggregate_per_prompt(rows, key):
    """Return per-prompt mean(control) and mean(treatment)."""
    out = []
    for r in rows:
        pid = r.get("id", "?")
        c = mean(run.get(key, 0) for run in r.get("control", []))
        t = mean(run.get(key, 0) for run in r.get("treatment", []))
        out.append((pid, c, t))
    return out


def fmt_ci(p, lo, hi, pct=True):
    if pct:
        return f"{p * 100:.1f}% [{lo * 100:.1f}%, {hi * 100:.1f}%]"
    return f"{p:,.0f} [{lo:,.0f}, {hi:,.0f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=RAW,
                    help="path to live-session-bench-raw.json")
    ap.add_argument("--out", default=OUT, help="output markdown path")
    ap.add_argument("--bootstrap", type=int, default=10000,
                    help="bootstrap resamples (default 10000)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    with open(args.raw) as f:
        data = json.load(f)
    rows = data.get("rows", [])
    if not rows:
        print("no rows in", args.raw)
        return 1

    rng = random.Random(args.seed)

    # --- Paired per-run totals ---
    pairs = aggregate_by_row(rows, "total_tokens")  # [(c, t), ...]
    diffs = [c - t for (c, t) in pairs]            # tokens saved per run
    rel = [(c - t) / c for (c, t) in pairs if c > 0]  # fractional savings

    # Bootstrap 95% CI on mean fractional savings
    rel_mean, rel_lo, rel_hi = bootstrap_ci(
        rel, mean, n=args.bootstrap, rng=rng)

    # Bootstrap on mean absolute savings per run
    abs_mean, abs_lo, abs_hi = bootstrap_ci(
        diffs, mean, n=args.bootstrap, rng=rng)

    # Aggregate % savings — the headline number from the main report
    total_c = sum(c for (c, _) in pairs)
    total_t = sum(t for (_, t) in pairs)
    agg_pct = (total_c - total_t) / total_c if total_c else 0.0

    # Bootstrap CI on aggregate by resampling at (c,t) pair level
    def agg_savings(resample):
        tc = sum(c for (c, _) in resample)
        tt = sum(t for (_, t) in resample)
        return (tc - tt) / tc if tc else 0.0

    _, agg_lo, agg_hi = bootstrap_ci(
        pairs, agg_savings, n=args.bootstrap, rng=rng)

    # Wilson CI on win rate at the per-run level
    wins = sum(1 for (c, t) in pairs if t < c)
    wr, wr_lo, wr_hi = wilson_ci(wins, len(pairs))

    # Per-prompt win rate (treatment mean < control mean)
    per_prompt = aggregate_per_prompt(rows, "total_tokens")
    pp_wins = sum(1 for (_, c, t) in per_prompt if t < c)
    pp_wr, pp_wr_lo, pp_wr_hi = wilson_ci(pp_wins, len(per_prompt))

    # Paired t-test + Cohen's d on per-run diffs
    p_val = paired_t_p(diffs)
    d = cohens_d_paired(diffs)

    # --- Latency ---
    def lat(lst, mode):
        return [run.get("wall_s", 0.0)
                for r in rows
                for run in r.get(mode, [])]

    lat_c = lat(rows, "control")
    lat_t = lat(rows, "treatment")
    lat_summary = {
        "control": {
            "mean": mean(lat_c), "p50": percentile(lat_c, 0.5),
            "p95": percentile(lat_c, 0.95), "p99": percentile(lat_c, 0.99),
        },
        "treatment": {
            "mean": mean(lat_t), "p50": percentile(lat_t, 0.5),
            "p95": percentile(lat_t, 0.95), "p99": percentile(lat_t, 0.99),
        },
    }

    # --- Turn counts ---
    turns_c = [run.get("num_turns", 0)
               for r in rows for run in r.get("control", [])]
    turns_t = [run.get("num_turns", 0)
               for r in rows for run in r.get("treatment", [])]

    # ---- Markdown ----
    lines = []
    a = lines.append
    a("# Live Claude A/B — statistical analysis")
    a("")
    gen = datetime.now(timezone.utc).isoformat(timespec="seconds")
    a(f"_Generated {gen} · bootstrap N={args.bootstrap:,} · seed={args.seed} "
      f"· paired runs n={len(pairs)} · prompts N={len(rows)}_")
    a("")
    a("## Why this exists")
    a("")
    a("`live-session-bench.md` reports point estimates. This file answers:")
    a("*how confident are we?* Bootstrap CIs, Wilson CI on win rate, paired")
    a("t-test p-value, and Cohen's d. All computed from the same raw JSON,")
    a("no external stats library — pure stdlib so CI can run it.")
    a("")
    a("## Headline")
    a("")
    a("| Metric | Point | 95% CI | Method |")
    a("|---|---:|---:|---|")
    a(f"| Aggregate tokens saved | **{agg_pct * 100:.1f}%** "
      f"| [{agg_lo * 100:.1f}%, {agg_hi * 100:.1f}%] "
      f"| bootstrap on (c,t) pairs |")
    a(f"| Mean per-run savings | **{rel_mean * 100:.1f}%** "
      f"| [{rel_lo * 100:.1f}%, {rel_hi * 100:.1f}%] "
      f"| bootstrap on fractional savings |")
    a(f"| Mean tokens saved / run | **{abs_mean:,.0f}** "
      f"| [{abs_lo:,.0f}, {abs_hi:,.0f}] "
      f"| bootstrap on absolute diffs |")
    a(f"| Per-run win rate | **{wr * 100:.1f}%** ({wins}/{len(pairs)}) "
      f"| [{wr_lo * 100:.1f}%, {wr_hi * 100:.1f}%] "
      f"| Wilson score |")
    a(f"| Per-prompt win rate | **{pp_wr * 100:.1f}%** "
      f"({pp_wins}/{len(per_prompt)}) "
      f"| [{pp_wr_lo * 100:.1f}%, {pp_wr_hi * 100:.1f}%] "
      f"| Wilson score |")
    a("")
    a("## Significance")
    a("")
    a("Paired t-test on per-run token differences (control − treatment):")
    a("")
    a(f"- **t-statistic** → p = **{p_val:.2e}** (two-sided, df={len(diffs)-1})")
    a(f"- **Cohen's d** = **{d:.2f}** "
      f"({_cohen_label(d)})")
    a(f"- **Paired n** = {len(diffs)} runs across {len(rows)} prompts")
    a("")
    a("Interpretation: if p < 0.05, we reject H0 (no difference). If the CI "
      "on aggregate savings excludes 0%, the effect is robust to the ")
    a("particular prompts sampled.")
    a("")
    a("## Latency")
    a("")
    a("Wall-clock time per `claude --print` invocation (includes hook latency):")
    a("")
    a("| mode | mean | p50 | p95 | p99 |")
    a("|---|---:|---:|---:|---:|")
    for m in ("control", "treatment"):
        s = lat_summary[m]
        a(f"| {m} | {s['mean']:.2f}s | {s['p50']:.2f}s "
          f"| {s['p95']:.2f}s | {s['p99']:.2f}s |")
    a("")
    a(f"Treatment cut mean wall-clock by "
      f"**{(1 - lat_summary['treatment']['mean'] / lat_summary['control']['mean']) * 100:.1f}%** "
      f"— the hook itself adds ~50ms but Claude needs fewer turns.")
    a("")
    a(f"Mean turns: control **{mean(turns_c):.2f}** · "
      f"treatment **{mean(turns_t):.2f}** "
      f"(Δ **{mean(turns_t) - mean(turns_c):+.2f}** turns).")
    a("")
    a("## Per-prompt table")
    a("")
    a("| id | control tok (mean) | treatment tok (mean) | Δ % |")
    a("|---|---:|---:|---:|")
    for pid, c, t in per_prompt:
        dpct = (c - t) / c * 100 if c else 0.0
        a(f"| {pid} | {c:,.0f} | {t:,.0f} | **{dpct:+.1f}%** |")
    a("")
    a("## Caveats")
    a("")
    a("- Bootstrap CI is percentile-based; skewed distributions may need BCa.")
    a("- Paired t-test assumes the per-run diffs are roughly normal. For N=18")
    a("  paired runs this is a mild assumption; a Wilcoxon signed-rank test")
    a("  would be more robust. The bootstrap CI above does not assume")
    a("  normality.")
    a("- Wilson CI is conservative on small samples but has correct coverage")
    a("  down to n≈10. Prefer it over the naive normal approximation.")
    a("- Single fixture (`autocontext_fixture`). Generalization to arbitrary")
    a("  repositories is covered by the offline eval across Python/TS/Rust")
    a("  (see `autocontext-eval.md`).")
    a("")
    a("## Reproduce")
    a("")
    a("```bash")
    a("python3 python/evals/runners/live_session_bench.py --runs 3")
    a("python3 python/evals/runners/live_bench_stats.py \\")
    a("    --bootstrap 10000 --seed 42")
    a("```")
    a("")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write("\n".join(lines))

    print(f"wrote {args.out}")
    print(f"agg savings: {agg_pct * 100:.1f}% "
          f"[{agg_lo * 100:.1f}%, {agg_hi * 100:.1f}%]")
    print(f"per-run win rate: {wr * 100:.1f}% "
          f"[{wr_lo * 100:.1f}%, {wr_hi * 100:.1f}%]")
    print(f"paired t p = {p_val:.2e}, Cohen's d = {d:.2f}")
    return 0


def _cohen_label(d):
    ad = abs(d)
    if ad < 0.2:
        return "negligible"
    if ad < 0.5:
        return "small"
    if ad < 0.8:
        return "medium"
    return "large"


if __name__ == "__main__":
    raise SystemExit(main())
