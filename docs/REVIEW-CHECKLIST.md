# Review checklist — for the Anthropic engineer who landed here

**Your time is expensive.** This file is designed so you can go from "never seen this repo" to "informed opinion" in **~20 minutes**.

## Claims to verify, in order of importance

### 1. The headline number (−40.9% tokens, p=5e-7) is real

**Claim:** on 36 live `claude --print` calls, auto_context saves 40.9% of tokens vs control, with a paired t-test p=5.06e-07 and Cohen's d=1.84.

**Read:** [`python/evals/reports/live-session-bench-stats.md`](../python/evals/reports/live-session-bench-stats.md).

**Re-derive:** the raw per-call usage JSON is at `python/evals/reports/live-session-bench-raw.json`. The stat-pack script is:
```bash
python3 python/evals/runners/live_bench_stats.py
```
Runs in <1s; reads the raw JSON, emits the stats markdown. Inspect both the raw numbers and the script — no model calls, no external calls, just arithmetic + bootstrap + `scipy`-free paired t-test.

**Red flags to look for:**
- Cherry-picked prompts? The 6 prompts are in `python/evals/prompts/live_prompts.json`. Read them — they're mundane developer tasks.
- Rigged token measurement? All numbers come from Claude Code's own `usage` object in the `stream-json` output. See `python/evals/runners/live_session_bench.py:run_one()`.
- P-value massaged? The t-test is vanilla paired on `tokens_treatment − tokens_control` per run. Check `live_bench_stats.py:paired_t()`.

### 2. The offline MRR 0.984 is not an over-fit

**Claim:** on 32 hand-labeled prompts × 3 language fixtures, auto_context achieves MRR 0.984 and beats BM25-symbols by +0.109 MRR.

**Read:** [`python/evals/reports/autocontext-eval.md`](../python/evals/reports/autocontext-eval.md) and [`python/evals/reports/baseline-comparison.md`](../python/evals/reports/baseline-comparison.md).

**Re-derive:**
```bash
python3 python/evals/runners/autocontext_eval.py
python3 python/evals/runners/baseline_comparison.py
```

**Red flags to look for:**
- Prompts written to fit the ranker? Open `python/evals/prompts/*.json`. Half mention files/symbols directly, half are descriptive ("how is user auth handled"). Baseline-comparison shows every baseline on the same prompts — the delta over BM25-symbols is the cleanest apples-to-apples.
- BM25 mis-tuned? `baseline_comparison.py:BM25` is a 40-line stdlib Okapi with standard k1=1.5, b=0.75. You can tweak the params and re-run — we did and the delta holds.

### 3. It works on real code, not just synthetic fixtures

**Claim:** on the Context-OS repo itself (50 source files, 444 symbols, real heterogeneous codebase), auto_context achieves MRR 0.756 and beats every lexical baseline including +0.142 MRR over BM25-symbols. Beyond dogfood, on **three unseen OSS repos** (axios/axios JS, BurntSushi/ripgrep Rust, psf/requests Py — 36 hand-labeled prompts), auto_context wins the **weighted aggregate MRR 0.545 vs best baseline 0.461 (+18.2%)**.

**Read:** [`python/evals/reports/dogfood-eval.md`](../python/evals/reports/dogfood-eval.md), [`python/evals/reports/multi-repo-eval.md`](../python/evals/reports/multi-repo-eval.md).

**Re-derive:**
```bash
python3 python/evals/runners/dogfood_eval.py
python3 python/evals/runners/multi_repo_eval.py    # clones 3 OSS repos to /tmp on first run
```

**Red flags to look for:**
- Prompts tailored to this repo's naming? The 15 dogfood prompts are in `python/evals/dogfood_prompts.json`; the 36 multi-repo prompts are in `python/evals/multi_repo_prompts/*.json`. Most are descriptive ("hook that blocks reading enormous files", "parser and matcher for .gitignore-style patterns"). Pinned SHAs verify expected files.
- Cherry-picked repos? We picked the first three popular OSS repos that span Py / JS / Rust and weren't already in our fixtures. Acceptance criterion in `multi_repo_eval.py` is honest: aggregate must win + per-repo must beat avg-baseline. We surface the one repo (psf/requests) where bm25-symbols matches us — prompts use exact class names, the lexical-retrieval ceiling regime.

### 4. It doesn't crash on pathological input

**Claim:** 18/18 adversarial cases pass, exit 0 in <1s.

**Read:** [`python/evals/reports/robustness.md`](../python/evals/reports/robustness.md).

**Re-derive:**
```bash
python3 python/evals/runners/robustness_test.py
```

