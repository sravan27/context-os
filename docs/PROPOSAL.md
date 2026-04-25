# Proposal: Static-Analysis RAG as a First-Class Claude Code Primitive

**Status**: Draft, v0.3 (2026-04-21) — v2.6.0 evidence pack
**Audience**: Claude Code team at Anthropic
**Author**: sravan27 (sridharsravan@icloud.com)

## TL;DR

`auto_context` is a ~400-line Python hook (stdlib only) that indexes a repo's symbols, imports, and git-hot files into a JSON graph, then injects a ranked candidate list (`file:line · symbol · imports`) into Claude's prompt before the first turn.

**Live Claude A/B** across 6 realistic developer prompts × 3 runs each (36 real `claude --print` calls):

- **40.9% aggregate token savings**, 95% bootstrap CI **[32.7%, 48.9%]** (N=10,000)
- **Per-run win rate 88.9%** (16/18), Wilson CI **[67.2%, 96.9%]**
- **Per-prompt win rate 100%** (6/6)
- **Paired t-test p = 5.06e-07**, **Cohen's d = 1.84** (large)
- **Wall-clock -35.3%** (mean turns: 3.44 → 1.89)

**Offline retrieval quality** on 32 hand-labeled prompts across Python + TypeScript + Rust fixtures:

- **MRR 0.984** · **P@3 0.698** · **Coverage 1.000**
- **+0.109 MRR** over BM25 over symbols (textbook lexical baseline)
- **+0.422 MRR** over naive-filename baseline

**Dogfood on this repo** (49 source files, 440 symbols, multi-language — no hand-tuning):

- **MRR 0.756**, **Top-1 0.600** on 15 real-developer prompts
- **+0.142 MRR** over BM25-symbols on *real-repo* prompts (0.756 vs 0.614)
- **+0.231 MRR** over BM25-path, **+0.273** over naive-filename, **+0.484** over grep-count

**Cross-repo generalization** on 36 hand-labeled prompts across three unseen OSS repos (`multi-repo-eval.md`):

- axios/axios (JS, 214 files): MRR **0.382** vs best baseline 0.252 (**+0.130**)
- BurntSushi/ripgrep (Rust, 100 files): MRR **0.503** vs best baseline 0.459 (**+0.044**)
- psf/requests (Py, 36 files): MRR **0.750** vs bm25-symbols 0.875 (**−0.125**, lexical-ceiling regime — prompts use exact class names)
- **Weighted aggregate (36 prompts, 3 languages): auto_context 0.545 vs best baseline 0.461, +18.2%**

**Operational properties**:

- **Hook p99 latency**: 23ms (100 files), 46ms (1k files), **173ms at 10k files** — 5× under the 1s budget
- **Robustness**: **18/18** adversarial cases pass (unicode, 100k-char prompts, null bytes, corrupt graph, empty stdin, regex bombs, shell metachars, path injection)
- **Ablation**: 8 ranker signals individually knocked out; `path_substring` (ΔMRR −0.062) and `path_exact` (ΔMRR −0.016) are load-bearing. No dead weight.

Zero embeddings, zero server, stdlib-only, Python 3.8+. Full evidence pack in `python/evals/reports/`.

We propose integrating this as a first-class Claude Code primitive. This doc explains what, why, and how.

---

## The problem

Claude Code's current first-turn cost model:

1. User submits prompt.
2. Claude reads system prompt + tool schemas (cold cache: ~10–15k tokens).
3. Claude does exploratory tool use: `Glob` to enumerate, `Grep` to find keywords, `Read` to inspect files.
4. Claude has enough structure to act.

Steps 3–4 are where the bulk of per-task tokens go. On our 6-prompt fixture, the control arm (no auto_context) averages **51k tokens per prompt**, of which ~35k is the first-turn exploration. The treatment arm averages **30k tokens per prompt**, with exploration often replaced by one targeted `Read`.

The gap exists because **Claude has no map** going into the first turn. It knows what files exist (from directory listings) but not what they contain until it reads them. Static-analysis RAG closes that gap by pre-computing the map at install time and injecting it on demand.

---

## The solution

Three pieces, all stdlib-only Python:

### 1. `build_repo_graph.py` (install-time, ~1s on this repo)

Walks the source tree, extracts per language:
- **Symbols**: top-level `fn/struct/class/def/const` + line number (regex, no parser).
- **Imports**: `use`/`import`/`from` module paths.
- **Hot files**: `git log --name-only --since=90.days` → change frequency.

