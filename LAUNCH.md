# LAUNCH

The whole launch in one file. **Tuesday 8:00–9:30 AM US Eastern** is the window — HN traffic peaks then. Click each link, paste each block, in order. Roughly **30 minutes** of clicks-and-pastes; everything below is reframed honest after the cold-cache caveat audit.

Do not start before Monday night. Do not post on Saturday/Sunday — Show HN dies on weekends.

---

## 0 · Pre-flight (Monday night, 5 min)

- [ ] Run `python3 python/evals/runners/ranker_floor.py` cold — all 9 floors green
- [ ] Run `python3 python/evals/runners/savings_test.py` — `all checks passed`
- [ ] `git status` clean, latest commit pushed
- [ ] Browser tabs open for: HN submit, X compose, Reddit submit, LinkedIn share, Anthropic Discord, Anthropic plugin form

---

## 1 · Show HN  ·  T+0  ·  the load-bearing one

**Click:** https://news.ycombinator.com/submit

**Title field** (paste verbatim):

```
Show HN: A 400-line hook so Claude Code opens the right file instead of grepping
```

**URL field**:

```
https://github.com/sravan27/context-os
```

**Text field** — *leave blank.* HN's algorithm prefers URL-only submissions; the body goes in the first comment.

After submitting, **immediately scroll to step 2 ↓** (within 60 seconds — HN rewards OP engagement on its own thread).

---

## 2 · HN first comment  ·  T+1 min

In the thread you just created, click "reply" on your own post and paste:

```
Built this because Claude Code's first turn reliably burns ~35k tokens on
Glob → Grep → Read → Read → Read before doing anything useful. The model has
no map of the repo going into turn 1, so it grep-walks one.

The hook (UserPromptSubmit, ~400 lines stdlib Python) pre-builds a static
graph of the repo (symbols + line ranges + imports + git-hot files) and
injects ranked file:line candidates before Claude sees the prompt. Plus
smart_read (PreToolUse) intercepts whole-file Reads of big indexed files and
returns the outline so Claude reads only the slice it needs.

What's load-bearing — the version-independent, CI-gated claim:
- MRR 0.984 synthetic (Py/TS/Rust), 0.756 on this repo, beats BM25 in every
  language across 3 unseen OSS repos (axios/ripgrep/requests, weighted MRR
  0.545 vs 0.461). Quality regression floor red-lines the PR if it drifts.

The number you should not over-read:
- A `claude --print` A/B showed −40.9% tokens (N=36, p=5e-7). Honest caveat:
  cold-cache one-shots. Warm interactive sessions reuse cache so the dollar
  delta is smaller — the durable wins are fewer first-turn tool calls and
  hitting compaction/limits later, not a flat 41% off the bill.

Don't trust my A/B — replay it on your own Claude Code history, $0, no API:
  python3 python/evals/runners/replay_history.py

Reproduce in 5 min:
  git clone https://github.com/sravan27/context-os && cd context-os
  python3 python/evals/runners/ranker_floor.py        # 9 hard gates
  python3 python/evals/runners/multi_repo_eval.py     # 3 unseen OSS repos

Happy to answer on: the ranker (8 signals + plural/singular stems +
df-discriminativity + file aggregation; full ablation in autocontext-ablation.md),
why no embeddings (cold-start + cost + binary deps), and why this belongs inside
`claude` itself, not as a third-party plugin.
```

Once posted, **watch the rank for 30 minutes.** If it hits the front page, proceed. If not, **do not flag, do not repost** — go on with your day; HN auto-detects retries.

---

## 3 · X / Twitter thread  ·  T+5 min

**Click:** https://x.com/compose/post

Post these 5 tweets in order (use "+ Add to thread" between each):

**1/5**

```
I built a 400-line Python hook so Claude Code's first turn opens the right
file instead of grepping for it.

Static-analysis repo graph injected pre-prompt. No embeddings, no server,
no model call, ~50ms.

github.com/sravan27/context-os
```

**2/5**

```
Claude Code's first turn burns ~35k tokens on Glob → Grep → Read → Read → Read.
The model has no map of the repo, so it grep-walks one.

The hook pre-builds that map (symbols + imports + git-hot files) and injects
ranked file:line candidates before turn 1.
```

