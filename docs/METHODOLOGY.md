# Context OS: Token-Savings Measurement Methodology

**Status:** Living document. Version 0.3 (2026-04-17).
**Audience:** Engineers at Anthropic and elsewhere who want to verify (or refute) the claims in this repo's README.
**Position:** We will state what we have measured, what we have estimated, and what is unmeasured. Where a number is weak we say so.

---

## 0. TL;DR for the skeptical reader

- The headline numbers in the README (`32% tokens`, `18.8% cost`) come from a **single 2-file fixture** with `N=1`. They are illustrative, not representative. Treat them as an existence proof that Context OS does reduce tokens on at least one realistic prompt, nothing more.
- The only numbers we consider scientifically defensible today are (a) the reducer benchmarks on logs/JSON/config fixtures (`N=7` cases, paired before/after, deterministic transform — see §7.1) and (b) the compaction-survival benchmark (`N=2` cases — see §7.2). Both are offline, deterministic, and have well-defined gates.
- Everything else in the README (noise filtering K-token estimates, `40–65%` output reduction, Haiku `93%` exploration savings, `27–70%` test-run compression) is either: cited from upstream work, estimated from documented Anthropic behavior, or pending proper measurement. §8 tags each of the 16 techniques with its evidence class.
- **Real savings are distributional, not a point estimate.** We report medians and interquartile ranges, not means. We will not quote an unqualified "X% saved" without specifying fixture, task, model, cache state, and N.
- If you run our benchmark once on one repo and get a different number than the README, **the README is the one at fault** for being under-specified, not your run.

---

## 1. The measurement problem, stated honestly

A "token savings" claim for a Claude Code optimization kit has at least seven free variables:

| Variable | Why it matters | Range in practice |
|---|---|---|
| Repo size (files, bytes) | Larger repos → more noise → larger absolute savings from `.claudeignore`. | 10–200K files |
| Repo shape | A Next.js monorepo has `node_modules`, `dist`, `.next`. A Rust library has `target`. A pure-Python repo has neither but has `__pycache__`. | Stack-dependent |
| Session length | Short sessions barely amortize the CLAUDE.md overhead. Long sessions benefit most from caching and compaction tuning. | 1–100+ turns |
| Task type | Explanation-heavy prompts cut more output than structured code-edits. (Our README cites 40–65% vs 13–21% from upstream caveman benchmarks.) | High variance |
| Model | Sonnet vs Haiku vs Opus have different input/output price ratios; same token count, different dollar impact. | 5× cost spread |
| Cache state | Cold vs warm cache changes `cache_read_input_tokens` by orders of magnitude. Prompt caching TTL (5m vs 1h) changes it again. | 10–100× |
| Time of day | 5-minute cache entries expire between runs; 1-hour entries often persist. Results taken 90 min apart on the same laptop can differ by 30%+ cache reads. | Confounder |

Any benchmark that pins all seven and reports a single number is measuring a point on a seven-dimensional surface. The README's `32%` is exactly that: one point, reported for transparency, not a population estimate.

This document defines the measurement protocol needed to produce numbers that generalize. We are publishing the protocol before we have the full corpus; §9 lists what's still missing.

---

## 2. Measurement taxonomy

We distinguish four levels of measurement. Every claim in the repo should be tagged with which level it lives at.

### 2.1 Per-session tokens

A **session** = one invocation of `claude` (interactive or `--print`) from start to stop. A session emits a final JSON `usage` block from Claude Code containing:

- `input_tokens` — fresh input this turn.
- `cache_read_input_tokens` — input served from prompt cache.
- `cache_creation_input_tokens` — input written into cache this turn.
- `output_tokens` — tokens emitted by the model.

We define:

```
total_tokens = input_tokens + cache_read_input_tokens + cache_creation_input_tokens + output_tokens
```

This is the primary metric. It is **cache-aware** (cached reads count as tokens processed) but not **cost-weighted** — for cost see §2.4.

