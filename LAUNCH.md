# Launch playbook

Everything needed to distribute Context OS. Not committed to make the repo root noisy — delete before a community linter complains if you like. The artifacts here are **copyable**: go to the target, paste, post.

## Ground rules

1. **No dead repos.** Every target below has >1k stars AND a commit in the last 90 days — verified via `gh repo view`.
2. **One channel per day.** Avoid looking like a coordinated spam wave.
3. **Measure + reply.** After posting, come back in 6h to reply to the first 3 comments. First replies drive thread ranking everywhere.
4. **Everything links to `--measure`.** Nobody trusts screenshots. `curl | bash -s -- --measure` is the best possible demo — no install, no config, 8 seconds.

---

## Submission order (by expected ROI)

| # | Channel | When | Priority |
|---|---|---|---|
| 1 | `hesreallyhim/awesome-claude-code` PR | Day 1, 09:00 PT | **P0** — canonical, 38k stars |
| 2 | HN Show HN | Day 1, 07:30 PT (Tue or Wed) | **P0** |
| 3 | r/ClaudeAI | Day 1, 10:00 PT | **P0** |
| 4 | X/Twitter thread | Day 1, 09:30 PT | **P1** |
| 5 | `travisvn/awesome-claude-skills` PR | Day 2 | **P1** — 11k stars, CONTRIBUTING.md clear |
| 6 | `VoltAgent/awesome-claude-code-subagents` PR | Day 2 | **P1** — 17k stars, fits (we ship Haiku subagent) |
| 7 | `jamesmurdza/awesome-ai-devtools` PR | Day 3 | P2 — 3.7k, DevTools-focused |
| 8 | `steven2358/awesome-generative-ai` PR | Day 3 | P2 |
| 9 | dev.to article | Day 4 | P2 — long-tail SEO |
| 10 | r/LocalLLaMA secondary post (angle: Haiku subagent cost) | Day 5 | P3 |

---

## 1. Show HN post

**Title** (max 80 chars, title-case discouraged):

```
Show HN: Context OS – every Claude Code token optimization in one command
```

**Body** (4 short paragraphs, HN prefers terse):

```
Claude Code has a 5-hour rate window. If you hit it, you wait. Every token counts.

There are ~12 techniques that measurably reduce Claude Code token usage: response
shaping (CLAUDE.md), output style enforcement, .claudeignore noise filtering,
thinking budget caps, early compaction, Haiku subagent for exploration, output
compression hooks, session memory hooks. Each one lives in a different repo.

Context OS is one command that installs all of them:

    curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash

Before you install, you can dry-run it to see what you'd save:

    curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --measure

That scans your repo (no writes, no config) and prints a conservative estimate of
tokens saved per session, based on file counts and documented per-technique savings.
Real benchmark script is `scripts/benchmark.sh` — runs the same task against a repo
before and after install, reads Claude Code's JSON output, reports measured delta.
On a 2-file fixture: 32% fewer tokens, 18.8% lower cost. Bigger repos benefit more
because noise filtering scales with the size of node_modules/dist/.next/target.

Repo: https://github.com/sravan27/context-os

Fully reversible (`--uninstall`), zero dependencies, MIT. Feedback on techniques
I'm missing especially welcome — the goal is completeness.
```

**First-comment reply template** (have ready, paste within 2 hours):

```
A few things I should've put in the post:

- It's a shell script + optional Rust binary. Core install is sh-only. Binary
  adds two hook-based optimizations (output compression, session memory).
- It ships a Haiku subagent (`.claude/agents/explorer.md`) so exploration runs
  on the cheaper model in an isolated context. Main session doesn't pay for it.
- --measure uses Sonnet 4.6 blended pricing ($6/M) — not Opus. I got this wrong
  in an earlier version.
- Works alongside caveman, RTK, claude-mem if you're already using them, but
  there's overlap. The README has a side-by-side matrix.

If you hit an issue on a stack we don't detect (next/python/rust/go/flutter),
please file — stack hints are easy to add and make a real difference.
```

---

## 2. Reddit r/ClaudeAI

**Subreddit:** r/ClaudeAI (250k+ subs, active) — also consider r/ChatGPTCoding, r/LocalLLaMA as secondaries.

