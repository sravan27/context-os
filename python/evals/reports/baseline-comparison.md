# auto_context vs retrieval baselines

_Generated 2026-04-24T16:21:09+00:00 · same 32 prompts × 3 fixtures as main eval_

## Headline ranking

| Retrieval method | P@3 | R@3 | MRR | Coverage |
|---|---:|---:|---:|---:|
| **auto_context** | **0.703** | 0.682 | **0.969** | 1.000 |
| bm25-symbols | 0.578 | 0.656 | 0.875 | 0.969 |
| bm25-path | 0.557 | 0.552 | 0.714 | 0.812 |
| grep-count | 0.516 | 0.688 | 0.849 | 1.000 |
| naive-filename | 0.490 | 0.354 | 0.562 | 0.594 |
| random | 0.177 | 0.219 | 0.407 | 1.000 |

## Lift over each baseline

| Baseline | auto_context P@3 | baseline P@3 | ΔP@3 | auto_context MRR | baseline MRR | ΔMRR |
|---|---:|---:|---:|---:|---:|---:|
| bm25-symbols | 0.703 | 0.578 | **+0.125** | 0.969 | 0.875 | **+0.094** |
| bm25-path | 0.703 | 0.557 | **+0.146** | 0.969 | 0.714 | **+0.255** |
| grep-count | 0.703 | 0.516 | **+0.188** | 0.969 | 0.849 | **+0.120** |
| naive-filename | 0.703 | 0.490 | **+0.214** | 0.969 | 0.562 | **+0.406** |
| random | 0.703 | 0.177 | **+0.526** | 0.969 | 0.407 | **+0.562** |

## Per-baseline notes

### `auto_context`

Context-OS auto_context hook (full ranker)

| Fixture | P@3 | R@3 | MRR | Coverage |
|---|---:|---:|---:|---:|
| python | 0.708 | 0.694 | 1.000 | 1.000 |
| typescript | 0.733 | 0.700 | 0.950 | 1.000 |
| rust | 0.667 | 0.650 | 0.950 | 1.000 |

### `bm25-symbols`

BM25 over path + declared symbol names

| Fixture | P@3 | R@3 | MRR | Coverage |
|---|---:|---:|---:|---:|
| python | 0.472 | 0.653 | 0.833 | 0.917 |
| typescript | 0.783 | 0.750 | 1.000 | 1.000 |
| rust | 0.500 | 0.567 | 0.800 | 1.000 |

### `bm25-path`

BM25 over file path + basename tokens

| Fixture | P@3 | R@3 | MRR | Coverage |
|---|---:|---:|---:|---:|
| python | 0.514 | 0.597 | 0.708 | 0.750 |
| typescript | 0.667 | 0.567 | 0.800 | 0.900 |
| rust | 0.500 | 0.483 | 0.633 | 0.800 |

### `grep-count`

Raw term-occurrence count over (path, symbols)

| Fixture | P@3 | R@3 | MRR | Coverage |
|---|---:|---:|---:|---:|
| python | 0.417 | 0.597 | 0.722 | 1.000 |
| typescript | 0.683 | 0.817 | 0.900 | 1.000 |
| rust | 0.467 | 0.667 | 0.950 | 1.000 |

### `naive-filename`

Filename-token overlap (already in main eval)

| Fixture | P@3 | R@3 | MRR | Coverage |
|---|---:|---:|---:|---:|
| python | 0.431 | 0.389 | 0.583 | 0.583 |
| typescript | 0.550 | 0.317 | 0.600 | 0.600 |
| rust | 0.500 | 0.350 | 0.500 | 0.600 |

### `random`

Random shuffle (control — confirms eval is non-trivial)

| Fixture | P@3 | R@3 | MRR | Coverage |
|---|---:|---:|---:|---:|
| python | 0.056 | 0.083 | 0.260 | 1.000 |
| typescript | 0.233 | 0.267 | 0.561 | 1.000 |
| rust | 0.267 | 0.333 | 0.429 | 1.000 |

## Why this matters

BM25 is the *textbook* lexical baseline — it's what Elasticsearch and Lucene use for lexical search by default. If auto_context beats BM25 on the same lexical inputs, it's the import-graph traversal +
hot-file signal + test/hub penalty doing the extra work. That's
the claim to defend.

## Reproduce

```bash
python3 python/evals/runners/baseline_comparison.py
```
