# Context OS — Pitch

**One-pager for the Claude Code team at Anthropic.**  
For the 20-minute version see [`PROPOSAL.md`](PROPOSAL.md). For reviewer walkthroughs see [`REVIEW-CHECKLIST.md`](REVIEW-CHECKLIST.md).

---

## The claim

**A ~400-line stdlib Python hook cuts Claude Code token spend by 40.9% on live, real workloads.** We have the receipts; the hook is MIT-licensed; everything in this document is reproducible in a CI run on GitHub Actions.

---

## The one-number pitch

| | Without `auto_context` | With `auto_context` |
|---|---:|---:|
| Tokens per prompt (mean) | 51,000 | 30,000 |
| Wall-clock per prompt (mean) | 11.80s | 7.64s |
| Tool calls in first turn (mean) | 3.44 | 1.89 |

**−40.9% aggregate tokens · −35.3% wall-clock · p=5.06e-07 · Cohen's d=1.84.**

Applied at Claude Code's scale that's a material change to per-user cost *and* perceived latency, without touching the model, the API, or the user's workflow.

---

## Why this works

Claude Code's first turn burns tokens on **exploration**: Glob → Grep → Read → Read → Read, searching for the file relevant to the user's prompt. That exploration is blind — the model doesn't know what's in the repo until it reads it.

**We pre-build the map.** A stdlib Python walker (`build_repo_graph.py`) indexes symbols + imports + git-hot files into `.context-os/repo-graph.json`. A `UserPromptSubmit` hook (`auto_context.py`) reads the user's prompt, looks up matching symbols/paths, and injects a 50-token block of `file:line · symbol · imports` candidates **before** Claude's first turn.

Claude now starts with structure in hand. Most of the time the top candidate is the right file. Instead of 5 exploratory tool calls, it's one targeted `Read`.

No embeddings. No server. No model call. No config. One hook, one build script, one JSON file on disk.

---

## Why it belongs inside Claude Code, not next to it

Today this is a third-party plugin. Discovery is the problem: users who would benefit most (new-to-Claude-Code, not power users) won't find a GitHub plugin.

Three integration paths, ordered by depth:

| Path | Anthropic-side cost | User-side cost | Win fraction |
|---|---|---|---|
| **(A) Bundle the hook** (`claude init-hooks --context`) | Zero; we donate the code | One command, opt-in | Power users only |
| **(B) First-class primitive** (`claude context build` / `search`) | ~1 engineer-week to port to Rust, wire up CLI verbs, schema-stabilize | Zero — auto-runs on first prompt, env-toggleable | Most users |
| **(C) Default-on with rebuild-on-stale** | Anthropic-scale telemetry to measure regressions | Zero | All users |

We recommend (B). Happy to PR the code or walk the Anthropic engineer through the port.

---

## The evidence pack (every number reproducible, CI-gated)

All reports live in `python/evals/reports/`, regenerated on every PR:

**Live Claude A/B** (`live-session-bench-stats.md`):
- N = 36 real `claude --print` calls (6 prompts × 3 runs × 2 arms)
- −40.9% aggregate tokens, bootstrap 95% CI **[32.7%, 48.9%]** (N=10,000)
- 6/6 prompt-level wins, 16/18 per-run wins (Wilson CI [67.2%, 96.9%])
- paired t-test **p = 5.06e-07**, Cohen's d = **1.84**
- wall-clock −35.3% (11.80s → 7.64s mean)

**Offline retrieval** (`autocontext-eval.md`, 32 hand-labeled prompts, Py/TS/Rust):
- MRR **0.969** · P@3 **0.703** · coverage 1.000
- **+0.094 MRR** over BM25-symbols · **+0.407** over naive-filename

**Dogfood on this repo** (`dogfood-eval.md`, 15 real-developer prompts, 50 files):
- MRR **0.789** · top-1 **0.667** · P@3 0.322
- **beats every lexical baseline** on real-repo prompts (+0.181 over BM25-symbols, +0.264 over BM25-path, +0.517 over grep-count)

