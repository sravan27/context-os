# Live Claude A/B — statistical analysis

_Generated 2026-04-20T12:03:14+00:00 · bootstrap N=10,000 · seed=42 · paired runs n=18 · prompts N=6_

## Why this exists

`live-session-bench.md` reports point estimates. This file answers:
*how confident are we?* Bootstrap CIs, Wilson CI on win rate, paired
t-test p-value, and Cohen's d. All computed from the same raw JSON,
no external stats library — pure stdlib so CI can run it.

## Headline

| Metric | Point | 95% CI | Method |
|---|---:|---:|---|
| Aggregate tokens saved | **40.9%** | [32.7%, 48.9%] | bootstrap on (c,t) pairs |
| Mean per-run savings | **39.4%** | [29.9%, 48.5%] | bootstrap on fractional savings |
| Mean tokens saved / run | **20,879** | [15,852, 25,845] | bootstrap on absolute diffs |
| Per-run win rate | **88.9%** (16/18) | [67.2%, 96.9%] | Wilson score |
| Per-prompt win rate | **100.0%** (6/6) | [61.0%, 100.0%] | Wilson score |

## Significance

Paired t-test on per-run token differences (control − treatment):

- **t-statistic** → p = **5.06e-07** (two-sided, df=17)
- **Cohen's d** = **1.84** (large)
- **Paired n** = 18 runs across 6 prompts

Interpretation: if p < 0.05, we reject H0 (no difference). If the CI on aggregate savings excludes 0%, the effect is robust to the 
particular prompts sampled.

## Latency

Wall-clock time per `claude --print` invocation (includes hook latency):

| mode | mean | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| control | 11.80s | 10.89s | 18.80s | 27.00s |
| treatment | 7.64s | 7.71s | 11.29s | 11.91s |

Treatment cut mean wall-clock by **35.3%** — the hook itself adds ~50ms but Claude needs fewer turns.

Mean turns: control **3.44** · treatment **1.89** (Δ **-1.56** turns).

## Per-prompt table

| id | control tok (mean) | treatment tok (mean) | Δ % |
|---|---:|---:|---:|
| p1-hash-password | 39,122 | 33,599 | **+14.1%** |
| p2-session-ttl | 46,870 | 22,716 | **+51.5%** |
| p3-rate-limit | 68,701 | 40,179 | **+41.5%** |
| p4-verify-password-bug | 50,564 | 33,865 | **+33.0%** |
| p5-migrations-add-col | 50,667 | 16,782 | **+66.9%** |
| p6-middleware-logging | 50,444 | 33,953 | **+32.7%** |

## Caveats

- Bootstrap CI is percentile-based; skewed distributions may need BCa.
- Paired t-test assumes the per-run diffs are roughly normal. For N=18
  paired runs this is a mild assumption; a Wilcoxon signed-rank test
  would be more robust. The bootstrap CI above does not assume
  normality.
- Wilson CI is conservative on small samples but has correct coverage
  down to n≈10. Prefer it over the naive normal approximation.
- Single fixture (`autocontext_fixture`). Generalization to arbitrary
  repositories is covered by the offline eval across Python/TS/Rust
  (see `autocontext-eval.md`).

## Reproduce

```bash
python3 python/evals/runners/live_session_bench.py --runs 3
python3 python/evals/runners/live_bench_stats.py \
    --bootstrap 10000 --seed 42
```
