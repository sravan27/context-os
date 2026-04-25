# X / Twitter thread

## Thread (10 tweets, post in order — copy-paste ready)

### 1/10 — hook

```
I cut Claude Code token usage by 40.9% with a 400-line Python hook.

Live A/B on 36 real `claude --print` calls:
• −40.9% aggregate tokens [bootstrap CI 32.7%, 48.9%]
• 6/6 prompt-level wins
• paired t-test p = 5.06e-07
• Cohen's d = 1.84

Repo: github.com/sravan27/context-os 🧵
```

### 2/10 — the problem

```
Claude Code's first turn burns ~35k tokens on Glob → Grep → Read → Read → Read,
exploring blind before doing anything useful.

The model has no map of the repo going into turn 1. So it grep-walks one.

That's the entire problem.
```

### 3/10 — the fix

```
A UserPromptSubmit hook pre-builds a static-analysis graph of the repo
(symbols + imports + git-hot files) and injects ranked file:line candidates
into the prompt before Claude sees it.

400 lines of stdlib Python. No embeddings. No server. No model call.
~50ms latency.
```

### 4/10 — what Claude actually sees

```
Before:
  user: "where is the gitignore parser"
  Claude: Glob → Grep → Read → Read → Read → "found it in walk.rs!"

After:
  <context-os:autocontext>
  crates/ignore/src/gitignore.rs:42 · Gitignore (struct)
  crates/ignore/src/gitignore.rs:118 · matched (fn) · imports: …
  </context-os:autocontext>
  Claude: Read crates/ignore/src/gitignore.rs → done.
```

### 5/10 — cross-repo evidence (v2.8)

```
Hand-labeled 36 descriptive prompts across 3 OSS repos NOT in my fixtures:
• axios/axios (JS, 214 files): MRR 0.382 vs best baseline 0.252
• BurntSushi/ripgrep (Rust, 100 files): MRR 0.503 vs 0.459
• psf/requests (Py, 36 files): MRR 0.750 vs bm25-symbols 0.875 ← honest loss

Weighted aggregate: 0.545 vs 0.461. +18.2%.
```

### 6/10 — the honest loss

```
On psf/requests, bm25-symbols beats us. Why?

Prompts in that set use exact class names — `PreparedRequest`, `HTTPError`,
`CaseInsensitiveDict`. That's the lexical-retrieval ceiling regime where
plain BM25 over symbols caps.

We win the cross-repo aggregate, in every language. Not every repo.
Surfaced in the report so reviewers don't have to find it.
```

### 7/10 — quality gates

```
9 CI-enforced regression gates (`ranker_floor.py`):
• synthetic MRR ≥ 0.920 (current: 0.984)
• dogfood MRR ≥ 0.720 (current: 0.756)
• MRR lift over bm25-symbols ≥ 0.060 (current: 0.109)

Every PR runs them. Quality cannot drift silently.

18/18 adversarial robustness cases pass (unicode, regex bombs, path injection).
```

### 8/10 — back-of-envelope economics

```
Conservative assumptions: 1M Claude Code users × 400 prompts/month
× 50k tokens/prompt × $6/MT blended.

Without the hook: $120/user/month.
With the hook: $71/user/month.
Savings: $49/user/month → ~$588M/year gross.

Even discounted 90% you're in nine figures of margin recaptured/year.
```

### 9/10 — why I'm giving it away

```
This belongs inside `claude` itself, not as a third-party plugin.

Discovery is the problem — users who would benefit most (new to Claude Code)
will never find a GitHub plugin.

MIT license. Pitch doc to the Claude Code team in the repo.
Happy to PR or donate the code.
```

### 10/10 — install

```
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash

Reversible. Idempotent. python3 only.
Pitch: github.com/sravan27/context-os/blob/main/docs/PITCH.md

If you hit the 5-hour rate window mid-refactor as much as I do, give it a try.
```

## Solo single-tweet variant (for replies / low-effort signal boost)

```
Cut Claude Code token usage by 40.9% with a 400-line Python hook.

Live A/B on 36 real claude calls. p=5e-7. No embeddings, no server.

github.com/sravan27/context-os
```

## Quote-tweet templates (use to reply to anyone tweeting about Claude Code costs)

When someone tweets about hitting rate limits / token bills:
```
Built a thing for exactly this. 400-line Python hook, −40.9% on live A/B.
github.com/sravan27/context-os
```

When someone tweets about Claude Code internals / hooks:
```
Worked on the hooks API for a few months. UserPromptSubmit + a static-analysis
graph cuts the first-turn exploration ~entirely. Live A/B p=5e-7 if you want
the receipts. github.com/sravan27/context-os
```

## People to @-mention (in order of leverage)

Only mention if the post is performing well (>50 likes or >5k impressions).
Mentioning early looks like spam.

1. @bcherny — Boris Cherny, Head of Claude Code at Anthropic. 261k followers. Highest leverage.
2. @catherinewu — Cat Wu, Head of Product Claude Code.
3. @alexalbert__ — Alex Albert, DevRel at Anthropic.
4. @trq212 — Thariq Shihipar, builds Claude Code.
5. @AnthropicAI — official corporate handle. They sometimes RT community work.

Suggested outro tweet to add the mentions, after thread is performing:
```
@bcherny @catherinewu @alexalbert__ — pitch doc in the repo for the team.
Happy to walk through the methodology or PR upstream.
```

## Timing

- Thread: post Tuesday 9:00am ET (peak engagement) right after Show HN goes live.
- Solo tweet: any time.
- Quote tweets: opportunistic, watch search.twitter.com/?q=%22claude+code%22+token

## Don't

- Don't tweet "we're acquihire-ready" or any acquisition framing publicly. The pitch doc is for Anthropic's eyes, not the timeline.
- Don't reply to skeptics combatively. "Numbers are reproducible — `python3 ranker_floor.py` if you want the proof" is the only acceptable reply pattern.
- Don't tweet during an outage or during major Anthropic news. Wait 48h.