**Ablation** (`autocontext-ablation.md`, 8 signals, leave-one-out):
- `path_substr` ΔMRR −0.062 (load-bearing)
- `path_exact` ΔMRR −0.016 (marginal)
- no signal is dead weight; none overfits

**Robustness** (`robustness.md`, 18 adversarial cases):
- 18/18 pass: unicode, 100K-char prompts, null bytes, corrupt JSON, regex bombs, shell metacharacters, path injection, ablate-all, disabled, empty stdin
- every case exits 0 in <1s, no tracebacks reach the user

**Latency** (`latency-bench.md`, synthetic 100 → 50k files):
- p99 **23ms** at 100 files · **118ms** at 10k · **589ms** at 50k
- 1.7× under the 1s SLA at 50,000 files; IDF-stable after precomputed `path_df` (v2 graph)

**Ranker regression floor** (`ranker_floor.py`, CI-enforced):
- 9 hard gates: synthetic MRR ≥ 0.920, dogfood MRR ≥ 0.720, top-1 ≥ 0.580, baseline margins on 4 baselines
- red-lines the PR if any gate fails

---

## Back-of-envelope economics

Assumptions (conservative):
- 1M Claude Code active users
- 20 prompts/day per user × 20 business days/month = 400 prompts/month
- Current token spend ≈ 50K/prompt (matches our measured control arm)
- Blended input+output cost ≈ $6 / 1M tokens (recent Sonnet pricing)

| Line | Without `auto_context` | With |
|---|---:|---:|
| Tokens / user / month | 20M | 11.8M |
| Cost / user / month (platform) | $120 | $71 |
| **Savings / user / month** | — | **$49** |
| **Savings across 1M users / year** | — | **~$588M** |

Even discounted 90% for cache reuse, cohort overlap, smaller sessions, and power-user skew, you're in the low-nine-figures in margin recaptured per year.

Our price for donating the code and consulting on the port: a fraction of one month of that. (Or $0 if you just ship it — the MIT license is the MIT license.)

---

## What we're NOT claiming

- Not Anthropic-scale. 36 live calls on 6 prompts is a proof-of-concept, not production telemetry. Your dataset is bigger than ours.
- Not universal. Purely descriptive prompts (no filename or symbol overlap) are the ceiling of lexical retrieval. A learned semantic reranker is the natural v3.
- Not a replacement for embeddings on broad-recall tasks. We target **precision** at the first candidate, so the first `Read` is correct, not that every candidate is relevant.

---

## What we want

Short version: **ship this, ideally upstream.** If Anthropic ports it into `claude context`, we'll close the third-party plugin and celebrate.

Longer version:
1. **Code review by your CLI team.** We want to hear what breaks at 50k-file monorepos and non-English prompts before you bet on it.
2. **Stable hook API.** Our `UserPromptSubmit` JSON payload has shifted twice in minor releases. A documented schema with version header would let every community hook (not just ours) stop being fragile.
3. **A path to upstream.** (A) / (B) / (C) above. We'll donate or license as works best.

No equity. No partnership release. No strings. Code and a conversation.

---

## Who we are

One full-stack engineer (sravan27). Ship-first, measurement-second. Context-OS is 6 months of after-hours work and 28 shipped patterns; `auto_context` is the one that broke out.

Email: sridharsravan@icloud.com  
Repo: https://github.com/sravan27/context-os  
Release: https://github.com/sravan27/context-os/releases/tag/v2.7.0

---

## How to verify in 5 minutes

```bash
git clone https://github.com/sravan27/context-os
cd context-os
python3 python/evals/runners/ranker_floor.py        # 9 hard gates, ~45s
python3 python/evals/runners/autocontext_eval.py    # MRR 0.969 · P@3 0.703
python3 python/evals/runners/dogfood_eval.py        # real-repo MRR 0.789
python3 python/evals/runners/robustness_test.py     # 18/18 adversarial
python3 python/evals/runners/latency_bench.py       # p99 SLA
```

Every number in this pitch is the output of one of those scripts. Nothing is hand-edited. The CI workflow runs all of them on every PR — the green badge is the contract.
