# Show HN draft

## Title (pick ONE — A/B value listed)

**Recommended:**
> **Show HN: A 400-line Python hook cuts Claude Code token usage 40.9% (live A/B, p=5e-7)**

Alternatives, ordered by likely uplift:
- Show HN: I cut my Claude Code token bill 40.9% with a 400-line Python hook
- Show HN: Static-analysis RAG for Claude Code — −40.9% tokens, no embeddings
- Show HN: Context OS – a Claude Code hook that beats BM25 across 36 prompts × 3 OSS repos

Title rules learned from research (`/docs/distribution/RESEARCH.md`):
- Specific number in the title (40.9%, 400-line)
- First-person motivation ("my", "I")
- One striking technical claim that signals rigor (p=5e-7)

## URL

`https://github.com/sravan27/context-os`

## Body (250-300 words — HN truncates after; lead has to do the work)

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
Pitch doc for the Claude Code team: docs/PITCH.md
Reviewer walkthrough (20 min): docs/REVIEW-CHECKLIST.md
```

## First-comment seed (post immediately after submission as OP)

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

## Pre-built rebuttals (paste-ready answers to predicted top comments)

### "40% sounds too good — what's the catch?"

> Two catches stated up front in the README:
> 1) On repos where prompts already name the exact class (psf/requests, MRR 0.750 vs bm25-symbols 0.875), we lose. Lexical-ceiling regime.
> 2) The live A/B is 36 calls on 6 prompts. p<0.001 is real but not Anthropic-scale. Their telemetry is bigger than my fixture.
>
> Everything else — the ranker quality, latency, robustness — is CI-gated. The numbers don't move silently.

### "Why not just use embeddings / a vector DB?"

> Three reasons:
> 1) Cold-start: embedding 50k files is slow + needs a model + needs a binary dep. The Python hook ships with `python3` only.
> 2) Cost: every prompt becomes a model call before Claude sees it.
> 3) Quality: on top-1 precision (the metric that matters because Claude only acts on the top result), well-tuned BM25 + path heuristics + a few semantic-ish signals already gets 0.984 MRR on synthetic. Embeddings help on broad recall, which isn't the bottleneck.
>
> If/when this gets ported into `claude` itself, embeddings as an optional reranker on top of the lexical layer is the obvious v3.

### "Isn't this just BM25 with extra steps?"

> Ablation answers this in `python/evals/reports/autocontext-ablation.md`:
> - BM25 over symbols alone: MRR 0.875
> - BM25 over paths alone: MRR 0.714
> - auto_context full ranker: MRR 0.984
>
> The +0.109 over BM25-symbols is from: NL→code expansions (authentication→auth, matcher→match), import-edge traversal, hot-file boost, test/hub-file penalties, plural↔singular stems, df-discriminative path scoring, file-level aggregation. Each contributes; removing the biggest (`path_substr`) costs 0.062 MRR.

### "How does this compare to {zilliztech/claude-context, claude-context-optimizer, ...}"

> The closest comparable is zilliztech/claude-context (MCP + Zilliz Cloud, ~40% claim, vector-coupled). Differences:
> - We measure on **live Claude calls**, not synthetic eval. p=5e-7 on real token usage.
> - Local-only — no Zilliz Cloud, no vector DB, MIT-licensed Python hook.
> - Cross-repo evidence: 36 hand-labeled prompts × 3 unseen OSS repos. Most competitors quote one synthetic number.
> - CI-enforced regression floor — 9 hard gates that would red-line a PR if quality drifts.

### "Will this work on my $LANGUAGE?"

> Symbol extraction is regex-based and ships handlers for Python, TypeScript/JavaScript, Rust, Go. For other languages it falls back to path-only ranking. The cross-repo eval covers Py + JS + Rust on real OSS code. Tree-sitter would push recall higher at the cost of a native dep.

### "Why are you giving this away to Anthropic?"

> Because the right place for this is inside `claude` itself, not as a third-party plugin. Discovery is the problem — users who would benefit most (new to Claude Code) won't find a GitHub plugin. The pitch doc (`docs/PITCH.md`) lays out three integration paths from "bundle the hook" to "default-on with telemetry-driven rebuild." MIT-licensed; happy to PR or donate the code.

### "Latency at 100k files?"

> Untested. Currently p99 589ms at 50k files (measured). Linear extrapolation = ~1.2s at 100k, over the 1s SLA. v2.7 already moved IDF to a precomputed `path_df` so the hook is O(tokens × matches) per query, not O(files × tokens). The remaining O(files) scan is the path-substring loop; prefix-bucketing would drop that but isn't built. Concrete next step if Anthropic ports this internally.

### "Did you cherry-pick the OSS repos?"

> I picked the first three popular repos that span the three languages and weren't already in my fixtures. Pinned SHAs are in `python/evals/multi_repo_prompts/*.json`. The acceptance criterion in `multi_repo_eval.py` is honest: weighted aggregate must beat every baseline, AND per-repo must beat the avg of the five baselines. We surface the one repo (psf/requests) where bm25-symbols matches us so reviewers don't have to find that themselves.

### "Where's the code?"

> Hook: `hooks/python/auto_context.py` (~400 lines, stdlib only).
> Graph builder: `.context-os/build_repo_graph.py`.
> Eval runners: `python/evals/runners/`.
> Reports (CI-regenerated on every PR): `python/evals/reports/`.

### "How do I install?"

> ```
> curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
> ```
> Idempotent. Reversible (`bash setup.sh --uninstall`). Status check (`--status`). Dry-run estimator (`--measure`).

## Timing

- **Best:** Tuesday 8:00–9:30am ET (5–6:30am PT). Peak HN traffic, low Show HN competition.
- **OK:** Wednesday/Thursday morning ET.
- **Avoid:** Friday afternoon, weekends, holidays.

## Post-submission checklist

- [ ] Watch the rank for the first 30 minutes. If it falls off the front page, do not flag/repost.
- [ ] Post the first-comment seed within 60 seconds of submission.
- [ ] Reply to every top-level comment in the first 2 hours, even one-line ones. HN rewards engagement.
- [ ] When the post lands on /front, post the link in:
  - X thread (see `TWEETS.md`)
  - Anthropic Discord #show-and-tell channel
  - Reddit r/ClaudeAI (see `REDDIT.md`)
- [ ] Do NOT email Boris Cherny / Cat Wu until the HN post is on the front page — otherwise it looks like spam. Once it's on /front, the email writes itself.

## Anti-patterns to avoid

- ❌ "I open-sourced X" framing — got 7 pts when tested by similar repo
- ❌ Buzzword-heavy title (no "AI", "revolutionary", "framework")
- ❌ More than one statistic in the title
- ❌ Replying combatively to skeptics — every "but actually" comment is a free FAQ entry. Treat them as gifts.
