# Launch: one-click submit links

> The kit is fully prepared. The only thing left is clicking submit on accounts I cannot access.
> Open each link in order. Each one prefills title + URL. You paste the body where indicated, then click submit.

## T+0  ·  Show HN  (the anchor post)

Click → confirm you're logged in → paste the **body** below → click submit.

**One-click submit URL:**
https://news.ycombinator.com/submitlink?u=https%3A%2F%2Fgithub.com%2Fsravan27%2Fcontext-os&t=Show+HN%3A+A+400-line+Python+hook+cuts+Claude+Code+token+usage+40.9%25+%28live+A%2FB%2C+p%3D5e-7%29

**Body** (paste into the text box):

```
I run Claude Code all day and kept hitting the 5-hour rate window mid-refactor.
Every time I looked at where the tokens went, the answer was the same: Claude's
first turn was burning ~35k tokens on Glob → Grep → Read → Read → Read,
exploring the repo blind before doing anything useful.

So I built a UserPromptSubmit hook that pre-builds a static-analysis graph of
the repo (symbols, imports, git-hot files) and injects ranked file:line
candidates into the prompt before Claude sees it. Stdlib Python, ~400 lines.
No embeddings, no server, no model call.

Receipts (all reproducible from one command):

  - Live A/B on 36 real `claude --print` calls (6 prompts × 3 runs × 2 arms):
    −40.9% aggregate tokens [bootstrap CI 32.7%, 48.9%], 6/6 prompt wins,
    paired t-test p = 5.06e-07, Cohen's d = 1.84, wall-clock −35.3%.

  - Cross-repo: 36 hand-labeled prompts × 3 unseen OSS repos
    (axios/axios JS, BurntSushi/ripgrep Rust, psf/requests Python).
    Weighted MRR 0.545 vs best lexical baseline 0.461 — +18.2%.
    Beats every baseline aggregate, in every language.

  - Hook p99 latency 118ms at 10k files, 589ms at 50k (1.7× under 1s SLA).

The honest scope note: on repos where prompts already name the exact class
(`PreparedRequest`, `HTTPError`), `bm25-symbols` matches us — that's the
lexical-retrieval ceiling regime. We win the aggregate, not every repo.

CI-gated regression floor (9 hard gates) prevents quality drift. 18/18
adversarial robustness cases pass.

Repo: https://github.com/sravan27/context-os
```

## T+60s  ·  First-comment seed  (post as OP, immediately after submission)

```
Quick reproduce in 5 minutes:

  git clone https://github.com/sravan27/context-os && cd context-os
  python3 python/evals/runners/ranker_floor.py        # 9 hard CI gates, ~45s
  python3 python/evals/runners/multi_repo_eval.py     # 36 prompts × 3 OSS repos

The only thing not reproducible without an Anthropic API key is the live A/B
(uses real `claude --print`). Raw usage JSON from all 36 calls is committed
under python/evals/reports/live-session-bench-raw.json so the ratio math is
auditable even without keys.

Happy to answer questions on:
- the ranker (8 signals + plural/singular stems + df-discriminativity + file
  aggregation; ablation in autocontext-ablation.md)
- why no embeddings (cost + cold-start + binary deps in a Python hook)
- why I think this belongs inside `claude` itself, not as a third-party plugin
```

## T+5min  ·  Tweet 1  (one-click)

Click → tweet is prefilled → click "Tweet".

https://twitter.com/intent/tweet?text=I+cut+Claude+Code+token+usage+by+40.9%25+with+a+400-line+Python+hook.%0A%0ALive+A%2FB+on+36+real+claude+--print+calls%3A%0A-+-40.9%25+aggregate+tokens%0A-+6%2F6+prompt-level+wins%0A-+p+%3D+5.06e-07%0A-+Cohen+d+%3D+1.84%0A%0ARepo%3A+github.com%2Fsravan27%2Fcontext-os+%F0%9F%A7%B5

Then paste tweets 2 through 10 as **replies to your own tweet 1**. The full thread text is in [`TWEETS.md`](TWEETS.md).

## T+10min  ·  Reddit r/ClaudeAI  (one-click)

Click → "url" tab is selected → title + URL prefilled → click submit.

https://www.reddit.com/r/ClaudeAI/submit?title=I+built+a+400-line+Python+hook+that+cuts+Claude+Code+token+usage+40.9%25+on+a+live+A%2FB+%28p%3D5e-7%29+%E2%80%94+no+embeddings%2C+no+server%2C+MIT&url=https%3A%2F%2Fgithub.com%2Fsravan27%2Fcontext-os

If it asks for a "text" body, paste:

```
Built a UserPromptSubmit hook that pre-builds a static-analysis graph of the
repo (symbols + imports + git-hot files) and injects ranked file:line
candidates into the prompt before Claude sees it. 400 lines of stdlib Python.

Live A/B on 36 real `claude --print` calls:
- −40.9% aggregate tokens (CI 32.7%, 48.9%)
- 6/6 prompt-level wins
- p = 5.06e-07

Cross-repo: 36 prompts × 3 unseen OSS repos (axios, ripgrep, requests).
Weighted MRR 0.545 vs 0.461 best lexical baseline.

MIT. No embeddings, no server, no telemetry. The Python hooks are stdlib-only —
auditable in ~400 lines.

Repo: https://github.com/sravan27/context-os
```

## T+15min  ·  LinkedIn  (paste, no URL prefill)

Open https://www.linkedin.com/feed/?shareActive&mini=true and paste the body from [`LINKEDIN.md`](LINKEDIN.md).

Do NOT boost — boosting Show-HN-style technical posts on LinkedIn signals desperation and gets less reach than organic.

## T+30min  ·  watch HN rank

- Open https://news.ycombinator.com/show in another tab. Refresh every 10 min.
- Reply to every top-level comment in the first 2 hours. Be technical, not promotional. Treat every "but actually" as a free FAQ entry — pre-built rebuttals are in [`SHOW-HN.md`](SHOW-HN.md).

## T+24h  ·  r/programming  (only if r/ClaudeAI is positive)

Cross-posting a dead post is worse than not posting. Skip this one if r/ClaudeAI got flagged or downvoted to zero. Template in [`REDDIT.md`](REDDIT.md).

## What I'm NOT doing  (and why)

- **Not DMing Anthropic employees.** Cold DMs from launch days read as begging. If the post is good, the link reaches them.
- **Not gating Tweet / LinkedIn on HN /front.** Independent surfaces. Post all of them within 20 minutes. The original launch checklist's conditional gates are why nothing went out — it sat in a markdown file for 15 days waiting for HN to magically take off first.
- **Not posting on Discord.** Same logic — wait for inbound, not outbound.

## After 24h  ·  honest assessment

- ≥100 HN pts + any Anthropic-employee comment = pass. Reply, engage, do not pivot to "selling."
- <30 HN pts, no organic X engagement = the title or the demo wasn't right. **Do NOT relaunch the same post.** Wait 4 weeks, ship a v2.9 with one new piece of evidence (semantic reranker, 100k-file scaling, real customer testimonial), relaunch with that as the headline.

## Backup: if HN flags or buries within the first hour

This is rare for Show HN with reproducible numbers, but if it happens:
1. Do **not** re-submit. HN auto-flags duplicates.
2. Check whether the title was the issue. The recommended title leads with "Show HN", has a specific number, and signals rigor (p=5e-7).
3. The X thread can still carry. Push that and the Reddit posts.