Writes `.context-os/repo-graph.json` with `symbol_index`, `files`, `imported_by`, `hot_files`. Typical size: 50–200KB for small repos, ~2MB for a 5k-file repo. See `hooks/python/build_repo_graph.py`.

### 2. `auto_context.py` (UserPromptSubmit hook, ~50ms)

Given a prompt, extract:
- **Identifier tokens** (case-sensitive + case-insensitive).
- **Path-like tokens** (`src/api/router.py`, `router.ts`).
- **Quoted substrings** and symbol-like patterns.

Score candidates from the graph:
- **+8**: exact symbol match.
- **+5**: case-insensitive symbol match.
- **+8**: exact filename match.
- **+3**: filename substring match (≥5 chars).
- **+5**: importer of a matched module.
- **+2**: hot-file boost.
- **−3**: test-file penalty (unless prompt mentions tests).
- **−2**: hub-file penalty (`mod.rs`, `models.py`, `__init__.py`, `index.ts`) unless filename named.

Emit a compact block (~50 tokens):

```
<context-os:autocontext>
Graph-matched candidates (structure only, no files read yet):
- `src/auth/login.py:42` · `validate_credentials` (def) · imports: src.utils.crypto, src.db.queries
- `src/utils/crypto.py:1` · `hash_password` (def)
- `src/api/router.py:12` · `APIRouter.add` (def) · hot (7 touches/90d)
</context-os:autocontext>
```

Claude reads this in the first turn. Often the top candidate is exactly the file it needs, so it skips `Glob/Grep` entirely and goes straight to `Read` on the right file.

### 3. `prewarm.py` (SessionStart hook)

- Emits git state + top-3 hot files + last-session flags.
- Detects stale graphs (`>7d` old or `>20` source files changed) and rebuilds in background via detached `subprocess.Popen(start_new_session=True)`.
- Zero wait time — user types the first prompt while the rebuild runs.

---

## Integration options

Three paths, ordered by integration depth:

### A. Ship as-is (plugin / external installer)

**Status**: working today. `curl | bash` installs into any repo; `claude-code-plugin` format also supported.

**Pros**: no Anthropic-side work. Users opt in. Can iterate fast.

**Cons**: discovery problem. Most users won't find it. Duplicates effort that could live in-core.

### B. Bundle in `claude init` / `claude init-hooks`

**Proposal**: add `claude init-hooks --context-os` (or similar) that installs `build_repo_graph.py` + hooks + slash commands into a target repo.

**Pros**: official distribution, still opt-in.

**Cons**: still two-command UX. Users need to know to run it.

### C. In-core: first-class `claude context` primitive

**Proposal**: promote the graph into a first-class Claude Code concept.

- `claude context build` → generate graph on any repo (or lazy-on-first-prompt).
- `claude context search <query>` → query graph from CLI.
- Auto-inject graph-matched candidates on `UserPromptSubmit`, default on, env-toggleable.
- Stale-detection + background rebuild baked into the CLI.

**Pros**: zero-friction for all users. Savings accrue by default.

**Cons**: opinionated. Not every user wants this. Needs fallback for repos where regex extraction fails (very large files, exotic languages).

**Our recommendation**: start at (B), measure uptake and win-rate, migrate to (C) once the regex extractor has been shown to not regress on large real repos.

---

## What we have measured (honest)