**Title** (reddit rewards curiosity + stakes):

```
I stacked every known Claude Code token optimization into one curl command. 32% token reduction measured on a trivial fixture.
```

**Body** (Reddit allows more length than HN — lead with pain, show the table):

```
Hitting the 5-hour window on Pro has been killing my flow. Spent a week reading
every Claude Code optimization thread and every repo that claims token savings.
There are about 12 techniques that actually measure out. Each lives in a
different tool. I wanted one command.

**What it installs:**

| # | Technique                           | Savings |
|---|-------------------------------------|---------|
| 1 | Response shaping (CLAUDE.md)        | 40-65% output tokens |
| 2 | Output style `terse`                | Stacks with #1 |
| 3 | .claudeignore (node_modules, etc.)  | 30-40% context |
| 4 | Secret exclusion (.env, *.pem)      | Security + tokens |
| 5 | Repo map + stack hints              | Saves 3-10 exploration calls |
| 6 | MAX_THINKING_TOKENS=8000            | 50-70% on simple tasks |
| 7 | Early compaction (80% vs 95%)       | Smaller context per turn |
| 8 | statusLine awareness                | Awareness > guessing |
| 9 | /compact /context /ship commands    | Structured efficiency |
| 10| Haiku subagent (explorer)           | ~93% on exploration |
| 11| Output compression hooks            | 27-70% on test runs |
| 12| Session memory hooks                | Survives compaction |

**See what you'd save without installing:**

```
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --measure
```

No writes, no config — scans your repo and estimates savings.

**Install:**

```
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

Fully reversible. `--uninstall` preserves your existing CLAUDE.md content.

**Benchmark:** `scripts/benchmark.sh` runs the same task before/after install,
reads Claude Code's JSON output, reports real input/output/cache tokens and
cost. On a 2-file fixture I got 32% fewer tokens and 18.8% lower cost — bigger
repos benefit more (noise filtering scales with node_modules/dist/target size).

Repo: https://github.com/sravan27/context-os

Feedback very welcome — especially if you know a technique I missed. The goal
is completeness.
```

---

## 3. X/Twitter thread

**Tweet 1** (hook):

```
Claude Code has a 5-hour rate window.

Every token counts.

There are ~12 techniques that measurably reduce token usage. Each lives in a
different repo.

I stacked all of them into one curl command.

👇
```

**Tweet 2** (proof):

```
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --measure

No install. No writes. Scans your repo and tells you what you'd save.

Conservative Sonnet 4.6 pricing. ~103K tokens/session on a mid-size Next.js repo.
```

**Tweet 3** (table image — screenshot the 12-row README table):

```
The full stack:

• Response shaping (CLAUDE.md)
• Output style `terse`
• .claudeignore (60+ noise dirs + lock files)
• Secret exclusion
• Repo map + stack hints
• MAX_THINKING_TOKENS=8000
• Early compaction at 80%
• statusLine
• /compact /context /ship
• Haiku subagent (15× cheaper exploration)
• Output compression hooks
• Session memory hooks
```

**Tweet 4** (install):

```
One command installs everything:

curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash

Zero dependencies. Fully reversible (--uninstall preserves your CLAUDE.md).
Works with Pro, Max, API.
```

**Tweet 5** (proof/ask):

```
Real benchmark (not speculative): 32% tokens, 18.8% cost on a 2-file fixture.
Bigger repos benefit more — noise filtering scales with node_modules/dist/target.

https://github.com/sravan27/context-os

If you know a technique I missed — open an issue. The goal is completeness.
```

---

## 4. Awesome-list PR bodies

### hesreallyhim/awesome-claude-code (P0 — 38k stars, canonical)

Their submission flow uses a `/add` slash command in an issue, not a raw README PR. Open issue:

```
Title: /add Context OS — every Claude Code token optimization in one command

Body:

- **Name:** Context OS
- **URL:** https://github.com/sravan27/context-os
- **Category:** Tooling / Optimization
- **Description:** One curl command that installs every measurable Claude Code
  token optimization: response shaping (CLAUDE.md), output style `terse`,
  .claudeignore noise filtering + secret exclusion, repo map + stack hints,
  MAX_THINKING_TOKENS cap, early compaction at 80%, statusLine, slash commands
  (/compact /context /ship), Haiku explorer subagent, output compression hooks,
  session memory hooks. Zero dependencies. Fully reversible. `--measure` flag
  shows per-session savings before installing. Real benchmark script against
  any git repo.
