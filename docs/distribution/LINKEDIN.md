# LinkedIn post

LinkedIn rewards: first-person, specific numbers, vulnerability, no buzzwords. Cap ~1300 chars for the visible block (rest is "see more").

## Recommended (post once, do not boost)

```
I cut my Claude Code token usage by 40.9% with a 400-line Python hook.

The problem: Claude Code's first turn burns ~35,000 tokens on blind repo
exploration — Glob, Grep, Read, Read, Read — before doing anything useful.
The model has no map of the codebase going into turn one.

The fix: a UserPromptSubmit hook that pre-builds a static-analysis graph
of the repo (symbols + imports + git-hot files) and injects ranked
file:line candidates into the prompt before Claude sees it. Stdlib Python.
No embeddings. No server. No model call.

The receipts:
• Live A/B on 36 real claude --print calls: −40.9% tokens, p = 5e-7
• Cross-repo evidence: 36 prompts × 3 unseen OSS repos
  weighted MRR 0.545 vs 0.461 best baseline (+18.2%)
• 9 CI-enforced regression gates so quality cannot drift silently
• 18/18 adversarial robustness cases

Open-sourced under MIT. Pitch doc inside the repo for the Anthropic
Claude Code team, because this belongs inside `claude` itself, not as
a third-party plugin.

Built this because I kept hitting the 5-hour rate window mid-refactor
and got tired of paying for blind exploration.

github.com/sravan27/context-os

If you run Claude Code at scale or own a developer-tools team, would
love your thoughts on whether the methodology survives a serious review.

#ClaudeCode #DeveloperTools #LLM #OpenSource #Anthropic
```

## Short variant for company page / employee shares

```
Open-sourced a small thing today: a 400-line Python hook that cuts
Claude Code token usage by 40.9% on live A/B (p = 5e-7).

It works by giving Claude a pre-built map of the codebase — symbols,
imports, git-hot files — before turn one, so the agent's first move is
a targeted Read instead of five exploratory Greps.

MIT-licensed, stdlib only, ~50ms hook latency.

github.com/sravan27/context-os
```

## DMs to specific people

If you have second-degree connections to these folks, a single targeted DM
beats a thousand cold tweets.

### Boris Cherny (@bcherny on X, Anthropic, Head of Claude Code)

```
Hi Boris — built a small thing for Claude Code that I think belongs
upstream. UserPromptSubmit hook, 400 lines of stdlib Python, no
embeddings. Live A/B on 36 real claude calls: −40.9% tokens, p = 5e-7,
Cohen's d = 1.84.

Cross-repo evidence (36 hand-labeled prompts × 3 unseen OSS repos)
shipped today in v2.8.0. Weighted MRR 0.545 vs 0.461 best lexical
baseline.

Pitch doc + reviewer walkthrough in the repo, ~25 minutes total.
github.com/sravan27/context-os/blob/main/docs/PITCH.md

No equity ask, no partnership. MIT license, happy to PR or donate.
Worst case I get a code review that makes the next version sharper.
```

### Cat Wu (@catherinewu, Head of Product Claude Code)

```
Hi Cat — open-sourced a context-optimization hook for Claude Code that
saves ~40% of tokens on live A/B (p = 5e-7). The interesting part for
product is that the savings come without a model swap or pricing
change — it's a pre-prompt static-analysis graph injection.

Pitch doc has the integration paths + back-of-envelope ROI math
(low-nine-figures gross at 1M users, conservative).

github.com/sravan27/context-os/blob/main/docs/PITCH.md

Happy to do a 20-minute walkthrough or to PR upstream. MIT license.
```

### Alex Albert (@alexalbert__, DevRel)

```
Hi Alex — for the developer-relations side: I open-sourced a thing
called context-os that cuts Claude Code token usage by ~40% with a
400-line Python hook. Live A/B receipts in the repo.

Posted Show HN on [date] — link if it lands well: [HN URL].

If it would be useful as a community example or to feature in a
walkthrough, take whatever you need under the MIT license. No
attribution required, but happy to record a demo if useful.

github.com/sravan27/context-os
```

## Don't

- Don't post to LinkedIn before the HN post is up — LinkedIn audiences will see the link, click, and bounce off a low-traffic page.
- Don't use the word "revolutionary" anywhere. LinkedIn moderators dampen reach for buzzword posts.
- Don't post the technical-deep version as a single LinkedIn post. Long-form goes on dev.to or Medium and the LinkedIn post links to it.
