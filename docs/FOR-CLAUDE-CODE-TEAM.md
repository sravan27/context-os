# Notes from Context OS to the Claude Code team

We're the maintainers of [Context OS](https://github.com/sravan27/context-os) — a one-command installer that applies 16 token-optimization patterns on top of Claude Code (env vars, hooks, a default `.claudeignore`, a small Rust reducer, session-memory hooks). We built it because we kept burning through our own quotas on the same three or four failure modes, and we shipped it MIT-licensed so we could stop patching it privately on every machine. Writing this because a handful of the patterns feel upstream-worthy, not wrapper-worthy, and you have the telemetry to confirm or kill each one. No pitch; just receipts and hypotheses.

---

## Three findings we think are worth acting on

### 1. Default `MAX_THINKING_TOKENS` is too high for most Claude Code tasks

**What we see.** Extended thinking defaults to 32K+ tokens. In a typical Claude Code session the model is doing `Read file → Edit function → run test → Read another file`. Those are short-horizon, single-step decisions. Thinking budget on the order of 32K is almost pure waste — the model spends tokens deliberating over a 40-line diff that it already knows how to write.

**Our fixture.** On a sample of 50 short-edit tasks from our repo we capped `MAX_THINKING_TOKENS=8000` and saw no regression in output quality (manual review, small N — we're not claiming statistical significance). Token spend on thinking dropped by roughly an order of magnitude on those tasks.

**Recommendation.**
- Ship with an 8K default for Claude Code specifically (the CLI knows its own task distribution better than the general API default).
- Surface the per-task thinking budget in the UI — even a one-line "thinking: 1.2K / 8K" indicator would let users self-correct.
- Keep the 32K ceiling available for users who opt in (design work, planning, hard debugging).

**Where to steal from.** `setup.sh` in Context OS sets `MAX_THINKING_TOKENS=8000` as the default and documents it as reversible.

---

### 2. AutoCompact at 95% is too late

**What we see.** The default AutoCompact threshold fires at ~95% of the context window. By the time it fires, the user has already accumulated ~180K tokens of context that Claude has been re-sending on every turn for the last N minutes. Several of our users hit rate limits *before* AutoCompact fires, which means the safety net doesn't save them — it just tidies up after the bill.

**Why 95% is the wrong number.** Compaction is approximately free to trigger at 80% and approximately free to trigger at 95%. The cost is monotonic in how long you wait — every tool call after 80% pays the re-send tax on an ever-growing window. There is no upside to waiting until 95%.

**Recommendation.**
- Drop the default to 80%.
- Expose the threshold as a first-class setting in `settings.json` (today `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` works but isn't documented — see ask #1 below).
- Consider compacting progressively (summarize oldest 20% at 70%, next 20% at 80%) instead of one big compact at the end.

**Where to steal from.** Context OS sets `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80` and nudges the user at 70% via a statusLine hint.

---

### 3. No default noise-filtering means new users burn tokens on their first Glob

**What we see.** Fresh `npx create-next-app` project. User opens Claude Code, types "help me add a login page." Claude runs `Glob **/*` to orient. `node_modules/` is indexed by default. Result: on the order of 3M tokens of vendored JS noise pulled into context before any real work has started. Same pattern with Rust `target/`, Python `.venv/`, `dist/`, `.next/`, `__pycache__/`.

We see this constantly in support threads on the Context OS repo. It's the single biggest "new user gets confused about why Claude is slow/expensive" failure mode we've observed.

**Recommendation.**
- Ship a default `.claudeignore` with the standard suspects: `node_modules`, `target`, `dist`, `build`, `.next`, `.nuxt`, `.venv`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `coverage`, `vendor`, `*.lock` (debatable but probably yes).
- Make it clearly user-extensible (`.claudeignore.local` or similar).
- Document precedence rules (`.gitignore` vs. `.claudeignore`).

**Where to steal from.** Our default `.claudeignore` has ~60 patterns across JS / Python / Rust / Go / Java / mobile. MIT licensed, grab what's useful.

---

## Three smaller observations

**Haiku subagents are invisible.** Users don't discover that they exist until someone tells them. For exploration tasks (Grep-heavy, Read-heavy, "where is X defined"), Haiku is roughly 15x cheaper with no practical quality loss. A one-click "Run this on Haiku" affordance on exploration-shaped tasks would change default behavior without any user education.

**Tool-call dedup would save ~30% of Reads.** In session transcripts we've sampled, users (via Claude) re-Read the same file 3-5x per session — once on discovery, again when returning to context, again after an edit in a nearby file. A PostToolUse content-hash cache keyed on `(file_path, mtime)` skips the re-read and re-injects the prior contents. Our implementation is `hooks/dedup-reads.py` in the repo. Cheap to prototype; potentially a large win if it holds up at scale.

**Loop detection.** Pattern: `Read foo.ts → Edit foo.ts → Read foo.ts → Edit foo.ts` on the same file 4+ times with no test run in between. That's a stuck model, not a productive one. A soft warning in the UI ("you've been iterating on foo.ts — consider /compact or a different approach") would catch the worst sessions before they burn a whole quota.

---

## What we are not claiming

We have not measured any of this at Anthropic scale. We have:
- our own fixtures (small N, manual quality review),
- shipped patterns that we and our users find useful,
- open-source code you can read in an afternoon.

You have the real telemetry. Treat everything above as hypotheses worth testing, not conclusions. If any of it is wrong in production, we'd rather know than keep shipping it.

---

## Specific upstream asks

These would meaningfully help us help users:

1. **Publish the official env var list.** Today we find `MAX_THINKING_TOKENS`, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, `DISABLE_AUTOUPDATER`, `BASH_DEFAULT_TIMEOUT_MS`, etc. by running `strings` on the binary and diffing across versions. A documented list (even a "subject to change" one) would let us stop guessing and let you stop having third parties reverse-engineer the surface.

2. **Stable hook API versioning.** Our hooks broke twice in the last two minor releases because the JSON payload shape changed silently. A `hookApiVersion` field in `settings.json` (or a version header in the payload) would let us pin compatibility.

3. **A `claude --token-report` flag.** Dumps per-tool-call token usage for the last session as JSON. Today we instrument this ourselves with wrapper scripts; doing it natively would be 20 lines and unblock a ton of community tooling.

4. **Token budget per task as a settings option.** Hard cap: "fail this task if it exceeds 50K tokens." Currently the only backstop is AutoCompact and quota exhaustion. A pre-emptive ceiling (configurable, default off) would let teams set guardrails without writing custom hooks.

---

## What we've shipped that you're welcome to review or steal

All MIT-licensed. Links relative to [github.com/sravan27/context-os](https://github.com/sravan27/context-os).

- **`setup.sh`** — idempotent, reversible installer. Detects OS / shell / existing settings, writes an additive patch, leaves a rollback file. Pattern might be useful for Claude Code's own plugin system.
- **`crates/reducer-engine/`** — small Rust crate that wraps test/build tool output and keeps only the failing lines + context. Safe-mode: never drops stderr, never rewrites user code. ~800 LOC.
- **`hooks/session-memory.py`** — writes salient facts to `.context-os/session.md` so they survive `/compact`. Loaded on session start.
- **`crates/repo-memory/`** — multi-stack repo-map generator (JS, Python, Rust, Go). Runs once on session start, produces a ~2K token summary of project structure. Cheaper than letting Claude Glob it fresh.
- **`hooks/dedup-reads.py`** — the content-hash Read cache from observation #2 above.
- **`python/evals/`** — fixtures and harness we use internally. Not production-grade but might be useful as a reference for what community evals look like.

Happy to walk any of this through on a call, or to rip out / rewrite anything that conflicts with direction you've already set internally.

---

## Closing

We'd love feedback. If something here is wrong, tell us and we'll fix it in the repo. If something is right and you want to ship it natively, please do — that's a better outcome than us maintaining a wrapper. We're not selling anything and we're not looking for a partnership announcement; we'd just like the patterns that work to end up in the place where they'll help the most people.

Reachable at the GitHub issues on the repo, or directly at the maintainer email in the README.

— Context OS maintainers
