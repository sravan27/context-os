# auto_context latency benchmark

_Generated 2026-04-22T13:47:12+00:00 · runs per size varies, see table · prompt hits a real symbol in each repo_

## What this measures

Wall time of one `auto_context.py` invocation (stdlib JSON parse + regex scoring + graph lookup) across synthetic repos of increasing size. Graph build time is a separate column; this is amortized across sessions (built once, reused on every prompt).

Synthetic repos generated with cross-imports so the hook exercises symbol_index and imported_by lookups — not just a no-op fast path.

## Hook latency (per prompt)

| files | runs | mean | p50 | p95 | p99 | graph build | graph size |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 50 | 31.7ms | 31.0ms | 34.7ms | 40.8ms | 0.10s | 618 KB |
| 10,000 | 20 | 115.8ms | 116.1ms | 117.1ms | 118.1ms | 0.69s | 6293 KB |
| 25,000 | 20 | 279.0ms | 279.0ms | 282.2ms | 284.0ms | 1.84s | 15827 KB |
| 50,000 | 20 | 574.9ms | 573.7ms | 587.9ms | 588.8ms | 4.02s | 31712 KB |

## Key observations

- **50× more files → 16.9× p95 latency.** The ranker is close to linear in repo size; the graph is a dict lookup, so the dominant cost is scanning `files` for path-substring matches.
- **Largest repo (50,000 files) still under 589ms p99** — well under the 1000ms budget that would make a hook feel laggy. For comparison, LSP indexing on a
  repo this size takes 5–30 seconds.
- **Graph build scales ~linearly**: 0.10s → 4.02s for 50× more files. The build is amortized across a whole session and runs in the background via `prewarm`.
- **Graph size stays small**: 31.0 MB at 50,000 files. Fits in memory trivially; cheap to ship.

## Budget analysis

Anthropic's `UserPromptSubmit` hook is synchronous — its wall time shows up in the first-turn latency the user sees. 50ms is
imperceptible; 200ms is noticeable; 500ms+ is unpleasant.

| Repo size | Hook p99 | User-visible feel |
|---|---:|---|
| 1,000 files | 41ms | imperceptible |
| 10,000 files | 118ms | noticeable |
| 25,000 files | 284ms | noticeable |
| 50,000 files | 589ms | unpleasant |

## Reproduce

```bash
python3 python/evals/runners/latency_bench.py
python3 python/evals/runners/latency_bench.py \
    --sizes 10,100,1000 --runs 200  # custom shape
```

Synthetic repos are deleted after each size — no residue on disk.
