# Launch checklist

The order of operations matters more than the content of any single post. This is the playbook.

## Pre-launch (do today, Saturday 2026-04-25)

- [x] v2.8.0 tagged + GitHub release published
- [x] README.md leads with v2.8 numbers
- [x] Repo description + topics updated on GitHub
- [ ] Record asciinema demo following `DEMO-SCRIPT.md` — 60-90 seconds, lives in README, HN, X
- [ ] Embed asciinema in README under the headline (one-line markdown)
- [ ] Skim every doc once for typos and v2.7→v2.8 number drift
- [ ] Pin the v2.8.0 release on GitHub repo profile
- [ ] (Optional) Add a 1280×640 social preview PNG via GitHub repo settings — shows on Twitter unfurls

## Launch day — Tuesday 2026-04-28

### T-30 (7:30am ET) — final prep
- [ ] Reread the Show HN draft fresh — anything that reads stale?
- [ ] Confirm `python3 python/evals/runners/ranker_floor.py` and `multi_repo_eval.py` both pass cold (clear caches first)
- [ ] Open browser tabs: HN submit page, X compose, Anthropic Discord, LinkedIn

### T = 8:00am ET — Show HN
- [ ] Submit using title from `SHOW-HN.md`
- [ ] Within 60s: post the first-comment seed (also from `SHOW-HN.md`)
- [ ] Watch the rank for 30 minutes. If on /front in 30 min, proceed. If not, do nothing — no flagging, no reposting.

### T + 30min — early signal boosts (only if HN is on /front)
- [ ] Tweet thread (paste from `TWEETS.md`, all 10 in one go)
- [ ] LinkedIn post (paste from `LINKEDIN.md`, do NOT boost)

### T + 2h — broaden, only if HN is sticking
- [ ] Anthropic Discord post (`DIRECT-OUTREACH.md` template F)
- [ ] DM Alex Albert with HN link (`DIRECT-OUTREACH.md` template C)

### T + 4h — Reddit (only if HN is climbing)
- [ ] r/ClaudeAI (template from `REDDIT.md`)

### T + 24h — sustained engagement
- [ ] Reply to every HN comment that's still open. Be technical, not promotional.
- [ ] Reply to every X reply. Quote-tweet anyone tagging Claude Code engineers.
- [ ] r/programming post (template from `REDDIT.md`)

### T + 24-48h — direct outreach (only if HN ≥150 pts or ≥30 X likes)
- [ ] DM Boris Cherny (`DIRECT-OUTREACH.md` template A) — single highest-leverage human
- [ ] File `feature_request` on anthropics/claude-code (`GH-FEATURE-REQUEST.md`) — link the HN post
- [ ] DM Cat Wu (`DIRECT-OUTREACH.md` template B)

### T + 48h-7d — close the loop
- [ ] r/LocalLLaMA post (`REDDIT.md`)
- [ ] DM Thariq if not already done
- [ ] Watch for any Anthropic engineer engaging — reply within 30 min, technically, no fluff
- [ ] If no Anthropic engagement by D+7, write a follow-up "what we learned from the launch" post on dev.to. Ends the cycle gracefully.

## Pause / abort triggers

If ANY of these happen, stop and re-plan:
- HN flag-killed within 1 hour (rare; means the title was off)
- A bug surfaces in the code that invalidates the headline number — pull the post immediately, fix, re-tag, relaunch a week later
- Anthropic legal / DMCA / cease-and-desist — extremely unlikely (MIT license + no Anthropic IP) but stop and consult a lawyer if it happens

## Don'ts

- Don't post on Saturday/Sunday.
- Don't post during major Anthropic news (model release, pricing change, outage).
- Don't post within 24h of a competitor's launch — you'll split attention.
- Don't email anyone at Anthropic before HN traction is established.
- Don't reply to skeptics with marketing language. Reply with code paths and CI commands.
- Don't talk about acquisition / acquihire publicly — those words belong only in PITCH.md.
- Don't auto-DM anyone. Every DM is bespoke.

## Success metrics

- Pass: HN ≥100 pts, ≥10 X engagements from devtools community, any reply from an Anthropic employee.
- Strong pass: HN ≥300 pts, mentioned in any developer newsletter (Lenny's, Pragmatic Engineer, ImportAI), Anthropic engineer commenting on the issue or DM.
- Win: Anthropic engineer asks for a call or commits to evaluation.
- Acquihire / port-upstream: that's downstream of "win." Not the launch goal.

## Reset rules

If the launch doesn't hit "pass" in 7 days:
- Don't relaunch the same post. HN auto-flags duplicates.
- Wait 4 weeks, ship a v2.9 with one new piece of evidence (e.g. semantic reranker, 100k-file scaling, real customer testimonial), and relaunch with that as the headline.
- The repo is the long-term asset. Stars accrue from search and word-of-mouth too. One launch is not the whole game.