Source: Claude Code `--output-format json` returns these fields directly ([Claude Code docs, headless mode](https://code.claude.com/docs/en/headless)). The benchmark script in `scripts/benchmark.sh` extracts them via `jq`.

### 2.2 Per-task tokens

A **task** = one user prompt until the model returns `stop_reason ∈ {"end_turn", "stop_sequence"}` without a tool call triggering a continuation. Tasks are sub-units of sessions. A 40-turn coding session is ~40 tasks.

Per-task measurement requires streaming the transcript and segmenting. Claude Code's `--output-format stream-json` provides turn-level events ([Claude Code docs, SDK streaming](https://code.claude.com/docs/en/sdk)). We have not built this aggregator yet (see §9).

### 2.3 Per-technique contribution (ablation)

For each of the 16 techniques (see §8), the contribution is measured by **leave-one-out ablation**: run the full Context OS install minus technique `i`, vs the full install, on the same fixture and task. The delta is technique `i`'s contribution *conditional on all others being active*.

Caveats:

- Techniques interact. Response shaping + output compression partially overlap. The marginal contribution of each depends on the order and the baseline.
- Some techniques (e.g. statusLine) have structurally zero token effect; measuring them produces noise around zero. We flag these as "non-token UX techniques" in §8.

We have **not yet run** ablation at scale. The per-technique numbers cited in README column 4 are upstream citations or estimates; see §8 "evidence class" column.

### 2.4 Dollar cost (blended pricing)

Claude Code reports `total_cost_usd` per session in the `--output-format json` response. We use this directly when available.

For manual accounting we use Anthropic's published Sonnet 4.6 pricing ([anthropic.com/pricing](https://www.anthropic.com/pricing), retrieved 2026-04-17):

| Token class | $ / million |
|---|---:|
| Input (fresh) | 3.00 |
| Cache write (5m TTL) | 3.75 |
| Cache write (1h TTL) | 6.00 |
| Cache read | 0.30 |
| Output | 15.00 |

"Blended" pricing for back-of-envelope estimates uses a session-weighted average. We assume a typical mix of 70% cache-read / 20% output / 10% fresh-input, giving ≈$3.41/M. This is the number behind the README's `$0.40/session` estimate. It is an **estimate**, not a measurement, and is only used in the `--measure` dry-run output.

Dollar deltas track token deltas monotonically but not linearly; a session that trades cache reads for fresh input can reduce tokens and *increase* cost.

---

## 3. Benchmark protocol

### 3.1 Fixture repos

We define four synthetic size classes. Each is a reproducible seed of a real-world repo shape.

| Class | Files (src) | Files (noise) | LOC (src) | Example |
|---|---:|---:|---:|---|
| Tiny | 1–10 | 0 | <500 | Single-file script, `README + index.js` (current fixture) |
| Small | 10–100 | 100–1K | 500–5K | Personal side-project, `examples/sample-repos/mini-next` |
| Medium | 100–1K | 1K–50K | 5K–100K | Typical SaaS backend, e.g. a fresh `create-next-app` with deps |
| Large | 1K–10K | 50K–500K | 100K–1M | Monorepo, e.g. this repo (`context-os` itself) |

Current status: **only the tiny fixture has been benchmarked end-to-end** (README §Measured results). Small/medium/large are pending (see §9).

Reproducibility: each fixture should be a git commit with a pinned SHA, so `git clone && git checkout <sha>` yields bit-identical state. The current tiny fixture at `/tmp/cos-bench-test` is **not** pinned — it's generated ad hoc. This is a bug. See §9.

### 3.2 Task prompts

Tasks must be:

1. **Deterministic in intent** — unambiguous enough that Claude's variance is in wording, not in action.
2. **Realistic** — drawn from real user sessions, not synthetic.
3. **Bounded** — one task should complete in <60s wall clock with Sonnet.

We have three task families planned, one implemented:

| Family | Example | Status |
|---|---|---|
| `repo-map` | "List the top-level directory structure. Count source files by language." | Implemented (default in `scripts/benchmark.sh`) |
| `code-edit` | "Add a null-check at `src/auth.ts:42`. Run the test suite. Report pass/fail." | Not implemented |
| `exploration` | "Find all callers of the function `authenticate` across the repo." | Not implemented |

The `repo-map` task was chosen first because it exercises noise filtering and repo-map hints directly. It **does not** exercise response shaping (low output) or output compression (no test runs). The 32% figure is heavily tilted toward filesystem-scan savings and under-reports the full stack.

### 3.3 Sample size, summary statistics

- **Minimum N**: 5 runs per (fixture × task × condition) cell.
- **Summary statistic**: **median**, not mean. Claude's output is heavy-tailed — a single run that triggered extended thinking can inflate a 5-run mean by 40%.
- **Variance measure**: **interquartile range** (IQR = Q3 − Q1). Quoted as `median [Q1–Q3]`.
- **Comparison**: paired design — same task run in baseline and treatment, in randomized order, using a fresh temp clone each time so there's no carryover.
- Report format: `total_tokens = 54,036 [48,200–58,900]` (median and IQR across 5 paired runs).

The current headline number has `N=1`. We have no variance estimate. This is the single biggest gap in our evidence.

### 3.4 Cold vs warm cache

Two canonical conditions must be reported separately:

- **Cold cache**: first invocation after ≥1h idle, or after `claude --resume` with a fresh session ID. Cache reads ≈ 0.
- **Warm cache**: second invocation within 5 minutes of an identical prior run. Cache reads ≈ full system prompt.

The README's `32%` is a **warm-cache** number (74K cache reads before, 48K after). The cold-cache number will be much smaller in absolute terms but potentially larger in percentage, because noise filtering reduces the content that *would* be cached.

Cold-cache runs are pending (§9).

### 3.5 Before/after design

For each (fixture, task, cache-state, N) cell:

1. Clone fixture into two temp dirs: `before/` and `after/`.
2. Run Context OS setup on `after/` only.
3. Interleave runs: `before[0], after[0], before[1], after[1], ...` to minimize time-of-day cache drift.
4. Record raw JSON transcripts to disk (not just aggregated numbers).
5. Compute paired deltas: one `Δtokens` per run pair, then take median over pairs.

This is what `scripts/benchmark.sh` implements at `N=1`. Extending to `N=5` is a matter of wrapping the current script — tracked in §9.

---

## 4. Honest caveats

### 4.1 Model non-determinism

Claude's outputs are non-deterministic even at `temperature=0` (we do not set it, so default applies). Output token count varies turn-to-turn for an identical prompt. Published studies ([Anthropic, "Inference and reproducibility"](https://docs.anthropic.com/en/api/messages-examples)) suggest output-token coefficient of variation ≈ 5–15% for short deterministic prompts, higher for open-ended tasks.

**Implication:** Any headline claim below ~10% reduction on a single run is indistinguishable from noise. The 32% figure is above this floor but we still lack a confidence interval.

### 4.2 Cache TTL and time-of-day

Prompt cache entries expire after 5 minutes (default) or 1 hour (opt-in, `ENABLE_PROMPT_CACHING_1H=1`). Two runs 7 minutes apart, default TTL, will both be cold. Two runs 7 minutes apart, 1h TTL, will both be warm. **We never compare across TTL settings; TTL is treated as part of the condition.**

Absolute cache_read numbers drift over the course of a day because other users' traffic affects cache availability (cache is per-workspace but subject to backend eviction; Anthropic does not publish eviction policy). We observe run-to-run drift of 10–20% on the same task under nominally identical conditions.

### 4.3 Caching-dependent techniques

Four techniques only show savings under specific conditions:

- **Prompt caching 1h** — no effect on single-session tasks; large effect on multi-session work over <1h.
- **Early compaction (80%)** — no effect on sessions that never hit 80% context.
- **Context cap (150K)** — no effect on sessions that stay below 150K anyway.
- **Session memory** — no effect within a session; benefit is amortized across session restarts.

Any benchmark with a single short session **under-reports** the value of these techniques by design. Our tiny-fixture 32% does not reflect them at all.

### 4.4 Zero-token-impact techniques

Two techniques have structurally zero direct token effect:

- **statusLine** — writes to a shell-visible status bar, not the context window.
- **Secret exclusion** (security subset of `.claudeignore`) — tokens are counted against the broader noise-filter entry; secret filtering is a correctness/safety property, not a token saving.

Both are included in the installer because users ask for them. We do not claim token savings for them.

### 4.5 Installer overhead

Context OS injects ~300 tokens of CLAUDE.md content and ~150 tokens of settings metadata. On a single short task this is visible in the "before" / "after" `cache_creation_input_tokens` delta (+301 in the tiny fixture: 5255 → 5556). The overhead amortizes across turns — by turn 2 or 3 the savings dominate on any non-trivial session. But on a **truly tiny** session (1 turn, 1 file) Context OS can cost more than it saves. We do not hide this.

---

## 5. Reproducibility

### 5.1 End-to-end benchmark

```bash
# Requires: claude CLI on PATH, git, jq.
git clone https://github.com/sravan27/context-os && cd context-os
scripts/benchmark.sh /path/to/target/repo --model sonnet
# Output: JSON report at /tmp/cos-last-benchmark.json
```

This reproduces the README's headline number when pointed at a tiny fixture. It will produce different numbers on different repos — that is the point of §1.

### 5.2 Reducer benchmark (offline, deterministic)

```bash
python3 python/evals/runners/safe_mode_runner.py
# Output: python/evals/reports/safe-mode-report.{json,md}
```

Fully deterministic. Same input → same output. `N=7` cases, each paired `before_tokens` vs `after_tokens` on the same raw log fixture. No Claude API calls.

Latest run: `2026-04-10T16:29:14Z`. Mean reduction 27.3% (range 13.0–42.3%). See `python/evals/reports/safe-mode-report.md`.

### 5.3 Compaction-survival benchmark (offline)

```bash
python3 python/evals/runners/compaction_survival_runner.py
# Output: python/evals/reports/compaction-survival-report.{json,md}
```

Deterministic. `N=2` cases. Verifies that the resume-packet generator retains decisions, modified files, next-step pointers, and stays within a token budget under synthetic noise.

Latest run: `2026-04-10T16:29:16Z`. 2/2 pass. Mean packet size 184 tokens.

### 5.4 Measurement estimator (not a benchmark)

```bash
curl -fsSL .../setup.sh | bash -s -- --measure
```

This is **not** a measurement. It is a formula (`setup.sh:42–100`) applied to file counts. It produces the README's `~103K tokens/session` figure. The constants (`NOISE_PER_SEARCH=10000`, `RESPONSE_PER_SESSION=20000`, etc.) are educated guesses documented inline. They have not been validated against real sessions. The number should be read as **"this is what we'd estimate under these assumptions,"** not **"this is what you'll save."**

We have flagged this in the README (`"Conservative per-session savings"`) but the word "conservative" is load-bearing in a way that should not be taken on faith. Validation against a corpus of real sessions is pending (§9).

---

## 6. Pricing assumptions

All dollar figures in this repo use Sonnet 4.6 pricing as of 2026-04-17:

| Class | USD / million |
|---:|---:|
| Input (fresh) | $3.00 |
| Output | $15.00 |
| Cache read | $0.30 |
| Cache write (5m) | $3.75 |
| Cache write (1h) | $6.00 |

Source: [anthropic.com/pricing](https://www.anthropic.com/pricing). These figures change without notice. Any dollar quote older than the pricing page should be recomputed before being cited.

**We do not** convert Claude Pro / Max plan "5-hour window" savings to dollars — usage-cap headroom is not fungible with dollars. We only quote Pro/Max savings in qualitative terms ("longer sessions before hitting the cap"). README does this correctly.

---

## 7. Current measured results (verbatim, nothing massaged)

### 7.1 Reducer benchmark (offline, deterministic)

Source: `python/evals/reports/safe-mode-report.json`, run `2026-04-10T16:29:14Z`.

| Case | Before tokens | After tokens | Reduction | Protected-string recall |
|---|---:|---:|---:|---:|
| stack_trace_safe | 149 | 86 | 42.3% | 1.00 |
| test_log_safe | 163 | 104 | 36.2% | 1.00 |
| json_safe | 199 | 173 | 13.1% | 1.00 |
| config_safe | 77 | 67 | 13.0% | 1.00 |
| build_log_safe | 566 | 379 | 33.0% | 1.00 |
| lint_output_safe | 599 | 441 | 26.4% | 1.00 |

- Mean reduction: 27.3%. Range: 13.0–42.3%.
- 6/6 reducer cases pass the recall gate (100% of protected strings preserved).
- 1/1 prompt-lint case passes the finding-recall gate.
- `N=6` cases, but each case is a single deterministic transform — no variance to report.

**Scope:** this measures the *reducer* (the hook that compresses tool output before Claude sees it). It does not measure downstream session-level savings, because Claude would react differently to the compressed output in a real session. We consider this a **lower bound** on the reducer's contribution but cannot yet quantify the session-level multiplier.

### 7.2 Compaction-survival benchmark

Source: `python/evals/reports/compaction-survival-report.json`, run `2026-04-10T16:29:16Z`.

| Case | Decision | Files | Next-step | Packet size | Pass |
|---|---:|---:|---:|---:|---|
| resume_packet_preserves_critical_state | 1.00 | 1.00 | 1.00 | 207 tok | yes |
| resume_packet_stays_within_budget_under_noise | 1.00 | 1.00 | 1.00 | 161 tok | yes |

- 2/2 cases pass.
- Packet size within budget on both.
- Failed-approach retention 1.00 and 0.00 respectively — the second case deliberately tests graceful degradation under noise; we retain pinned facts and drop failed approaches under budget pressure. Passing gate is "pinned / current-subtask / latest-decision / modified-files retention = 1.0". Failed-approach retention is not a gate.

This is **not** a token-savings benchmark. It's a correctness benchmark for the session-memory technique (row 16 in the README's techniques table). Token savings from session memory come from not re-explaining after a restart — unmeasured (§9).

### 7.3 End-to-end benchmark

Source: `python/evals/reports/benchmark-fixture-20260415.json`, run `2026-04-15` (single run, `N=1`).

```
target:  /tmp/cos-bench-test  (2 files: README.md, one .js)
task:    "List the top-level directory structure of this repo,
          then count source files by language. One line per language."
model:   sonnet
```

| Metric | Before | After | Δ |
|---|---:|---:|---:|
| `input_tokens` | 5 | 4 | −1 |
| `cache_read_input_tokens` | 74,064 | 48,182 | −25,882 |
| `cache_creation_input_tokens` | 5,255 | 5,556 | +301 |
| `output_tokens` | 466 | 294 | −172 |
| **`total_tokens`** | **79,790** | **54,036** | **−25,754 (−32.3%)** |
| **`total_cost_usd`** | **$0.04893** | **$0.03971** | **−$0.00922 (−18.8%)** |

**What to read from this:**

1. Most of the token delta is `cache_read_input_tokens` (−25,882). This is the system prompt / tool schema load. On a 2-file repo there is effectively no "user content" to filter — the saving comes from Claude Code loading a leaner working set because `.claudeignore` blocks the phantom directories the scanner would otherwise stat.
2. Output-token delta is −172 (−36.9%). Consistent with the upstream 40–65% claim for response shaping on explanatory prompts.
3. Cache-creation ticks **up** (+301). This is the Context OS CLAUDE.md + settings overhead. As predicted in §4.5.
4. Cost reduction (18.8%) is lower than token reduction (32.3%) because cache reads are cheap ($0.30/M). The composition of savings matters.
5. **`N=1`. No variance. Do not generalize.**

---

## 8. Per-technique evidence class

For each technique in the README, we tag the evidence supporting its token-savings claim. Four classes:

- **M** — directly measured in this repo, with a report artifact linked.
- **U** — cited from an upstream measurement we have read and consider credible.
- **D** — derived from documented Anthropic behavior (env vars, pricing, etc.) with arithmetic we can show.
- **N** — non-token (UX / safety / correctness). No token claim.
- **P** — pending measurement. We have a plan but no number yet.

| # | Technique | Claim | Evidence | Source / pending work |
|---|---|---|:-:|---|
| 1 | Response shaping | 40–65% output tokens | U | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) benchmark. Our 2-file fixture saw 36.9% (consistent with low end). |
| 2 | Output style `terse` | Stacks with #1 | P | No isolated measurement. Expected effect: incremental 5–15% beyond CLAUDE.md. Would need ablation runs. |
| 3 | Noise filtering | 30–40% context reduction on Next.js | U | [Anthropic docs on ignore files](https://code.claude.com/docs/en/memory). Validated qualitatively on tiny fixture (−25,882 cache_read). |
| 4 | Secret exclusion | Security property | N | Not a token claim. |
| 5 | Repo map + stack hints | Saves 3–10 tool calls/session | D | Each avoided Glob/Grep call ≈ 200–2,000 tokens depending on result size. 3 × 500 ≈ 1,500 lower bound. |
| 6 | Thinking budget cap | 50–70% on simple tasks | D | Default `MAX_THINKING_TOKENS` per [Anthropic extended-thinking docs](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking) is 32K+. 8K cap → ~75% reduction on thinking-budget when fully spent. Claimed range 50–70% assumes partial use. Pending empirical validation. |
| 7 | Early compaction (80%) | "Keeps context small" | D | Arithmetic: compacting at 80% vs 95% reduces per-turn input by ~15% late in long sessions. No measurement. |
| 8 | Prompt caching 1h | "Massive on long sessions" | D | Arithmetic from [prompt-caching docs](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching): a session that re-uses cache 12× at 1h TTL vs 2× at 5m TTL → 6× fewer cache writes. Unquantified in absolute terms. |
| 9 | Traffic control (disable nonessential) | "Silent burn eliminated" | D | `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` disables auto-titling + telemetry per [Claude Code env vars](https://code.claude.com/docs/en/settings). Effect size per session: 100s–1000s of tokens, unmeasured. |
| 10 | Context cap (150K) | "Faster compaction" | D | Arithmetic. No standalone measurement. |
| 11 | Permission auto-grant | ~200–500 tokens/confirmation | D | Each permission prompt adds a tool_result round-trip. 200–500 token range is an estimate from inspection of raw transcripts. Not measured at scale. |
| 12 | statusLine | UX only | N | No token claim. |
| 13 | Slash commands | Structured efficiency | N / P | `/cheap` has token impact (routes to Haiku); others are organization. Haiku routing savings: see #14. |
| 14 | Haiku subagent (explorer) | ~93% on exploration | D | Pricing arithmetic: Haiku 4.5 input $0.80/M vs Sonnet 4.6 $3.00/M ≈ 73% cheaper on input; output $4 vs $15 ≈ 73% cheaper. Isolated subagent context adds savings. Claimed 93% is an upper bound for exploration-heavy tasks. Has **not** been benchmarked in our harness. |
| 15 | Output compression (hooks) | 27–70% on test runs | **M** | `python/evals/reports/safe-mode-report.md`. Measured 13.0–42.3% per fixture; 71% on 50-test cargo run cited in README is from a separate `cargo test` trace (pending formal reproduction — this number should not be taken as measured under our gates until a report artifact is produced). |
| 16 | Session memory | Survives compaction | **M** | `python/evals/reports/compaction-survival-report.md`. 2/2 cases pass correctness gates. Token-savings contribution (from not re-explaining) is unmeasured. |

### Summary by evidence class

| Class | Count | Techniques |
|---|---:|---|
| **M** (directly measured) | 2 | #15 (output compression, partial), #16 (session memory, correctness only) |
| **U** (upstream citation) | 2 | #1 (response shaping), #3 (noise filtering) |
| **D** (derived arithmetic) | 8 | #5, #6, #7, #8, #9, #10, #11, #14 |
| **N** (non-token) | 3 | #4, #12, #13 (partial) |
| **P** (pending) | 1 | #2 |

**Bottom line:** of 16 techniques, **2** have direct measurements in this repo, **2** have upstream measurements, and **8** are arithmetic derivations from documented behavior. This is the honest picture.

---

## 9. Open questions & known unknowns

### 9.1 What would raise our confidence materially

| Gap | What's needed | Effort |
|---|---|---|
| `N=5` on tiny fixture | Wrap `scripts/benchmark.sh` in a loop, randomize order, compute median+IQR | 1 day |
| Pinned fixture repos | Commit small/medium/large synthetic repos at fixed SHAs to the `examples/` tree | 2–3 days |
| Cold-cache vs warm-cache split | Add a 1-hour sleep between runs OR use `--session-id` to force fresh cache | 1 day + 1h wallclock |
| Per-technique ablation | 16 × 3 fixtures × 5 runs = 240 sessions. Automate via `setup.sh --only <tech>` | 1 week + API budget |
| Multi-session (session memory benefit) | Scripted sequence: session A writes files, `/compact`, session B resumes, measure delta | 3 days |
| Real-session corpus | Partner willing to share opted-in anonymized transcripts for `setup.sh --measure` calibration | Ongoing |
| Haiku subagent savings | Run exploration task with and without `/cheap` flag; compare (cost, output quality) | 2 days |
| Response-shaping isolation | Ablate CLAUDE.md shaping block; measure output-token delta on code-edit vs explanation tasks | 2 days |
| Cost methodology double-check | Cross-check `total_cost_usd` against recomputed blended price; verify no accounting gaps from cache-write tier | 1 day |

### 9.2 What would not raise our confidence

- Running the current `N=1` benchmark on 50 more repos. Without N-within-cell variance, cross-repo comparisons still have no CI. Better to do 5 runs on 5 pinned fixtures than 1 run on 50 random repos.
- Switching to token-counting via `tiktoken` / local estimates. Claude's server-reported token counts are authoritative; any local approximation adds a confound.
- Claiming "up to X%" numbers. We do not quote maxima.

### 9.3 What Anthropic could do that'd help

Nothing strictly required, but would help:

- Publish cache eviction policy (or statistical distribution of TTL-within-TTL).
- Expose a deterministic mode for benchmarking (`temperature=0, seed=<n>` behavior across sessions).
- Document the exact composition of system-prompt / tool-schema cache entries so we can attribute cache-read savings precisely.

---

## 10. Change log

| Date | Version | Change |
|---|---|---|
| 2026-04-17 | 0.3 | Initial rigorous methodology draft. Tagged all 16 techniques with evidence class. Documented N=1 headline weakness. |

---

## Appendix A: Glossary

- **Cache read** (`cache_read_input_tokens`) — tokens served from the prompt-cache tier. Cheap ($0.30/M on Sonnet).
- **Cache creation / write** (`cache_creation_input_tokens`) — tokens written *into* the cache this turn. Charged at a premium over fresh input ($3.75–$6/M depending on TTL).
- **Fresh input** (`input_tokens`) — tokens in the prompt that were neither cached nor cache-written. Charged at standard input rate ($3/M on Sonnet).
- **Output** (`output_tokens`) — model-generated tokens. Most expensive class ($15/M on Sonnet).
- **Session** — one `claude` invocation from start to stop, identified by session id.
- **Task** — one user prompt until the model returns `stop_reason` without a continuing tool call.
- **Fixture** — a pinned, reproducible input artifact (repo or log file) used in a benchmark.
- **Protected string** — a literal (file path, version, shell command, error class) that a safe-mode reducer must not drop.
- **Ablation** — running the full system with one technique disabled, to measure that technique's marginal contribution.

## Appendix B: File index

Everything referenced by this document, for cross-checking:

- `README.md` — headline claims.
- `setup.sh` — installer and `--measure` estimator.
- `scripts/benchmark.sh` — end-to-end benchmark runner.
- `python/evals/runners/safe_mode_runner.py` — reducer benchmark runner.
- `python/evals/runners/compaction_survival_runner.py` — session-memory correctness runner.
- `python/evals/datasets/safe_mode_cases.json` — reducer fixture manifest.
- `python/evals/datasets/compaction_survival_cases.json` — session-memory fixture manifest.
- `python/evals/reports/safe-mode-report.{json,md}` — latest reducer benchmark.
- `python/evals/reports/compaction-survival-report.{json,md}` — latest session-memory benchmark.
- `python/evals/reports/benchmark-fixture-20260415.json` — the single-run end-to-end result.
- `docs/benchmark-plan.md` — pre-existing benchmark scope notes (superseded by this document on the measurement-rigour dimension).
- `docs/limitations.md` — shipping-time honest limitations.

## Appendix C: Contact

Methodological objections are the whole point of publishing this document. Open an issue at [github.com/sravan27/context-os](https://github.com/sravan27/context-os/issues) with the tag `methodology` and we will address it in the change log.
