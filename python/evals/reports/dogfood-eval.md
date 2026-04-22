# auto_context — dogfood eval on the Context-OS repo

_Generated 2026-04-21T14:04:40+00:00 · N=15 prompts · repo has 49 source files, 440 indexed symbols_

## Why this exists

The three synthetic fixtures (Python/TypeScript/Rust) are small and
uniform by design — controlled conditions, hand-labeled ground truth.
This eval runs the same hook on a **real, heterogeneous repo**: the
Context-OS repo itself (49 source files, 440 symbols,
multi-language). Closest we can get to 'does this work when you `cd`
into an actual codebase' without shipping live A/B dollars.

**Honest scope note.** These 15 prompts are deliberately a mix: some
name the file/symbol directly (`build-repo-graph`, `latency-bench`),
others are purely descriptive (`hook that blocks reading enormous
files`). auto_context is a *lexical* ranker — when prompts mention
filenames or declared symbols it wins cleanly; when they're abstract,
BM25 can tie or beat it because it doesn't apply extra penalties.
The report below shows both regimes side-by-side rather than
cherry-picking the friendly ones.

## Headline

| Metric | Value |
|---|---:|
| Precision@3 | **0.322** |
| Recall@3 | **0.933** |
| MRR | **0.800** |
| Top-1 accuracy | **0.667** |
| Coverage (non-empty) | **1.000** |

## Baselines on the same dogfood prompts

Same prompts, same graph, different rankers. Confirms the win isn't
an artifact of synthetic fixtures.

| Method | P@3 | R@3 | MRR | Top-1 | Coverage |
|---|---:|---:|---:|---:|---:|
| **auto_context** | **0.322** | 0.933 | **0.800** | 0.667 | 1.000 |
| bm25-symbols | 0.244 | 0.733 | 0.619 | 0.533 | 1.000 |
| bm25-path | 0.256 | 0.600 | 0.536 | 0.467 | 0.867 |
| grep-count | 0.111 | 0.333 | 0.283 | 0.133 | 1.000 |
| naive-filename | 0.322 | 0.533 | 0.483 | 0.400 | 0.867 |
| random | 0.000 | 0.000 | 0.061 | 0.000 | 1.000 |

### Lift over each baseline (on real-repo prompts)

| Baseline | auto_context MRR | baseline MRR | ΔMRR | auto_context P@3 | baseline P@3 | ΔP@3 |
|---|---:|---:|---:|---:|---:|---:|
| bm25-symbols | 0.800 | 0.619 | **+0.181** | 0.322 | 0.244 | **+0.078** |
| bm25-path | 0.800 | 0.536 | **+0.264** | 0.322 | 0.256 | **+0.067** |
| grep-count | 0.800 | 0.283 | **+0.517** | 0.322 | 0.111 | **+0.211** |
| naive-filename | 0.800 | 0.483 | **+0.317** | 0.322 | 0.322 | **+0.000** |
| random | 0.800 | 0.061 | **+0.739** | 0.322 | 0.000 | **+0.322** |

## Per-prompt (auto_context)

| id | expected | top-3 predicted | P@3 | RR |
|---|---|---|---:|---:|
| ranker-scoring-logic | `hooks/python/auto_context.py` | `hooks/python/auto_context.py`, `python/evals/runners/autocontext_eval.py`, `python/evals/runners/autocontext_ablation.py` | 0.33 | 1.00 |
| hub-file-penalty | `hooks/python/auto_context.py` | `python/__init__.py`, `python/evals/__init__.py`, `python/evals/scorers/__init__.py` | 0.00 | 0.00 |
| build-repo-graph | `hooks/python/build_repo_graph.py` | `hooks/python/build_repo_graph.py`, `crates/repo-memory/src/lib.rs`, `examples/sample-repos/mini-next/app/page.tsx` | 0.33 | 1.00 |
| live-session-bench | `python/evals/runners/live_session_bench.py` | `hooks/python/auto_context.py`, `python/evals/runners/live_session_bench.py`, `python/evals/runners/autocontext_eval.py` | 0.33 | 0.50 |
| session-replay-simulator | `python/evals/runners/session_replay.py` | `python/evals/runners/session_replay.py`, `crates/token-estimator/src/lib.rs` | 0.50 | 1.00 |
| autocontext-eval-pipeline | `python/evals/runners/autocontext_eval.py` | `hooks/python/auto_context.py`, `python/evals/runners/autocontext_eval.py`, `python/evals/runners/autocontext_ablation.py` | 0.33 | 0.50 |
| dedup-guard | `hooks/python/dedup_guard.py` | `hooks/python/dedup_guard.py`, `hooks/python/file_size_guard.py`, `hooks/python/loop_guard.py` | 0.33 | 1.00 |
| loop-guard | `hooks/python/loop_guard.py` | `hooks/python/loop_guard.py`, `hooks/python/file_size_guard.py`, `hooks/python/session_profile.py` | 0.33 | 1.00 |
| prewarm-session-start | `hooks/python/prewarm.py` | `hooks/python/prewarm.py`, `hooks/python/session_profile.py`, `hooks/python/auto_context.py` | 0.33 | 1.00 |
| file-size-guard | `hooks/python/file_size_guard.py` | `hooks/python/file_size_guard.py`, `hooks/python/dedup_guard.py`, `hooks/python/loop_guard.py` | 0.33 | 1.00 |
| ablation-study | `python/evals/runners/autocontext_ablation.py` | `python/evals/runners/_ablation_child.py`, `python/evals/runners/autocontext_ablation.py`, `python/evals/runners/autocontext_eval.py` | 0.33 | 0.50 |
| baseline-comparison | `python/evals/runners/baseline_comparison.py` | `python/evals/runners/baseline_comparison.py`, `python/evals/runners/autocontext_eval.py`, `python/evals/runners/_ablation_child.py` | 0.33 | 1.00 |
| latency-bench | `python/evals/runners/latency_bench.py` | `python/evals/runners/latency_bench.py`, `python/evals/runners/live_session_bench.py`, `hooks/python/build_repo_graph.py` | 0.33 | 1.00 |
| robustness-tests | `python/evals/runners/robustness_test.py` | `hooks/python/auto_context.py`, `python/evals/runners/robustness_test.py`, `python/evals/runners/autocontext_eval.py` | 0.33 | 0.50 |
| live-bench-stats | `python/evals/runners/live_bench_stats.py` | `python/evals/runners/live_bench_stats.py`, `python/evals/runners/live_session_bench.py`, `python/evals/runners/latency_bench.py` | 0.33 | 1.00 |

## Reproduce

```bash
python3 python/evals/runners/dogfood_eval.py
```

The eval builds a fresh graph on every run — no stale state carries
over between invocations.