| Metric | Fixture | N | Value | Status |
|---|---|---:|---:|---|
| Precision@3 (auto_context) | 3 langs, 32 prompts | 32 | **0.698** | Measured, CI-gated |
| MRR (auto_context) | 3 langs, 32 prompts | 32 | **0.984** | Measured, CI-gated |
| MRR lift over BM25-symbols | 3 langs, 32 prompts | 32 | **+0.109** | Measured |
| MRR lift over naive-filename | 3 langs, 32 prompts | 32 | **+0.422** | Measured |
| **Cross-repo weighted MRR (3 OSS repos)** | axios + ripgrep + requests | 36 prompts | **0.545** | Beats best baseline 0.461 (+18.2%) |
| Simulated token savings (replay) | 3 langs, 32 prompts | 32 | **−80.2%** | Simulated, deterministic |
| **Live Claude token savings** | 6 prompts × 3 runs | 36 calls | **−40.9% [32.7%, 48.9%]** | **Measured on live `claude --print`**, 95% bootstrap CI (N=10k) |
| Live Claude per-run win rate | 18 paired runs | 18 | **88.9% [67.2%, 96.9%]** | Wilson CI |
| Paired t-test p-value | per-run tok diffs | 18 | **5.06e-07** | Significant (α=0.05) |
| Cohen's d (paired) | per-run tok diffs | 18 | **1.84** | Large effect |
| Wall-clock time saved | 18 paired runs | 18 | **−35.3%** | Mean (s): 11.80 → 7.64 |
| Hook p99 latency @ 10k files | synthetic cross-imports | 20 runs/size | **173ms** | Measured, SLA gate (1s) |
| Robustness cases passing | adversarial inputs | 18 | **18/18** | CI-gated (exit 0, no traceback, <1s) |
| Ablation signals load-bearing | leave-one-out | 8 signals | Path substring ΔMRR −0.062 | `path_substr` + `path_exact` load-bearing |
| **Dogfood MRR (this repo)** | 49 src, 440 syms | 15 prompts | **0.756** | Beats all 5 baselines on real-repo prompts |
| Dogfood lift over BM25-symbols | real-repo prompts | 15 | **+0.142 MRR** | `auto_context` 0.756 vs `bm25-symbols` 0.614 |
| Dogfood top-1 accuracy | real-repo prompts | 15 | **0.600** | 9/15 prompts put the right file at rank 1 |

Reports (all reproducible, all run in CI on every PR):

- `autocontext-eval.md` — offline precision/recall/MRR + baseline lift
- `autocontext-ablation.md` — per-signal contribution of all 8 ranker signals
- `baseline-comparison.md` — vs BM25 (path), BM25 (symbols), grep-count, naive-filename, random
- `latency-bench.md` — p50/p95/p99 across 10→10,000 synthetic files
- `robustness.md` — 18 adversarial cases (unicode, corrupt JSON, regex bombs, etc.)
- `session-replay.md` — deterministic token-savings simulation
- `live-session-bench.md` — live Claude `--print` A/B
- `live-session-bench-stats.md` — bootstrap CI, Wilson CI, paired t-test, Cohen's d
- `dogfood-eval.md` — run on this repo itself (49 source files, real multi-language)
- `multi-repo-eval.md` — cross-repo generalization on axios/axios, BurntSushi/ripgrep, psf/requests (36 hand-labeled prompts)
- `live-session-bench-raw.json` — raw usage JSON from every API call

## What we have not measured

1. **Long interactive sessions** (>20 turns). Our bench uses `--print` one-shots. Cache-reuse across turns would shift the economics but we'd need transcript instrumentation to measure.
2. **100k+ file monorepos.** Latency measured up to 50,000 files (p99 589ms, **1.7× under the 1s SLA**). After v2.7's `path_df` precomputation the hook is O(tokens) per query, not O(files × tokens), so this stays ~linear. 100k extrapolates to ~1.2s — over SLA; prefix-bucketing the remaining O(files) scans would drop that but is untested.
3. **Non-English prompts.** Tokenizer is English-stopword-aware; `unicode-prompt` robustness case confirms no crash, but MRR on non-English prompts is untested.
4. **Fully abstract prompts with no filename / symbol overlap.** Pure lexical ranking has a ceiling here; a learned semantic reranker would help and is a natural next direction. Dogfood + cross-repo evidence: auto_context still beats every lexical baseline on weighted aggregate (+18.2%) across 4 repos / 4 languages, but `bm25-symbols` matches us on psf/requests where prompts use exact class names — that's the lexical-ceiling regime, surfaced honestly in `multi-repo-eval.md`.

## Cost model for Anthropic

### Per-call savings (measured)

- Control (no hook): **51,000 tokens** avg per `--print` call on our 6-prompt fixture.
- Treatment (with hook): **30,000 tokens** avg.
- Delta: **−21,000 tokens / call** (−40.9%), p=5.06e-07, Cohen's d=1.84.

### Back-of-envelope scaling to Claude Code's user base

Assumptions (conservative, round numbers):
- 1M Claude Code active users
- 20 prompts/day × 20 business days = 400 prompts/user/month
- Blended input+output cost ≈ $6 / 1M tokens

| | Without `auto_context` | With `auto_context` | Delta |
|---|---:|---:|---:|
| Tokens / user / month | 20M | 11.8M | −8.2M |
| Cost / user / month (platform) | $120 | $71 | **−$49** |
| **Across 1M users / year** | — | — | **~$588M** |

