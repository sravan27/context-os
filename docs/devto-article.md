---
title: "I Stacked Every Claude Code Token Optimization Into One Curl Command"
published: false
tags: claude, ai, productivity, opensource
canonical_url: https://github.com/sravan27/context-os
---

## TL;DR

- Claude Code has a 5-hour rate window. Every token counts.
- ~12 proven techniques measurably reduce token usage. Each lives in a different repo.
- `curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash` installs all of them. Dry-run first with `--measure`.

---

## The problem

Claude Code — Anthropic's CLI coding agent — caps usage by rolling 5-hour windows. On Pro that window is narrower than you think. You hit it mid-refactor, sit there for forty minutes, forget what you were doing, `/clear` the wrong session.

Every token spent on `node_modules/` paths you'll never read, every paragraph of "I'll take a look at that for you!" preamble, every tool announcement — it's burning your window.

I spent a week reading every thread and every GitHub repo claiming token savings. I found about twelve techniques that *measurably* work. They live in a dozen different places. You can install four tools, maintain four configs, and still miss things that need custom integration (env vars, secret filtering, Haiku subagents, output-style, statusLine).

I wanted **one command**.

## The 12 techniques

Here's the full list, in install order. Each row has a documented savings citation — no hand-waving.

| # | Technique | What it does | Measured savings |
|---|---|---|---|
| 1 | **Response shaping** (CLAUDE.md) | Drops preamble, recap, filler, tool announcements | 40–65% output tokens ([caveman benchmark](https://github.com/JuliusBrussee/caveman)) |
| 2 | **Output style `terse`** (.claude/output-styles/) | Deeper response contract than CLAUDE.md — enforced at every turn | Stacks with #1 |
| 3 | **.claudeignore** (noise filtering) | Blocks `node_modules`, `dist`, `.next`, `target`, 60+ dirs + lock files | 30–40% context in Next.js repos |
| 4 | **Secret exclusion** (.claudeignore) | `.env`, `*.pem`, `credentials.json`, SSH keys, AWS creds | Security + tokens |
| 5 | **Repo map + stack hints** (CLAUDE.md) | Stack-specific hints (Next, Python, Rust, Go, Flutter) + dir index | Saves 3–10 Bash/Glob calls/session |
| 6 | **Thinking budget cap** (settings.json) | `MAX_THINKING_TOKENS=8000` — default is 32K+ | 50–70% on simple tasks |
| 7 | **Early compaction** (settings.json) | `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80` (default is 95) | Smaller context per turn |
| 8 | **statusLine** (.claude/statusline.sh) | Live model · branch · context-os ✓ indicator | Awareness > guessing |
| 9 | **Slash commands** (.claude/commands/) | `/compact` `/context` `/ship` | Structured efficiency |
| 10 | **Haiku subagent** (.claude/agents/explorer.md) | Exploration on Haiku (15× cheaper) in isolated context | ~93% on exploration |
| 11 | **Output compression** (hooks) | Test/build output reduced before Claude reads it | 27–70% on test runs |
| 12 | **Session memory** (hooks) | Decisions captured before compaction/session end | Survives restarts |

Steps 1–10 need only `curl | bash`. Steps 11–12 need the optional Rust binary (one `cargo install` away).

## See what you'd save — no install

The scariest thing about optimization tools is they write files you didn't ask for. So the first thing `setup.sh` supports is a dry run:

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --measure
```

It scans your repo, counts source files vs. noise files, and prints a conservative estimate based on documented per-technique savings:

```
  Source files:            342
  Noise files:             12,847

  Conservative per-session savings:

  Noise filtering:         ~50K tokens
  Response shaping:        ~20K tokens
  Thinking cap (8K):       ~15K tokens
  Haiku exploration:       ~10K tokens
  Output compression:      ~8K tokens
  ────────────────────────────────────
  TOTAL:                   ~103K tokens/session

  Pro/Max plan:            longer sessions before hitting 5-hr cap
  API users (Sonnet 4.6):  ~$0.61/session ($12/week @ 20 sessions)
```

Conservative Sonnet 4.6 blended pricing ($6/M). No config. No writes. No install.

## Install

```bash
cd your-project
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

That's the whole install. It's idempotent — run it twice, you get exactly one copy of the CLAUDE.md block (marker-delimited with `<!-- context-os:start -->` / `<!-- context-os:end -->`).

It's reversible:

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --uninstall
```

`--uninstall` removes the context-os files and strips the marker block from CLAUDE.md — **but preserves any content you added to CLAUDE.md yourself.** Your hand-written response rules stay. Only the auto-generated block between the markers is removed.

There's also a `--global` flag that installs the response-shaping block + env tuning to `~/.claude/` so it applies to every project:

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --global
```

## Real benchmark (not speculative)

The `--measure` flag is math. For actual numbers, there's a benchmark script:

```bash
git clone https://github.com/sravan27/context-os
cd context-os
scripts/benchmark.sh /path/to/your/repo --model sonnet
```

It clones your repo to `/tmp`, runs a canonical task against it twice — once without Context OS, once with — by shelling out to `claude --print --output-format json`. Then it parses Claude Code's real usage report (input tokens, cache reads, cache writes, output, total_cost_usd) and prints the delta.

Against a trivial 2-file fixture:

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Input tokens | 5 | 4 | −1 |
| Cached reads | 74,064 | 48,182 | −25,882 |
| Output tokens | 466 | 294 | −172 |
| **Total tokens** | **79,790** | **54,036** | **−32%** |
| **Cost (USD)** | **$0.049** | **$0.040** | **−18.8%** |

That's on a 2-file repo. On real projects with actual `node_modules`, `dist`, `.next` — reductions get **larger**, not smaller, because noise filtering scales with the size of what you're ignoring.

## What it doesn't do

Honest limitations (copied from the README):

- Doesn't bypass Anthropic usage limits. Makes them hurt less.
- Response-shaping effectiveness varies: 40–65% on explanation-heavy tasks, 13–21% on already-structured code.
- Haiku subagent quality varies. Complex reasoning → main session.
- Hook-based compression depends on Claude Code hook availability.
- The ~12–15% overhead from the CLAUDE.md block pays for itself in 1–2 turns on non-trivial sessions.

## The techniques that don't automate (but are worth knowing)

Context OS automates what can be automated. These can't, but they round out the stack:

- **`/clear`** between unrelated tasks. Stale context costs tokens on every message.
- **`/btw [question]`** for side questions that don't need to persist.
- **Plan mode** (Shift+Tab) for exploration without execution.
- **Specific prompting.** `fix the null check in auth.ts:42` vs `improve the auth code`.
- **`@filename`** references instead of making Claude search.
- **Writer/reviewer pattern.** Session 1 implements, fresh session 2 reviews.
- **Invoke the explorer subagent explicitly.** *"use the explorer subagent to find all callers of `authenticate`"*.

## How to contribute

If you know a technique that measurably reduces Claude Code token consumption and it's not in the [12-row table](https://github.com/sravan27/context-os#what-it-does-in-order), I want it. Open an issue with your benchmark numbers and how to automate it. The goal is **completeness** — every proven technique in one command.

Bar for inclusion:

1. **Measurable.** "Feels faster" doesn't count. Show the delta.
2. **Automatable.** Can be installed via shell or hook. Anything requiring manual intervention belongs in the "manual techniques" list, not the installer.
3. **Reversible.** `--uninstall` must cleanly remove it.
4. **Idempotent.** Re-running `setup.sh` must not compound the change.
5. **Zero-dependency by default.** Core install is sh-only. Hook-based optimizations can require the Rust binary.
6. **Safe.** Never touch untracked files, never commit, never delete user content.

## Links

- **Repo:** https://github.com/sravan27/context-os
- **Measure (no install):** `curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --measure`
- **Install:** `curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash`
- **Issues:** https://github.com/sravan27/context-os/issues

If this saved you a 5-hour window, star the repo — that's how it gets found by the next person about to hit the wall.