**3/5**

```
What's CI-gated and version-independent:
• MRR 0.984 synthetic (Py/TS/Rust)
• Beats BM25 in every language across 3 unseen OSS repos
  (axios/ripgrep/requests, weighted MRR 0.545 vs 0.461)
• 9 hard regression floors red-line the PR if quality drifts
```

**4/5**

```
The number people over-read: −40.9% tokens on a claude --print A/B (N=36, p=5e-7).

Honest: cold-cache one-shots. In a warm session, prompt caching makes
re-sent context cheap — so dollar delta is smaller. The durable wins are
fewer first-turn tool calls and hitting compaction/limits later.
```

**5/5**

```
Don't trust my A/B — replay it on YOUR own Claude Code history:

  python3 python/evals/runners/replay_history.py

$0, no API key, measured from your real transcripts.

MIT, stdlib Python only.
github.com/sravan27/context-os
```

---

## 4 · r/ClaudeAI  ·  T+10 min

**Click:** https://www.reddit.com/r/ClaudeAI/submit?type=TEXT

**Title**:

```
A 400-line Python hook so Claude Code opens the right file instead of grepping for it (MIT, no embeddings)
```

**Body**:

```
I run Claude Code daily and kept hitting the 5-hour window mid-refactor.
The pattern was always the same: first turn burns ~35k tokens on
Glob → Grep → Read → Read → Read, exploring blind.

So I built a UserPromptSubmit hook that pre-builds a static graph of the
repo (symbols + line ranges + imports + git-hot files) and injects ranked
file:line candidates before Claude sees the prompt. Plus smart_read, a
PreToolUse hook that intercepts whole-file Reads of big indexed files and
returns the file's outline so Claude reads only the slice it needs.

Stdlib Python, ~400 lines, MIT. No embeddings, no server, ~50ms hook latency.

**What's measured and CI-gated** (this is the bankable part):
- MRR 0.984 synthetic across Py/TS/Rust fixtures
- 0.756 on the repo itself
- Beats BM25 in every language across 3 unseen OSS repos
  (axios/ripgrep/requests, weighted MRR 0.545 vs 0.461)
- 9 regression-floor gates so retrieval quality can't silently drift

**The number to read precisely:**
A `claude --print` A/B showed −40.9% aggregate tokens (N=36, p=5e-7,
Cohen's d=1.84). Honest caveat: those are cold-cache one-shots. In a warm
interactive session, prompt caching makes re-sent context cheap, so your
*dollar* savings are smaller than 40.9%. The reliable wins are fewer
first-turn tool calls and hitting context limits / compaction later.

**Don't trust my A/B — replay it on YOUR history, $0, no API key:**
`python3 python/evals/runners/replay_history.py`

Backtests the whole stack against your existing `~/.claude/projects/**/*.jsonl`
transcripts; load sizes measured directly from real tool_result content.

Install:
`curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash`

Repo: https://github.com/sravan27/context-os
```

---

## 5 · LinkedIn  ·  T+15 min

**Click:** https://www.linkedin.com/feed/?shareActive=true

**Post**:

```
Open-sourced a small Claude Code optimization that I think is worth a look.

The problem: Claude Code's first turn burns ~35k tokens exploring the repo
blind — Glob, Grep, Read, Read, Read — before doing anything useful. The
model has no map going into turn 1, so it grep-walks one.

The fix: a 400-line stdlib Python hook that pre-builds a static-analysis
repo graph (symbols + imports + git-hot files) and injects ranked file:line
candidates BEFORE Claude sees the prompt. No embeddings, no server, no
model call, ~50ms latency.

What's CI-gated and reproducible:
• MRR 0.984 on synthetic Py/TS/Rust fixtures
• Beats BM25 across 3 unseen OSS repos (axios/ripgrep/requests)
• 9 regression-floor gates red-line the PR if retrieval quality drifts

A `claude --print` A/B showed −40.9% tokens (N=36, p=5e-7), but I want to
flag the honest caveat upfront: cold-cache one-shots. Warm interactive
sessions reuse cache, so dollar savings are smaller. The durable wins are
fewer first-turn tool calls and hitting context limits later.

Anyone can validate it on their own Claude Code history (no API key required)
via replay_history.py — backtests against your actual ~/.claude/projects
transcripts.

MIT licensed. Reproducible in one git clone.

github.com/sravan27/context-os
```

