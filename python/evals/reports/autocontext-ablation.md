# auto_context — ranker ablation study

_Generated 2026-04-21T14:05:01+00:00 · prompts N=32 across 3 fixtures_

## Why this exists

The ranker is 8 independent signals (6 positive, 2 negative). This study turns each one off and reruns the whole eval so we can see the per-signal contribution. Signals that barely move the numbers are candidates for removal (simpler is better); signals that move them a lot are load-bearing and must stay.

Ablation = disable one signal only, keep the other 7 on. Reported deltas are `(ablated − full)` — a negative number means disabling that signal *hurt* (the signal was helping).

## Headline

Full ranker (all 8 signals):

| Metric | Value |
|---|---:|
| Precision@3 | **0.703** |
| Recall@3 | **0.682** |
| MRR | **0.969** |
| Coverage | **1.000** |

## Per-signal contribution

Each row shows what happens when that ONE signal is disabled while
the rest stay on. Negative Δ = disabling hurts = signal is load-
bearing.

| Signal | P@3 | ΔP@3 | MRR | ΔMRR | Coverage | ΔCov |
|---|---:|---:|---:|---:|---:|---:|
| Exact symbol match | 0.693 | **-0.010** | 0.969 | **+0.000** | 1.000 | **+0.000** |
| Case-insensitive symbol | 0.724 | **+0.021** | 0.969 | **+0.000** | 1.000 | **+0.000** |
| Exact path / basename | 0.682 | **-0.021** | 0.953 | **-0.016** | 1.000 | **+0.000** |
| Path substring | 0.672 | **-0.031** | 0.906 | **-0.062** | 0.938 | **-0.062** |
| Import traversal | 0.714 | **+0.010** | 0.969 | **+0.000** | 1.000 | **+0.000** |
| Hot-file boost | 0.703 | **+0.000** | 0.969 | **+0.000** | 1.000 | **+0.000** |
| Test-file penalty | 0.682 | **-0.021** | 0.969 | **+0.000** | 1.000 | **+0.000** |
| Hub-file penalty | 0.693 | **-0.010** | 0.964 | **-0.005** | 1.000 | **+0.000** |

## Per-signal notes

### Exact symbol match (`symbol_exact`)

A token from the prompt equals a known function/class/const name (score +10).

Disabling this signal changes MRR by **+0.000**.

| Fixture | P@3 | MRR | Coverage |
|---|---:|---:|---:|
| python | 0.708 | 1.000 | 1.000 |
| typescript | 0.733 | 0.950 | 1.000 |
| rust | 0.633 | 0.950 | 1.000 |

### Case-insensitive symbol (`symbol_ci`)

Same as above but case-folded (score +8, only fires when exact misses).

Disabling this signal changes MRR by **+0.000**.

| Fixture | P@3 | MRR | Coverage |
|---|---:|---:|---:|
| python | 0.750 | 1.000 | 1.000 |
| typescript | 0.733 | 0.950 | 1.000 |
| rust | 0.683 | 0.950 | 1.000 |

### Exact path / basename (`path_exact`)

A token equals the path, ends with `/basename`, or is a path substring that includes a `/` (score +8).

Disabling this signal changes MRR by **-0.016**.

| Fixture | P@3 | MRR | Coverage |
|---|---:|---:|---:|
| python | 0.681 | 1.000 | 1.000 |
| typescript | 0.667 | 0.950 | 1.000 |
| rust | 0.700 | 0.900 | 1.000 |

### Path substring (`path_substr`)

Token ≥5 chars appears anywhere in the file path (score +3).

Disabling this signal changes MRR by **-0.062**.

| Fixture | P@3 | MRR | Coverage |
|---|---:|---:|---:|
| python | 0.708 | 0.917 | 0.917 |
| typescript | 0.717 | 0.950 | 1.000 |
| rust | 0.583 | 0.850 | 0.900 |

### Import traversal (`import`)

Token matches an imported module name; surfaces importers (score +5 per importer, capped at 3).

Disabling this signal changes MRR by **+0.000**.

| Fixture | P@3 | MRR | Coverage |
|---|---:|---:|---:|
| python | 0.681 | 1.000 | 1.000 |
| typescript | 0.800 | 0.950 | 1.000 |
| rust | 0.667 | 0.950 | 1.000 |

### Hot-file boost (`hot`)

Boost files with high 90-day git touch counts (score +2).

Disabling this signal changes MRR by **+0.000**.

| Fixture | P@3 | MRR | Coverage |
|---|---:|---:|---:|
| python | 0.708 | 1.000 | 1.000 |
| typescript | 0.733 | 0.950 | 1.000 |
| rust | 0.667 | 0.950 | 1.000 |

### Test-file penalty (`test_penalty`)

Down-weight `tests/test_*.py`, `*.spec.ts`, etc. unless the prompt asks about testing (score −3).

Disabling this signal changes MRR by **+0.000**.

| Fixture | P@3 | MRR | Coverage |
|---|---:|---:|---:|
| python | 0.681 | 1.000 | 1.000 |
| typescript | 0.700 | 0.950 | 1.000 |
| rust | 0.667 | 0.950 | 1.000 |

### Hub-file penalty (`hub_penalty`)

Down-weight `mod.rs` / `__init__.py` / `index.ts` / `models.py` / `lib.rs` when not named in the prompt (score −2).

Disabling this signal changes MRR by **-0.005**.

| Fixture | P@3 | MRR | Coverage |
|---|---:|---:|---:|
| python | 0.708 | 1.000 | 1.000 |
| typescript | 0.733 | 0.950 | 1.000 |
| rust | 0.633 | 0.933 | 1.000 |

## Interpretation

- Signals that move MRR by ≥0.05 are load-bearing. Removing them is
  a regression.
- Signals that barely move the numbers (<0.01) are either redundant
  (their evidence is captured by another signal) or rare on this
  fixture set. They may still matter on bigger repos — we keep them
  if the cost of evaluating them is near-zero.
- A positive delta (disabling helps) means the signal is *hurting*
  on this eval. Investigate — either the weight is wrong or the
  signal fires on pathological cases.

## Reproduce

```bash
python3 python/evals/runners/autocontext_ablation.py
```