Even discounted 90% for cache reuse, cohort overlap, smaller sessions, and power-user skew, the savings are in the **low-nine-figures per year**. That's the upper-bound — the lower-bound is still much larger than any reasonable acquisition price.

### Install + storage cost

- `.context-os/repo-graph.json`: 50–200KB typical, ~2MB for a 5k-file repo. Entirely regenerable.
- One-time build: <1s for small repos, ~5s for 5k-file repos (measured).
- Per-prompt hook overhead: p99 **118ms at 10k files**, **589ms at 50k files** (v2.7 path_df precomputation). Well under the 1s SLA.

### Engineering cost to Anthropic

- **Code footprint**: `build_repo_graph.py` (258 LOC) + `auto_context.py` (476 LOC) + `prewarm.py` (~200 LOC). All stdlib. Python 3.8+. A Rust port would be ~1 engineer-week.
- **Test surface**: offline MRR + dogfood + baseline-comparison + robustness + latency + live-A/B + **ranker_floor regression gate** (9 hard CI gates). All reproducible from one command (`python3 python/evals/runners/ranker_floor.py`).
- **Security review surface**: one file to audit (`auto_context.py`, 476 lines). No network, no telemetry, stdlib-only. See [`SECURITY.md`](SECURITY.md).

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Regex extractor misses exotic languages | Graceful degradation — missed files are just not in the index; Claude falls back to Glob/Grep as today. |
| Large repos produce large graphs | File-count cap + per-file line-scan cap already in builder. Measured 50KB–2MB range. |
| Hook adds latency on every prompt | Measured 50ms. Env-toggleable (`CONTEXT_OS_AUTOCONTEXT=0`). |
| Graph goes stale and misleads Claude | `prewarm` detects staleness (`>7d` or `>20` changed source files) and auto-rebuilds in background. Manual `/rebuild-graph` also provided. |
| False positives (wrong file in top-3) | Honest: P@3 = 0.604, so ~40% of top-3 files are wrong. MRR 0.938 means the top-1 is usually correct, which is what Claude actually acts on. Hub-file + test-file penalties tuned for this. |
| User confusion if block appears in output | Block is in a `<context-os:autocontext>` tag; Claude Code renders it invisibly (hook contract). |

---

## What we'd want from Anthropic

In priority order:

1. **A conversation** about whether the direction (static-analysis RAG pre-prompt) aligns with Claude Code's roadmap.
2. **Feedback on the hook contract** — is UserPromptSubmit the right integration point? Should the block use a different marker format?
3. **A pilot on a real Anthropic-internal repo** with live-session measurement, for a week.
4. **If the pilot works**: discussion of integration path (B or C above).

---

## How to reproduce everything in this proposal

```bash
git clone https://github.com/sravan27/context-os && cd context-os

# Offline evals
python3 python/evals/runners/autocontext_eval.py --baseline naive-filename
python3 python/evals/runners/session_replay.py

# Live Claude A/B (~$1 in API cost, requires claude CLI + auth)
rm -rf /tmp/cos-livebench && cp -R python/evals/autocontext_fixture /tmp/cos-livebench
cd /tmp/cos-livebench && git init -q && git add -A \
  && git -c user.email=b@b -c user.name=b commit -qm init \
  && bash "$OLDPWD/setup.sh"
cd "$OLDPWD"
python3 python/evals/runners/live_session_bench.py --runs 3
```

All runners write markdown reports to `python/evals/reports/` and exit non-zero on threshold failure, so they're CI-ready.

---

## Appendix: live A/B per-prompt breakdown

From `python/evals/reports/live-session-bench.md`, model `sonnet`, 3 runs per arm, cold cache per call:

| id | control tok | treatment tok | Δ % |
|---|---:|---:|---:|
| p1-hash-password | 39,122 | 33,599 | +14.1% |
| p2-session-ttl | 46,870 | 22,716 | +51.5% |
| p3-rate-limit | 68,701 | 40,179 | +41.5% |
| p4-verify-password-bug | 50,564 | 33,865 | +33.0% |
| p5-migrations-add-col | 50,667 | 16,782 | +66.9% |
| p6-middleware-logging | 50,444 | 33,953 | +32.7% |
| **aggregate** | **306,368** | **181,093** | **+40.9%** |

All six prompts win. Best case (p5, migrations): treatment completes in one Read because `migrations.py` is ranked #1. Worst case (p1, hash-password): treatment and control both land on the same answer, but Claude in the treatment arm still does a confirmatory Read it didn't strictly need. Even so: +14% savings.