- **License:** MIT
- **Stars at submission:** (fill in)
- **Maintained:** yes, active (v1.1.0 tagged, CI green on macOS + Linux)
```

### travisvn/awesome-claude-skills (P1 — 11k stars)

Their CONTRIBUTING.md says "raw README edit PR." Add under the "Tools" or "Optimization" section (verify current section structure when opening PR):

```
- **[Context OS](https://github.com/sravan27/context-os)** — Every measurable
  Claude Code token optimization in one curl command (response shaping,
  .claudeignore, thinking budget cap, Haiku explorer subagent, output
  compression hooks, session memory). Zero dependencies. Fully reversible.
  `--measure` flag estimates per-session savings without installing.
```

PR body:

```
## Summary

Adds Context OS — a one-command installer that stacks every measurable Claude
Code token optimization (response shaping, noise filtering, thinking budget
caps, Haiku subagent, output compression hooks, session memory).

## Why it fits this list

Directly targets Claude Code users. Ships a Haiku subagent, hooks, slash
commands, statusLine, output-style — all Claude Code-specific features.

## Artifact

- Repo: https://github.com/sravan27/context-os
- License: MIT
- CI: green on macOS + Linux (https://github.com/sravan27/context-os/actions)
- Benchmark script included (scripts/benchmark.sh) — 32% token reduction
  measured on a trivial fixture using real `claude --print` invocations.
```

### VoltAgent/awesome-claude-code-subagents (P1 — 17k stars)

Add under the "Companion tools" or "Tools" section — we ship an explorer subagent:

```
- **[Context OS](https://github.com/sravan27/context-os)** — Bundles an
  explorer subagent (Haiku, 15× cheaper) alongside 11 other Claude Code token
  optimizations in one curl install. Explorer runs in an isolated context
  window so main session doesn't pay for exploration.
```

### jamesmurdza/awesome-ai-devtools (P2 — 3.7k stars)

Under "CLI Tools" or "AI Coding Agents":

```
- **[Context OS](https://github.com/sravan27/context-os)** — Claude Code token
  optimization layer. Response shaping, noise filtering, Haiku subagent for
  exploration, output compression hooks. One curl command. MIT.
```

---

## 5. dev.to article

**Title:** "I Stacked Every Claude Code Token Optimization Into One Curl Command"

**Tags:** claude, ai, productivity, opensource

**TL;DR:** 3 lines.

**Structure:**
1. The 5-hour window problem (1 paragraph, link to anthropic docs)
2. The 12 techniques with measured citations (table, link to caveman + drona23)
3. The install command + `--measure` dry run (code block)
4. Real benchmark results (the fixture table)
5. What it doesn't do (honest limitations from README)
6. How to contribute a technique
7. Close + repo link

Target length: 1200-1800 words. dev.to's sweet spot.

Draft it offline, paste into dev.to editor, set canonical URL to `https://github.com/sravan27/context-os/blob/main/README.md` so you don't split SEO with your repo.

---

## 6. Monitoring

After each channel goes live:

```
# CI status (we've had 2 past failures — check before and after each push)
gh run list --workflow=ci.yml --limit 5

# HN post rank (replace ID after posting)
open https://news.ycombinator.com/item?id=XXXXXXXX

# Reddit sort by new then controversial
open https://www.reddit.com/r/ClaudeAI/new/

# Repo traffic
gh api repos/sravan27/context-os/traffic/views
gh api repos/sravan27/context-os/traffic/clones
```

First 24h: reply to every comment. Second 24h: reply to threaded discussions.
Third day: tally stars + star velocity, decide whether to push the P2 channels.

---

## 7. Things that failed last time (don't repeat)

- Submitting to lists with 0 stars / no traffic. Wasted effort.
- Posting to HN on a Friday afternoon. Dead zone.
- Long Reddit titles with adjectives. Stripped by the algorithm.
- Twitter threads without a clear hook in tweet 1. Dies at tweet 2.
- Posting without a ready first-comment reply. Thread momentum dies in 90 min.
