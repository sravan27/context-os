# auto_context latency benchmark

_Generated 2026-04-21T14:05:22+00:00 · runs per size varies, see table · prompt hits a real symbol in each repo_

## What this measures

Wall time of one `auto_context.py` invocation (stdlib JSON parse + regex scoring + graph lookup) across synthetic repos of increasing size. Graph build time is a separate column; this is amortized across sessions (built once, reused on every prompt).

Synthetic repos generated with cross-imports so the hook exercises symbol_index and imported_by lookups — not just a no-op fast path.

## Hook latency (per prompt)

| files | runs | mean | p50 | p95 | p99 | graph build | graph size |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 100 | 21.1ms | 20.9ms | 21.6ms | 23.0ms | 0.04s | 6 KB |
| 100 | 100 | 22.2ms | 22.1ms | 23.0ms | 23.3ms | 0.04s | 59 KB |
| 1,000 | 50 | 35.9ms | 35.6ms | 36.3ms | 45.5ms | 0.09s | 595 KB |
| 5,000 | 20 | 95.6ms | 95.3ms | 99.2ms | 103.6ms | 0.32s | 3000 KB |
| 10,000 | 20 | 170.3ms | 170.2ms | 172.6ms | 172.8ms | 0.62s | 6064 KB |

## Key observations

- **1000× more files → 8.0× p95 latency.** The ranker is close to linear in repo size; the graph is a dict lookup, so the dominant cost is scanning `files` for path-substring matches.
- **Largest repo (10,000 files) still under 173ms p99** — well under the 1000ms budget that would make a hook feel laggy. For comparison, LSP indexing on a
  repo this size takes 5–30 seconds.
- **Graph build scales ~linearly**: 0.04s → 0.62s for 1000× more files. The build is amortized across a whole session and runs in the background via `prewarm`.
- **Graph size stays small**: 5.9 MB at 10,000 files. Fits in memory trivially; cheap to ship.

## Budget analysis

Anthropic's `UserPromptSubmit` hook is synchronous — its wall time shows up in the first-turn latency the user sees. 50ms is
imperceptible; 200ms is noticeable; 500ms+ is unpleasant.

| Repo size | Hook p99 | User-visible feel |
|---|---:|---|
| 10 files | 23ms | imperceptible |
| 100 files | 23ms | imperceptible |
| 1,000 files | 45ms | imperceptible |
| 5,000 files | 104ms | noticeable |
| 10,000 files | 173ms | noticeable |

## Reproduce

```bash
python3 python/evals/runners/latency_bench.py
python3 python/evals/runners/latency_bench.py \
    --sizes 10,100,1000 --runs 200  # custom shape
```

Synthetic repos are deleted after each size — no residue on disk.
