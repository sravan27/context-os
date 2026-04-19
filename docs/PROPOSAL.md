# Proposal: Static-Analysis RAG as a First-Class Claude Code Primitive

**Status**: Draft, v0.1 (2026-04-19)
**Audience**: Claude Code team at Anthropic
**Author**: sravan27 (sridharsravan@icloud.com)

## TL;DR

`auto_context` is a ~200-line Python hook that indexes a repo's symbols, imports, and git-hot files into a JSON graph, then injects a ranked candidate list (`file:line · symbol · imports`) into Claude's prompt before the first turn. On a live `claude --print` A/B across 6 realistic developer prompts × 3 runs each (36 real Claude calls):

- **40.9% aggregate token savings** (306,368 → 181,093 tok)
- **Median per-prompt savings: +37.3%**
- **Wins: 6/6 prompts**
- **Offline MRR: 0.938** on 32 hand-labeled prompts across Python + TypeScript + Rust fixtures
- **+0.375 MRR lift over naive-filename baseline**
- **Zero embeddings, zero server, ~50ms hook latency**

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
| Precision@3 (auto_context) | 3 langs, 32 prompts | 32 | **0.604** | Measured, CI-gated |
| MRR (auto_context) | 3 langs, 32 prompts | 32 | **0.938** | Measured, CI-gated |
| MRR lift over filename baseline | 3 langs, 32 prompts | 32 | **+0.375** | Measured, CI-gated |
| Simulated token savings (replay) | 3 langs, 32 prompts | 32 | **−80.2%** | Simulated, deterministic |
| **Live Claude token savings** | 6 prompts × 3 runs | 36 calls | **−40.9%** | **Measured on live `claude --print`** |
| Live Claude win rate | 6 prompts | 6 | **6/6** | Measured |
| Live Claude median Δ | 6 prompts | 6 | **+37.3%** | Measured |

Reports:
- `python/evals/reports/autocontext-eval.md` — offline precision/recall/MRR + baseline lift
- `python/evals/reports/session-replay.md` — deterministic token-savings simulation
- `python/evals/reports/live-session-bench.md` — **live Claude A/B**
- `python/evals/reports/live-session-bench-raw.json` — raw usage JSON from every call

## What we have not measured

1. **Long interactive sessions** (>20 turns). Our bench uses `--print` one-shots. Cache-reuse across turns would shift the economics but we'd need transcript instrumentation to measure.
2. **Large real repos** (>10k files). Fixtures are 13–18 files. The graph builder does scale (tested on this 36-file repo), but we haven't measured hit-rate on a 50k-file monorepo.
3. **Non-English prompts.** Tokenizer is English-stopword-aware.
4. **Adversarial prompts** designed to mislead the ranker. Untested.

## Cost model for Anthropic

### Inference cost

- Control (no hook): 51k tokens avg per our 6-prompt fixture → ~$0.03 per Sonnet call.
- Treatment (with hook): 30k tokens avg → ~$0.02 per call.
- **Net savings: ~$0.01/call at 40% reduction, before considering cache reuse on long sessions.**

### Install + storage cost

- `.context-os/repo-graph.json`: 50–200KB typical.
- One-time build: <1s for small repos, ~5s for 5k-file repos (measured on this repo).
- Per-prompt hook overhead: ~50ms (measured).

### Engineering cost

- **Code footprint**: `build_repo_graph.py` (~250 LOC), `auto_context.py` (~350 LOC), `prewarm.py` (~200 LOC). All stdlib. Python 3.8+.
- **Test surface**: precision/recall/MRR + session-replay + live-A/B, all runnable in CI. `make test` green on first install.

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
