# Launch: one-click submit links

> **Revised 2026-05-13.** HN is rate-limiting new submissions. Launch anchors on **GitHub + Reddit**. The kit below is the operational play. Click each link, paste body where indicated, submit. No conditional gates between channels.

## T+0  ·  awesome-claude-code  (the highest-leverage shot)

`hesreallyhim/awesome-claude-code` has 43.6k stars and is the de-facto registry for Claude Code resources. Getting listed there is worth more than a HN front-page slot for our audience.

**One-click prefilled issue** (the maintainer requires submissions via the GitHub UI, not `gh` CLI — the link below prefills every field, you just click *Submit new issue*):

[Submit context-os to awesome-claude-code →](https://github.com/hesreallyhim/awesome-claude-code/issues/new?template=recommend-resource.yml&title=%5BResource%5D%3A+context-os&display_name=context-os&category=Hooks&primary_link=https%3A%2F%2Fgithub.com%2Fsravan27%2Fcontext-os&author_name=sravan27&author_link=https%3A%2F%2Fgithub.com%2Fsravan27&license=MIT&description=A+UserPromptSubmit+hook+that+pre-builds+a+static-analysis+graph+of+the+repo+%28symbols%2C+imports%2C+git-hot+files%29+and+injects+ranked+file%3Aline+candidates+into+the+prompt+before+Claude+sees+it.+~400+lines+of+stdlib+Python%2C+no+embeddings%2C+no+server%2C+no+model+call.+On+a+live+A%2FB+over+36+real+%60claude+--print%60+calls%2C+aggregate+tokens+dropped+40.9%25+%28paired+t-test+p%3D5.06e-07%2C+Cohen%27s+d%3D1.84%2C+6%2F6+prompt-level+wins%29.+Ships+alongside+.claudeignore%2C+settings.json%2C+eleven+slash+commands%2C+an+output+style%2C+an+explorer+subagent%2C+and+five+additional+stdlib-Python+hooks+%28dedup-guard%2C+loop-guard%2C+file-size-guard%2C+prewarm%2C+session-profile%29.&validate_claims=Run+%60python3+python%2Fevals%2Frunners%2Franker_floor.py%60+%289+CI-enforced+regression+gates%2C+~45s%29+and+%60python3+python%2Fevals%2Frunners%2Fmulti_repo_eval.py%60+%2836+hand-labeled+prompts+%C3%97+3+unseen+OSS+repos%3A+axios%2C+ripgrep%2C+requests%3B+~2+min%29.+Both+reproduce+the+headline+retrieval+numbers+without+an+Anthropic+API+key.+The+live+A%2FB+requires+a+key%2C+but+the+raw+usage+JSON+from+all+36+%60claude+--print%60+calls+is+committed+under+%60python%2Fevals%2Freports%2Flive-session-bench-raw.json%60+so+the+ratio+math+is+auditable.&validate_claim_part_2=Install+on+any+repo+with+%3E20+source+files%3A+%60curl+-fsSL+https%3A%2F%2Fraw.githubusercontent.com%2Fsravan27%2Fcontext-os%2Fmain%2Fsetup.sh+%7C+bash%60.+Open+Claude+Code+%28which+the+install+also+wires+up+via+%60.claude%2Fsettings.local.json%60%29+and+ask+any+question+that+requires+Claude+to+locate+a+specific+symbol+or+file.&validate_claims_part_3=%22where+is+the+X+defined%22+%E2%80%94+for+any+class%2C+function%2C+or+feature+name+in+the+repo.+With+context-os+active+you+should+see+a+%60%3Ccontext-os%3Aautocontext%3E%60+block+prepended+to+Claude%27s+input+and+Claude+should+open+the+right+file+in+turn+1+instead+of+running+Glob+%E2%86%92+Grep+%E2%86%92+Read+%E2%86%92+Read+%E2%86%92+Read.+Disable+by+setting+CONTEXT_OS_AUTOCONTEXT%3D0+to+verify+the+delta.&additional_comments=Demo+GIF+%2860s%29%3A+https%3A%2F%2Fraw.githubusercontent.com%2Fsravan27%2Fcontext-os%2Fmain%2Fdocs%2Fdemo.gif+%C2%B7+Methodology%3A+https%3A%2F%2Fgithub.com%2Fsravan27%2Fcontext-os%2Fblob%2Fmain%2Fdocs%2FMETHODOLOGY.md+%C2%B7+Full+eval+reports%3A+https%3A%2F%2Fgithub.com%2Fsravan27%2Fcontext-os%2Ftree%2Fmain%2Fpython%2Fevals%2Freports+%C2%B7+Uninstall%3A+%60bash+setup.sh+--uninstall%60+%28idempotent%2C+removes+only+files+context-os+wrote%29.)

After clicking, **also tick the 5 confirmation checkboxes** at the bottom of the form (the bot won't validate the issue otherwise):
- [ ] I have checked that this resource hasn't already been submitted
- [ ] It has been over one week since the first public commit
- [ ] All provided links are working and publicly accessible
- [ ] I do NOT have any other open issues in this repository
- [ ] I am primarily composed of human-y stuff and not electrical circuits

The maintainer's bot validates within minutes. If valid, the recommendation enters the review queue. Approval ≈ auto-PR adds context-os to the registry.

## T+5min  ·  r/ClaudeAI  (50k+ subscribers, direct fit)

[Submit to r/ClaudeAI →](https://www.reddit.com/r/ClaudeAI/submit?title=I+built+a+400-line+Python+hook+that+cuts+Claude+Code+token+usage+40.9%25+on+a+live+A%2FB+%28p%3D5e-7%29+%E2%80%94+no+embeddings%2C+no+server%2C+MIT&url=https%3A%2F%2Fgithub.com%2Fsravan27%2Fcontext-os)

Reddit auto-detects the URL and uses GitHub's social preview. After submission, **post this as the first comment** (OP comments rank well on Reddit):

```
Quick reproduce in ~5 min, no Anthropic key needed:

  git clone https://github.com/sravan27/context-os && cd context-os
  python3 python/evals/runners/ranker_floor.py        # 9 hard CI gates, ~45s
  python3 python/evals/runners/multi_repo_eval.py     # 36 prompts × 3 OSS repos

The live -40.9% A/B does require a key, but the raw usage JSON from all 36
`claude --print` calls is committed at
python/evals/reports/live-session-bench-raw.json so the ratio math is
auditable without one.

Demo GIF (60s):
https://raw.githubusercontent.com/sravan27/context-os/main/docs/demo.gif

Happy to dig into the ranker design (8 signals + plural/singular stems +
df-discriminativity), the ablations, or the cross-repo eval — ask away.
```

## T+15min  ·  r/LocalLLaMA  (AI tools community, very technical)

[Submit to r/LocalLLaMA →](https://www.reddit.com/r/LocalLLaMA/submit?title=Static-analysis+RAG+for+Claude+Code%3A+400-line+stdlib+Python+hook%2C+-40.9%25+tokens+on+a+live+A%2FB+over+36+real+claude+--print+calls+%28p%3D5e-7%29&url=https%3A%2F%2Fgithub.com%2Fsravan27%2Fcontext-os)

Tone-match for r/LocalLLaMA: lead with the technical pitch (static-analysis RAG, no embeddings) over the marketing pitch. Same first-comment seed as above.

## T+30min  ·  r/programming  (generalist, very large, demands rigor)

[Submit to r/programming →](https://www.reddit.com/r/programming/submit?title=A+400-line+Python+hook+cuts+Claude+Code+token+usage+40.9%25+on+a+live+A%2FB+%28no+embeddings%2C+no+server%2C+p%3D5e-7%29&url=https%3A%2F%2Fgithub.com%2Fsravan27%2Fcontext-os)

r/programming aggressively removes self-promotion. If the post drops, do NOT repost. Same content as r/ClaudeAI; the audience overlap is small enough that cross-posting won't burn either side.

## T+60min  ·  r/Anthropic  (small but exact fit)

[Submit to r/Anthropic →](https://www.reddit.com/r/Anthropic/submit?title=400-line+stdlib+Python+hook+for+Claude+Code%3A+live+A%2FB+shows+-40.9%25+aggregate+tokens+%28p%3D5e-7%29%2C+cross-repo+MRR+0.545+vs+0.461+best+baseline&url=https%3A%2F%2Fgithub.com%2Fsravan27%2Fcontext-os)

Smaller subreddit but every reader is exactly the target.

## Held in reserve

### HN — when the rate-limit lifts
The prefilled submit URL is still good:
https://news.ycombinator.com/submitlink?u=https%3A%2F%2Fgithub.com%2Fsravan27%2Fcontext-os&t=Show+HN%3A+A+400-line+Python+hook+cuts+Claude+Code+token+usage+40.9%25+%28live+A%2FB%2C+p%3D5e-7%29

Try again in 48h. If still blocked: HN's "submit" route works through gateways like https://news.ycombinator.com/submit (manual form). HN account >30 days old, with karma >5, hits no rate-limit.

### Twitter/X thread — if account access returns
Full thread (10 tweets) is in [`TWEETS.md`](TWEETS.md). One-click first tweet:
https://twitter.com/intent/tweet?text=I+cut+Claude+Code+token+usage+by+40.9%25+with+a+400-line+Python+hook.%0A%0ALive+A%2FB+on+36+real+claude+--print+calls%3A%0A-+-40.9%25+aggregate+tokens%0A-+6%2F6+prompt-level+wins%0A-+p+%3D+5.06e-07%0A-+Cohen+d+%3D+1.84%0A%0ARepo%3A+github.com%2Fsravan27%2Fcontext-os+%F0%9F%A7%B5

### dev.to article — already drafted
Article is in [`DEVTO-ARTICLE.md`](DEVTO-ARTICLE.md). Publish at https://dev.to/new — paste, set the `claude` and `developertools` tags.

## What I (Claude) did from this kit, on your behalf

- Commented on the existing GH feature-request issue [anthropics/claude-code#53224](https://github.com/anthropics/claude-code/issues/53224) with the new GIF + cross-repo + regression-floor + latency evidence. The issue had 0 comments since filing 18 days ago; the comment bumps it and notifies anyone watching.
- Built every prefilled submit URL above. You click. I cannot click for you on accounts where I have no auth.

## What I'm NOT doing  (and why)

- **No `gh` submissions to awesome-claude-code.** The maintainer's CONTRIBUTING explicitly bans programmatic submissions: "Issues must be submitted by human users using the github.com UI... Doing so violates the Code of Conduct and submissions will be automatically closed." So this link is for the user only.
- **No Anthropic DMs.** Same rule as before — cold reach-out during launch reads as desperation. The GH issue comment is the *only* signal we send Anthropic-side, and it's evidence, not ask.
- **No HN auto-retry loop.** HN's rate-limit is anti-abuse. Retrying inside the window makes it worse. Try again in 48 hours, manually.

## After 24h  ·  honest assessment

- ≥50 upvotes on r/ClaudeAI + awesome-claude-code submission validated = pass. Reply to every comment.
- Any "added to the list" notification from awesome-claude-code = small win. Star count starts climbing from ambient discovery alone.
- <10 upvotes everywhere = the title or the demo isn't right. Wait 4 weeks, ship v2.9 with one new piece of evidence (semantic reranker, 100k-file scaling, real-user testimonial), relaunch with that as the headline.

## Reference: the body templates

All paste-ready bodies live in [`SHOW-HN.md`](SHOW-HN.md), [`TWEETS.md`](TWEETS.md), [`REDDIT.md`](REDDIT.md), [`LINKEDIN.md`](LINKEDIN.md), [`DEVTO-ARTICLE.md`](DEVTO-ARTICLE.md). The original gated launch checklist is at [`LAUNCH-CHECKLIST.md`](LAUNCH-CHECKLIST.md) — kept for reference, but its conditional gates are why we sat unposted for 15 days. Use *this* file instead.
