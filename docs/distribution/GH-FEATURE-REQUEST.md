# anthropics/claude-code Feature Request

File against https://github.com/anthropics/claude-code/issues/new — pick the **`feature_request`** template (`bug_report` is for regressions; ours is an enhancement).

## Title

> [FEATURE] Static-analysis RAG primitive: pre-prompt repo graph injection cuts first-turn tokens 40.9% on live A/B

## Body

```
## Problem

Claude Code's first-turn pattern on a "where is X" prompt is reliably
Glob → Grep → Read → Read → Read before the agent does anything useful.
On a 6-prompt fixture I instrumented with `claude --print --stream-json`,
the control arm averaged **51,000 tokens per prompt**, of which roughly
35k was first-turn exploration. The model has no map of the codebase
going into turn 1, so it grep-walks one.

This is a structural cost — every Claude Code user pays it on every
fresh session, regardless of model or pricing tier.

## Proposed solution

A static-analysis RAG primitive shipped inside Claude Code itself:

1. `claude context build` — walks the source tree, extracts symbols
   (function/class/type defs), import edges, git-hot files (90-day
   change frequency). Writes `.context-os/repo-graph.json` (or
   equivalent). Runs in <1s on a 5k-file repo, <10s on 50k.

2. UserPromptSubmit-time hook — parses the prompt, queries the graph
   (IDF-weighted symbol/path matches + import traversal + hot-file
   boost + test/hub-file penalties), prepends a compact ranked
   candidate list as `<context-os:autocontext>`. Hook latency ~50ms
   typical, p99 118ms at 10k files.

3. Stale-graph rebuild — detect via `git log --since=last-build` and
   rebuild in the background. User's next prompt uses the fresh index.

No embeddings. No server. No model call. The whole primitive is
~400 lines of stdlib Python in our reference implementation.

## Evidence (from a prototype I built and shipped MIT-licensed)

The prototype lives at https://github.com/sravan27/context-os and
has been measured exhaustively. Every number is reproducible from one
command, all reports CI-regenerated on every PR:

**Live A/B on 36 real `claude --print` calls** (6 prompts × 3 runs × 2 arms):
- −40.9% aggregate tokens [bootstrap CI 32.7%, 48.9%]
- 6/6 prompt-level wins
- paired t-test p = 5.06e-07
- Cohen's d = 1.84 (large effect)
- wall-clock −35.3% (11.80s → 7.64s mean per prompt)

**Cross-repo generalization** (36 hand-labeled prompts × 3 unseen OSS repos):
- axios/axios (JS, 214 files): MRR 0.382 vs best baseline 0.252 (+0.130)
- BurntSushi/ripgrep (Rust, 100 files): MRR 0.503 vs 0.459 (+0.044)
- psf/requests (Py, 36 files): MRR 0.750 vs bm25-symbols 0.875 (lexical-ceiling regime)
- **Weighted aggregate: auto_context 0.545 vs best lexical baseline 0.461. +18.2%.**

**Operational**:
- Hook p99 latency 118ms @ 10k files, 589ms @ 50k files (1.7× under 1s SLA)
- 18/18 adversarial robustness cases pass (unicode, regex bombs, path injection)
- 9 CI-enforced regression gates prevent quality drift on every PR
- 8-signal leave-one-out ablation confirms no dead weight

## Why upstream (vs. third-party plugin)

Discovery is the problem. Users who would benefit most (new to Claude Code)
won't find a GitHub plugin. The savings only accrue to Anthropic's hosted
users if the primitive is on by default.

Three integration paths, ordered by depth (full detail in
`docs/PROPOSAL.md` of the prototype repo):

- **(A) Bundle the hook.** Ship the reference implementation as
  `claude init-hooks --context`. Zero Anthropic-side work. Opt-in.
- **(B) First-class primitive.** `claude context build` and
  `claude context search` as CLI verbs. ~1 engineer-week to port to Rust.
- **(C) Default-on with telemetry-driven rebuild.** Anthropic-scale
  measurement loop catches regressions.

## Anti-patterns I want to flag

- **Embeddings.** Cold-start, cost, binary deps. On top-1 precision (the
  metric that matters because Claude only acts on the top result),
  well-tuned BM25 + path heuristics already get MRR 0.984 on synthetic.
  Embeddings as an optional reranker on top of the lexical layer is a
  reasonable v3, not v1.
- **MCP server.** Adds a network hop and a separate process to manage.
  An in-process hook (or Rust-port primitive) is cheaper.
- **Tree-sitter symbol extraction.** Higher recall but a native
  dependency. Regex extraction at 95% recall + the ranker recovering
  via path-substring matching is good enough for v1.

## Honest scope notes

- We lose on psf/requests in cross-repo eval. Prompts there use exact
  class names (`PreparedRequest`, `HTTPError`) — the lexical-retrieval
  ceiling regime where bm25-symbols caps. The aggregate win is real,
  the per-repo win is not universal.
- The live A/B is 36 calls on 6 prompts. Statistically significant
  (p<0.001) but Anthropic-scale telemetry would dwarf this.
- Tested on Py/TS/Rust/Go. Other languages fall back to path-only
  ranking until a per-language symbol extractor is added.

## What I'm offering

- The reference implementation under MIT, no strings.
- Methodology, evals, regression gates — all in the repo.
- Whatever consultation is useful for the port (1 engineer-week
  estimate). I do not need credit, equity, or attribution.

## What I'd want in return

- A stable `UserPromptSubmit` hook payload schema with a version
  header. Today it shifts in minor releases and every community hook
  has to keep up.
- A `claude --token-report` flag emitting per-turn usage as JSON.
  We hack it with `--stream-json` today; native support would unlock
  proper community benchmarking.

Pitch doc: https://github.com/sravan27/context-os/blob/main/docs/PITCH.md
Reviewer walkthrough (20 min): https://github.com/sravan27/context-os/blob/main/docs/REVIEW-CHECKLIST.md
Multi-repo eval report: https://github.com/sravan27/context-os/blob/main/python/evals/reports/multi-repo-eval.md
```

## Submission timing

- File **after** Show HN is up and trending (≥30 points). Link the HN post in the issue body.
- Mention `@bcherny` and `@catherinewu` in a follow-up comment (NOT in the issue body — the body should stand on its own merit).
- Use label `area:cost` if available — research showed that label gets engagement.

## Don't

- Don't submit before evidence is fresh. v2.8.0 was tagged today. Strike while the receipts are timestamped.
- Don't use the `bug_report` template — wrong category.
- Don't link to your X thread inside the issue. Engineers reading the issue are turned off by promo linking.
- Don't promise an exact engineer-week port. Hand-wave gracefully if pressed.
