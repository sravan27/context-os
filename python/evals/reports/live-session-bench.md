# Live Claude A/B — auto_context

_Generated 2026-04-19T14:52:58+00:00 · model `sonnet` · 3 run(s) per mode · N=6 prompts · cwd `/tmp/cos-livebench` · total cost $1.0403_

## What this measures

Real `claude --print --output-format json` calls, with and without the `auto_context` UserPromptSubmit hook active. Each prompt is run once per mode (or N times per mode with `--runs N`); same fixture, same model, same cold cache per call. Delta comes from Claude seeing the `<context-os:autocontext>` block (treatment) vs not (control) — everything else is identical.

## Per-prompt totals (mean across runs)

| id | control tok | treatment tok | Δ tok | Δ % | control $ | treatment $ | Δ $ |
|---|---:|---:|---:|---:|---:|---:|---:|
| p1-hash-password | 39,122 | 33,599 | **+5,523** | **+14.1%** | $0.0224 | $0.0197 | **$+0.0028** |
| p2-session-ttl | 46,870 | 22,716 | **+24,154** | **+51.5%** | $0.0396 | $0.0180 | **$+0.0216** |
| p3-rate-limit | 68,701 | 40,179 | **+28,522** | **+41.5%** | $0.0461 | $0.0336 | **$+0.0124** |
| p4-verify-password-bug | 50,564 | 33,865 | **+16,699** | **+33.0%** | $0.0231 | $0.0282 | **$-0.0051** |
| p5-migrations-add-col | 50,667 | 16,782 | **+33,885** | **+66.9%** | $0.0280 | $0.0260 | **$+0.0020** |
| p6-middleware-logging | 50,444 | 33,953 | **+16,491** | **+32.7%** | $0.0279 | $0.0342 | **$-0.0063** |

## Aggregate

| Metric | Value |
|---|---:|
| Total control tokens | **306,368** |
| Total treatment tokens | **181,093** |
| Total savings | **+125,275 tok (+40.9%)** |
| Median savings per prompt | **+37.3%** |
| Prompts where treatment < control | **6/6** |
| Total control cost | $0.1871 |
| Total treatment cost | $0.1597 |
| Total cost savings | **$+0.0273** |

## Caveats

- N=6 prompts. Small sample — individual prompt variance is high. Use `--runs N` to average multiple Claude invocations per mode and suppress single-call noise.
- Cold cache per call: Claude Code doesn't share cache between separate `--print` invocations, so each run pays full cache creation. This biases toward larger absolute numbers and smaller percentage deltas than a long interactive session would show.
- `claude --permission-mode bypassPermissions` lets the model actually run Read/Glob/Grep. Without this, the control arm can't explore and the bench is meaningless.
- Model and fixture held constant across arms. Only variable: `CONTEXT_OS_AUTOCONTEXT` env var (0 = hook installed but inert, 1 = hook emits the block).

## Reproduce

```bash
python3 python/evals/runners/live_session_bench.py \
  --cwd /tmp/cos-livebench \
  --model sonnet --runs 3
```

Raw per-call data: `python/evals/reports/live-session-bench-raw.json`.