**Cases:** unicode prompts, 100K-character prompts, null-byte prompts, corrupt JSON graph, empty stdin, stdin-not-JSON, regex bombs (`(a+)+$`, `(.*)*`), shell metacharacters, path injection (`../../etc/passwd`), ablate-all (every ranker signal disabled), disabled (`CONTEXT_OS_AUTOCONTEXT=0`), missing graph, corrupt graph, nested symlinks, 0-byte files, huge files, and more.

### 5. It meets the latency SLA

**Claim:** p99 hook latency ≤ 1s at 10,000 files.

**Read:** [`python/evals/reports/latency-bench.md`](../python/evals/reports/latency-bench.md).

**Re-derive:**
```bash
python3 python/evals/runners/latency_bench.py --sizes 100,1000,10000
python3 python/evals/runners/latency_bench.py --sizes 25000,50000  # extended
```

**Current measurements:**
- 100 files: p99 23ms
- 1,000 files: p99 41ms
- 10,000 files: p99 118ms (**8.5× under SLA**)
- 25,000 files: p99 284ms
- 50,000 files: p99 589ms (**1.7× under SLA**)

After the v2.7.0 path-df precomputation the hook is O(tokens) per query, not O(files × tokens), which is why it stays linear in repo size.

---

## Run all of this in one command

```bash
python3 python/evals/runners/ranker_floor.py
```

Runs the synthetic, dogfood, and baseline evals, then asserts 9 hard regression gates. Exits non-zero if any gate fails. This is what CI enforces on every PR.

---

## What's in the hot path

```
hooks/python/auto_context.py   — 476 lines. THE hook. Read this file.
hooks/python/build_repo_graph.py — 258 lines. Install-time indexer.
.github/workflows/ci.yml       — CI gates. Every report is regenerated per PR.
docs/PROPOSAL.md               — 20-minute writeup for the CLI team.
docs/SECURITY.md               — what leaves your machine (nothing).
docs/PITCH.md                  — 5-minute writeup for leadership.
```

Everything else is either evaluation infrastructure or supporting hooks (dedup, loop, file-size, session-profile).

---

## Likely objections (with our honest answer)

**"Lexical retrieval caps at MRR 0.984; semantic rankers would do better."**
Agreed. Lexical is cheap, fast, explainable, and stdlib-only. The −40.9% tokens number is measured against a *strong* baseline (Claude does its own retrieval natively), not a strawman. A semantic reranker on top of this is v3 material and we're happy to collaborate.

**"This won't scale to 100k-file monorepos."**
Measured to 50k at p99 589ms. Extrapolating linearly, 100k is ~1.2s — over SLA. The O(files) scans that remain (basename-in-prompt check, file enumeration) can be pre-bucketed by prefix to drop to O(log n). We haven't done that work yet because most Claude Code users aren't in 100k-file repos; if you tell us that's a large cohort, we'll prioritize.

**"Regex symbol extraction misses edge cases."**
Yes. We accept ~5% recall loss in exchange for zero parser dependencies and 1-second graph builds on 5k-file repos. The ranker recovers from missed symbols via path substring matching. For languages where regex struggles (C++, Scala, metaprogrammed Ruby), a tree-sitter-backed extractor is a 2-day port.

**"What if the graph gets stale?"**
`prewarm.py` detects stale graphs (>7d old or >20 source files changed in git) and rebuilds in the background via detached `subprocess.Popen`. User types the first prompt while the rebuild runs; the hook uses the previous graph until the new one lands.

**"How does this compare to `tree-sitter-based` retrieval systems?"**
We don't ship one, but: tree-sitter gives you better symbol extraction (higher recall) at cost of a native dep (hard to ship in a Python hook). The ranker in `auto_context.py` is orthogonal — swap in a tree-sitter-backed `build_repo_graph.py` and all the eval scripts still run. We'd bet the MRR moves from 0.984 → 0.99+.

**"Isn't this just BM25 with extra steps?"**
The 8-signal ablation (`autocontext-ablation.md`) shows:
- BM25 over symbols alone: MRR 0.875
- BM25 over paths alone: MRR 0.714
- auto_context (symbol-exact + symbol-ci + path-exact + path-substr + import + hot + test-penalty + hub-penalty + basename-in-prompt + multi-token coverage + NL-expansion + plural/singular stems + path-token dedupe + df-discriminativity + file-level aggregation): MRR 0.984
The signals beyond BM25 each contribute something. Removing the biggest (`path_substr`) costs 0.062 MRR; removing everything non-BM25 costs much more. v2.8 added plural/singular stems, df-discriminative path scoring, and file-level aggregation — visible in the multi-repo eval as a 0.5+ weighted-MRR aggregate across 3 unseen OSS repos.

---

## If you want to talk

Email **sridharsravan@icloud.com**.  
Repo: **https://github.com/sravan27/context-os**  
Latest release: **https://github.com/sravan27/context-os/releases/tag/v2.8.0**

We've got code, time, and a strong bias for shipping. Happy to walk the upstream port with you.
