# Direct outreach templates

## Targets, in order of leverage

| # | Person | Role | Channel | Why |
|---|---|---|---|---|
| 1 | Boris Cherny (`@bcherny`) | Head of Claude Code, Anthropic | X DM, GitHub, email if findable | Single highest-leverage human for this pitch. Top contributor to anthropics/claude-code. |
| 2 | Cat Wu (`@catherinewu`) | Head of Product Claude Code, Anthropic | X DM, LinkedIn | Owns roadmap. The ROI math in PITCH.md is for her. |
| 3 | Alex Albert (`@alexalbert__`) | DevRel, Anthropic | X DM, LinkedIn | Ecosystem amplification. Quotes community wins. |
| 4 | Thariq Shihipar (`@trq212`) | Builds Claude Code, Anthropic | X DM | Will read the code, not the pitch. Treat technically. |
| 5 | Anthropic recruiting / careers | — | careers@anthropic.com | If Anthropic-internal contact fails. |

## Channel rules

- **X DM:** must follow first; many engineers gate DMs.
- **Email:** only if listed publicly. Don't guess company emails.
- **GitHub:** comment on closed issues / open issue is fine; do NOT @-mention in unrelated PRs.
- **LinkedIn:** only if you have a 1st or 2nd-degree connection. Cold InMails are dead-letter.
- **Discord:** sanctioned channel is `discord.com/invite/6PPFFzqPDZ`. Use `#show-and-tell` (or wherever community projects post) AFTER the HN post is up.

## Templates

### A. To Boris Cherny (X DM)

Send only after Show HN is on /front. Mention the HN post.

```
Hi Boris — landed on HN today: news.ycombinator.com/item?id=XXXX

400-line Python hook for Claude Code, −40.9% tokens on live A/B (36 real
calls, p=5e-7, Cohen's d=1.84). Cross-repo evidence on 3 unseen OSS repos
in v2.8.0 today: weighted MRR 0.545 vs 0.461 best lexical baseline.

Pitch + proposal for upstream port in repo. MIT, no strings.
github.com/sravan27/context-os/blob/main/docs/PITCH.md

Worst case I get a code review. Best case `claude context build` ships in
a future minor. Either's fine.
```

### B. To Cat Wu (LinkedIn or X DM)

```
Hi Cat — open-sourced a context-optimization primitive for Claude Code.
Live A/B receipts: −40.9% tokens, p = 5e-7. Cross-repo eval shipped today
in v2.8.0.

The pitch doc has the integration paths and a back-of-envelope on ROI
(low nine figures gross at 1M users, conservative). Written for the
product side specifically — would love your read.

github.com/sravan27/context-os/blob/main/docs/PITCH.md

MIT-licensed. Happy to do a 20-min walkthrough or PR upstream.
```

### C. To Alex Albert (X DM)

```
Hi Alex — built a Claude Code hook that's getting traction on HN today
(news.ycombinator.com/item?id=XXXX). −40.9% tokens on live A/B, MIT.

If it would be useful as a community example or to feature in a walkthrough,
take whatever you need. No attribution required, but happy to record a
demo if useful.

github.com/sravan27/context-os
```

### D. To Thariq Shihipar (X DM, technical)

```
Hi Thariq — hook implementation for Claude Code that I think is worth a
glance. UserPromptSubmit + a static-analysis graph (symbols + imports +
git-hot files), 400 lines stdlib Python.

Ranker is 8 signals + 4 v2.8 additions (plural/singular stems,
df-discriminative path scoring, file-level aggregation, case-fold dedupe).
Ablation in autocontext-ablation.md if you want the leave-one-out numbers.

The interesting question for me: what's the right place for prefix-bucketing
the path-substring scan? Currently O(files × tokens), and at 100k files
extrapolation puts it over the 1s SLA.

github.com/sravan27/context-os/blob/main/hooks/python/auto_context.py
```

### E. Generic warm intro (for friends who can vouch)

If anyone in your network knows any of the above, ask them to forward this.
Lightweight, no commitment.

```
Subject: quick intro request — Claude Code optimization

Hi [name] — I built an open-source thing for Claude Code (Anthropic's CLI
agent) that cuts token usage 40.9% on live A/B. Numbers are reproducible
and CI-gated.

I'd love a warm intro to anyone you know on the Claude Code team —
ideally Boris Cherny, Cat Wu, or Alex Albert. The pitch is in the repo:
github.com/sravan27/context-os/blob/main/docs/PITCH.md

Happy to send you the 1-paragraph version if it's easier to forward.
No pressure if you don't have the connection.
```

### F. Anthropic Discord — `#show-and-tell` or equivalent

Post AFTER HN momentum:

```
Open-sourced a Claude Code optimization today — UserPromptSubmit hook
that pre-builds a static-analysis graph and injects ranked file:line
candidates at turn 1.

Live A/B on 36 real claude --print calls: −40.9% tokens, p = 5e-7,
Cohen's d = 1.84.

Cross-repo eval (axios JS / ripgrep Rust / requests Py): weighted MRR
0.545 vs 0.461 best lexical baseline.

MIT, stdlib Python, no embeddings. 400 lines.

github.com/sravan27/context-os
HN: news.ycombinator.com/item?id=XXXX

Happy to take feedback — especially on the cross-repo methodology.
```

## Anti-patterns

- ❌ "Acquihire" / "acquisition" / "would Anthropic be interested" anywhere in writing.
  The pitch claims belong in PITCH.md, not in DMs. DMs are about the work, not the deal.
- ❌ Cold-emailing executives without a warm intro or a public proof point.
  HN traction IS the proof point. Wait for it.
- ❌ Following up more than once. If they don't respond in 7 days, move on.
- ❌ Multi-channel pinging the same person within 24h. Pick one channel per person.
- ❌ "I'd love to chat" / "do you have 30 minutes" — replace with a specific ask or specific value-add.

## Schedule

Day of HN landing on /front (call it D0):
- D0 + 1h: post in Anthropic Discord
- D0 + 2h: tweet thread, then DM Alex Albert (low-stakes)
- D0 + 24h: DM Boris Cherny (only if HN is still on /front or hit ≥150 pts)
- D0 + 48h: DM Cat Wu and Thariq, file the GitHub feature request
- D0 + 7 days: follow up on any unanswered DMs once, then drop it