---

## 6 · Anthropic Discord  ·  T+20 min  (after HN momentum is visible)

**Click:** https://anthropic.com/discord — then navigate to **`#show-and-tell`** (or `#projects`, whichever is the community-projects channel)

**Replace `XXXX` with your HN post's item ID**, then paste:

```
Open-sourced a small Claude Code thing this morning: a 400-line stdlib
Python UserPromptSubmit hook that pre-builds a static repo graph (symbols,
imports, git-hot files) and injects ranked file:line candidates before
Claude's first turn — so the first move is a targeted Read instead of
Glob → Grep → Read → Read → Read.

Retrieval quality CI-gated: MRR 0.984 synthetic, beats BM25 across 3
unseen OSS repos (axios/ripgrep/requests).

A claude --print A/B showed −40.9% tokens (N=36, p=5e-7) — cold-cache
one-shots; in warm sessions the dollar delta is smaller due to caching.
Durable wins are fewer first-turn tool calls + later compaction.

MIT, no embeddings, no server. github.com/sravan27/context-os
HN: news.ycombinator.com/item?id=XXXX

Happy to take feedback — especially on the methodology.
```

---

## 7 · Anthropic Plugin Directory  ·  T+25 min  (the highest-prize channel)

**Click:** https://clau.de/plugin-directory-submission

Fill out:
- **Plugin name**: `context-os`
- **Repo URL**: `https://github.com/sravan27/context-os`
- **Description** (paste):

```
A static-analysis repo graph injected pre-prompt so Claude Code's first turn
opens the right file instead of grepping for it. Plus PreToolUse hooks
(smart_read, smart_bash) that intercept whole-file dumps and return the
file's structural outline so Claude reads only the needed slice. Plus a
/savings dashboard that measures both sources causally from the transcript.

Stdlib Python only. No embeddings, no server, no model call. ~50ms hook
latency, fail-open on every error, ~100 CI-gated test assertions.

Retrieval CI-gated (MRR 0.984 synthetic; beats BM25 across 3 unseen OSS
repos). −40.9% tokens on a cold-cache claude --print A/B (N=36, p=5e-7;
warm-session dollar delta smaller due to caching).
```

Anything else they ask for (license, contact email): MIT; your email.

---

## After it's live

- Reply to every HN comment that's still open. Be technical, not promotional. Treat skeptics' questions as gifts — they're free FAQ entries.
- If the post hits ≥150 points, DM Boris Cherny (`@bcherny` on X) — template in `docs/distribution/DIRECT-OUTREACH.md` template A.
- If no Anthropic engagement by D+7, write a "what we learned from the launch" follow-up on dev.to. Ends the cycle cleanly.

## Don'ts (these have killed launches before)

- ❌ Post on a weekend.
- ❌ Post during major Anthropic news (model release, pricing change, outage).
- ❌ Reply to skeptics with marketing copy. Reply with code paths + CI commands.
- ❌ Use the word "revolutionary," "must-have," or "save your bill" — every honest reader's BS detector trips.
- ❌ Send the HN link to Anthropic before traction is established (looks like spam).
- ❌ Auto-DM. Every DM should be hand-written.
- ❌ Crosspost to multiple subreddits in the same hour — Reddit shadow-bans for this.

## Success metrics (honest)

- **Pass** = HN ≥100 points, any reply from any Anthropic employee, ≥3 "actually trying it" comments.
- **Strong pass** = HN ≥300 points, mentioned in any developer newsletter (Pragmatic Engineer, Lenny's, ImportAI, etc.), Anthropic engineer commenting on issue #53224.
- **Win** = Anthropic engineer asks for a call or commits to evaluation.

If you don't hit "pass" in 7 days: **don't relaunch the same post** — HN auto-flags duplicates. Wait 4 weeks, ship a v2.11 with one new piece of evidence (e.g., real customer testimonial from someone other than you), and relaunch with that as the headline.

---

That's the whole thing. The only thing left is you, a Tuesday morning, and 30 minutes.
