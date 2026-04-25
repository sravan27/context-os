# Reddit posts

Three subreddits, ordered by likely traction. Post each at least 4 hours apart, never same hour, to avoid auto-flagging as spam.

---

## r/ClaudeAI (~80k members) — primary target

**Title:**
> I cut Claude Code token usage by 40.9% with a 400-line Python hook (live A/B, p=5e-7)

**Body:**
```
I run Claude Code daily and kept hitting the 5-hour rate window mid-refactor.
Looked at where tokens were going: Claude's first turn was burning ~35k tokens
on Glob → Grep → Read → Read → Read, exploring blind.

Built a UserPromptSubmit hook that pre-builds a static-analysis graph of the
repo (symbols + imports + git-hot files) and injects ranked file:line
candidates into the prompt before Claude sees it. Stdlib Python, ~400 lines.
No embeddings, no server, no model call.

**Live A/B on 36 real `claude --print` calls** (6 prompts × 3 runs × 2 arms):
- −40.9% aggregate tokens [bootstrap CI 32.7%, 48.9%]
- 6/6 prompt-level wins
- paired t-test p = 5.06e-07
- Cohen's d = 1.84 (large effect)
- wall-clock −35.3% (11.80s → 7.64s mean)

**Cross-repo evidence** (v2.8.0, just shipped):
- 36 hand-labeled prompts across 3 OSS repos NOT in my fixtures
- axios/axios (JS): MRR 0.382 vs best baseline 0.252 (+0.130)
- BurntSushi/ripgrep (Rust): MRR 0.503 vs 0.459 (+0.044)
- psf/requests (Py): MRR 0.750 vs bm25-symbols 0.875 (lexical-ceiling regime — prompts use exact class names)
- Weighted aggregate: 0.545 vs 0.461. +18.2%.

**Quality gates** — 9 CI-enforced floors so the ranker can't silently regress.
18/18 adversarial robustness cases pass.

Install:
`curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash`

Repo: https://github.com/sravan27/context-os
Pitch doc: https://github.com/sravan27/context-os/blob/main/docs/PITCH.md

Happy to answer questions on the ranker, why I went with no embeddings, or
how this compares to MCP-based vector approaches.
```

---

## r/programming (~6M members) — broader audience, harder to land

**Title:**
> Static-analysis RAG for Claude Code: a 400-line hook that beats BM25 on 36 prompts × 3 OSS repos

**Body:**
```
A small experiment that turned into a real result.

I noticed Claude Code (Anthropic's CLI agent) burns most of its first-turn
tokens on blind repo exploration — Glob, Grep, Read, Read, Read — before
doing anything useful. The model has no map of the codebase going into
turn 1.

So I built one.

A `UserPromptSubmit` hook (400 lines, stdlib Python) parses the prompt,
queries a pre-built graph of symbols + imports + git-hot files, and prepends
a ranked candidate list of `file:line · symbol · imports`. Claude starts
turn 1 with structure already in hand.

The interesting bits:

1. **It works on live Claude.** A/B on 36 real `claude --print` calls:
   −40.9% aggregate tokens, p = 5e-7, Cohen's d = 1.84, 6/6 prompt-level
   wins, wall-clock −35.3%.

2. **It generalizes across languages.** Hand-labeled 36 descriptive prompts
   across 3 unseen OSS repos (axios JS, ripgrep Rust, requests Python) and
   ran every prompt against auto_context + 5 lexical baselines.
   Weighted MRR 0.545 vs best baseline 0.461.

3. **Honest scope note.** On psf/requests, prompts use exact class names
   (PreparedRequest, HTTPError) — the lexical-retrieval ceiling regime where
   bm25-symbols caps. We lose that one. Surfaced in the report.

4. **Why no embeddings.** Cold-start, cost, binary deps. On top-1 precision
   (the metric that matters because Claude only acts on top-1), well-tuned
   BM25 + 8 path/symbol heuristics already gets MRR 0.984 on synthetic.

5. **CI-enforced regression floor.** 9 hard gates that red-line a PR if
   quality drifts. 18/18 adversarial robustness cases.

Repo: https://github.com/sravan27/context-os
Methodology / reviewer walkthrough: docs/REVIEW-CHECKLIST.md

Reproduce in 5 minutes:
```
git clone https://github.com/sravan27/context-os && cd context-os
python3 python/evals/runners/ranker_floor.py
python3 python/evals/runners/multi_repo_eval.py
```

Open to feedback on the methodology — especially from anyone who's
benchmarked retrieval rankers more rigorously than I have.
```

---

## r/LocalLLaMA (~370k members) — the audience that cares about local-first

**Title:**
> Hook-based RAG for coding agents (no embeddings, no server, MIT) — measured 40.9% token cut on live Claude

**Body:**
```
This isn't local-LLM but I think it's relevant: a stdlib Python hook that
gives Claude Code static-analysis RAG without any of the usual MCP / vector
DB overhead.

Why post here: the architecture is the kind of thing this sub appreciates —
local-only, zero deps, auditable in 100 lines. No phone-home, no server, no
embedding model required. The same shape would port cleanly to any agent
that exposes a pre-prompt hook.

What it does:
- Pre-build a graph of the repo (symbols + imports + git-hot files) at
  install time.
- On every UserPromptSubmit, parse the prompt, query the graph, prepend
  ranked file:line candidates.
- Hook latency: ~50ms typical, p99 118ms at 10k files.

Numbers (all reproducible):
- Live A/B on real Claude calls: −40.9% aggregate tokens, p = 5e-7
- Synthetic MRR 0.984 across Py/TS/Rust fixtures
- Cross-repo MRR 0.545 vs 0.461 best baseline across 36 prompts × 3 OSS repos

Repo: https://github.com/sravan27/context-os

The ranker is the interesting part:
hooks/python/auto_context.py:1-400

8 signals, ablation in autocontext-ablation.md. df-discriminative path
scoring + plural/singular stems + file-level aggregation are the v2.8
additions that pushed it past BM25-symbols on cross-repo aggregate.

Curious if anyone here has tried similar architectures for local agents
(Aider, OpenInterpreter). The pre-prompt-hook surface seems underexplored.
```

---

## Crosspost timing

Saturday 2026-04-25 (today): too quiet for any meaningful traction. Wait.

Tuesday 2026-04-28:
- 8:00am ET — Show HN
- 12:00pm ET — r/ClaudeAI (after HN momentum is established)
- 4:00pm ET — r/programming
- Wednesday 9:00am ET — r/LocalLLaMA

Wait at least 30 min between posts. Reddit has shadow-bans for "too many subs in one hour."

## Don't

- Don't crosspost identical body to multiple subs. Re-frame for each audience.
- Don't reply to skeptics with marketing copy. Reply with code paths and CI commands.
- Don't link to twitter/x screenshots in r/programming — they get downvoted reflexively.
