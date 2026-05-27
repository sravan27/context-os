# context-os

[![CI](https://github.com/sravan27/context-os/actions/workflows/ci.yml/badge.svg)](https://github.com/sravan27/context-os/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Release](https://img.shields.io/github/v/release/sravan27/context-os?label=release)](https://github.com/sravan27/context-os/releases/latest)

**Cut Claude Code token usage by 40.9%.** A 400-line Python hook that builds a static graph of your repo (symbols + imports + git-hot files) and injects ranked `file:line` candidates into the prompt before Claude sees it. So the first turn opens the right file instead of grepping for it.

No embeddings. No server. No model call. ~50 ms.

Need this applied to a private repo this week? I have **2 paid audit slots open**. [Fund the $1,000 AI Agent Cost Leak Audit](https://buy.polar.sh/polar_cl_z0eLsPUJeMwrcNs4MQPAQbKIM3Rbdb8fLDgVj2RZcmr) or read the [audit scope](https://sravan27.github.io/money-27-proof/agent-cost-leak-audit.html). The OSS tool stays free; the sprint is for teams that want a private report, CI leak gate, and one concrete repo/workflow patch.

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

![demo](docs/demo.gif)

*60-second demo: graph stats → autocontext block with import counts → cross-repo eval (auto_context 0.545 winning) → 9/9 CI floors PASS. Reproduce with `bash docs/distribution/demo.sh`.*

## Private repo audit

If your team is already spending heavily on Claude Code, Codex, Cursor, or other coding agents and wants a private cost-leak report, I am doing **2 paid 48-hour audits** this week: [AI Agent Cost Leak Audit](https://sravan27.github.io/money-27-proof/agent-cost-leak-audit.html).

Payment starts the slot. After checkout, send repo/access details by email or private intake; do not paste private code into a public issue.

The open-source hook stays MIT and free. The paid audit is for teams that want the same measurement discipline applied to their own repo, prompts, and agent workflows.

What the paid sprint ships:

- a private repo scorecard using the same leak signals as the Action
- a short report on the highest-cost agent loops and file-noise sources
- one concrete CI, ignore-rule, or repo-guidance patch where the fix is clear
- a handoff note your team can reuse when running Claude Code, Codex, Cursor, or internal agents

Quick local preview:

```bash
python3 python/agent_cost_leak_check.py --repo . --json
```

CI recipe: [`docs/AGENT-COST-LEAK-CHECKER.md`](docs/AGENT-COST-LEAK-CHECKER.md). For public intake without sharing private code, use the [private audit request template](https://github.com/sravan27/context-os/issues/new?template=private_audit.yml).

Versioned GitHub Action:

```yaml
- uses: sravan27/context-os@v2.9.0
  with:
    max-score: "40"
```

## The number

Live A/B on 36 real `claude --print` calls, identical fixture, identical model, only difference is whether the hook is active:

| Metric                           |        Value |
| -------------------------------- | -----------: |
| Aggregate tokens                 |   **−40.9%** |
| Prompt-level wins                |      **6/6** |
| Bootstrap 95% CI                 |  32.7%–48.9% |
| Paired t-test                    |   p = 5.1e-7 |
| Wall-clock                       |       −35.3% |

Raw JSON for every call: [`python/evals/reports/live-session-bench-raw.json`](python/evals/reports/live-session-bench-raw.json) · methodology: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

Cross-repo: 36 hand-labeled prompts × 3 unseen OSS repos (axios, ripgrep, requests). Weighted MRR **0.545 vs 0.461** best lexical baseline — **+18.2%**. Beats every baseline in every language. Report: [`multi-repo-eval.md`](python/evals/reports/multi-repo-eval.md).

## What Claude sees

Before:
```
user: where is the gitignore parser
claude: Glob → Grep → Read → Read → Read → "found it in walk.rs"
```

After:
```
<context-os:autocontext>
crates/ignore/src/gitignore.rs:42  · Gitignore (struct)
crates/ignore/src/gitignore.rs:118 · matched (fn) · imports: …
</context-os:autocontext>
claude: Read crates/ignore/src/gitignore.rs → done
```

## Read less — the compounding cost nobody attacks

auto_context kills *first-turn* exploration. But the bigger, compounding cost is
that **every file Claude reads is re-sent on every later turn until compaction.**
Read an 800-line file at turn 3 and you pay for it again, and again, for 40 turns
— when Claude needed one 40-line function.

So when Claude goes to read a whole file, context-os intercepts it and hands back
the file's **outline** — every symbol with its exact line range, rendered from the
graph with *zero* file content — and Claude re-reads only the slice it needs:

```
user: (Claude is about to Read payment.py — 847 lines)
context-os intercepts ↓
  L12-45    class PaymentProcessor
  L47-89      def charge(self, amount, method)
  L91-120     def refund(self, txn_id)
  L340-410  def validate_card(number, cvv)
  … +28 symbols
  e.g. Read("payment.py", offset=47, limit=43) for the block at L47.

claude: Read payment.py offset=47 limit=43 → 43 lines, not 847.
```

The 800 lines never enter context — so they're never re-sent. One whole-file read
turned into an outline can keep ~20k tokens out of context per file. It fires once
per file per session (no nag), only on big files, and only when the graph has the
structure to slice. `/outline <file>` does it on demand. Disable with
`CONTEXT_OS_SMART_READ=0`.

## Your savings, measured — not estimated

Saving 40% silently builds no habit. So context-os keeps a receipt — and it
**measures** the saving causally from your own transcript, it doesn't guess.

Every prompt is classified: did Claude open the right file *first* (a search
**avoided**), or did it Glob/Grep around before finding it (an **exploration**)?
The exploration cost is read straight off the real `tool_result` sizes — so each
avoided search is credited the average a search *actually cost in your session*.
A Stop hook does this; the statusLine shows a live meter; `/savings` shows the rest:

```
💰 2.3M saved · 5d🔥        ← statusLine, every prompt

$ /savings
  All-time saved      2,340,000 tokens  (~$14.04)
  Runway bought            ~47 prompts before the rate window
  Searches avoided            412  (opened the right file with no Glob/Grep)
  Big reads sliced             96  (whole-file reads turned into an outline)

  Where it came from
  Avoided searches    1,402,000 tok  (auto_context → straight to file)
  Sliced big reads      938,000 tok  (smart_read → outline, not whole file)

  How it's measured
  A search cost        14,200 tokens on average — measured
                       from 287 of your own prompts that still explored
  ╭─────────────────────────────────────────────╮
  │            context-os · receipts            │
  │  2,340,000 tokens saved   (~$14.04)         │
  │  412 searches replaced by a direct open     │
  │  avg search cost 14,200 tok — measured      │
  ╰─────────────────────────────────────────────╯   ← copy/paste anywhere
```

Local-only, no phone-home. The credit per avoided search is clamped to ≤15k
(below the 21k aggregate the live A/B measured), and sessions with nothing to
measure fall back to a labelled 8k estimate — so the number under-claims, never
over-claims. Correctness is CI-gated (`python3 python/evals/runners/savings_test.py`, 39 assertions).

**Don't trust my A/B — replay it on *your own* history (no API key, $0):**

```bash
python3 python/evals/runners/replay_history.py --all
```

Scans your existing `~/.claude/projects/**/*.jsonl` transcripts and backtests
the whole stack: how many whole-file reads smart_read would have sliced (load
sizes measured exactly from your transcripts) and how many explorations
auto_context's top-5 would have collapsed. It's a counterfactual, not a live
A/B — and it's honest that results depend on your session mix (navigation-heavy
interactive work is the regime these hooks target; long autonomous build runs
show less).

## Install

Per-project:

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

Global response-shaping + env vars to `~/.claude/`:

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --global
```

Reproduce the eval locally:

```bash
git clone https://github.com/sravan27/context-os && cd context-os
python3 python/evals/runners/ranker_floor.py     # 9 CI-enforced floors, ~45s
python3 python/evals/runners/multi_repo_eval.py  # cross-repo eval, ~2 min
```

## What it installs

`setup.sh` writes 30 techniques across `CLAUDE.md`, `.claudeignore`, `.claude/settings.json`, thirteen slash commands, an output style, a Haiku explorer subagent, and eight stdlib-Python hooks under `.claude/hooks/`. Full list with evidence per row: [`docs/TECHNIQUES.md`](docs/TECHNIQUES.md).

Three hooks are the heart of it, all backed by one graph: **`auto_context.py`** (UserPromptSubmit — retrieval, skip first-turn exploration), **`smart_read.py`** (PreToolUse — structural slicing, read the slice not the file), and **`savings_tracker.py`** (Stop — measure both, causally) surfaced via `/savings`. All hooks fail-open — if they break, your session keeps going.

## What it doesn't do

- No LLM routing, model swapping, prompt rewriting.
- No proxy. Claude Code talks to Anthropic directly.
- No telemetry, no phone-home, no analytics. Read [`setup.sh`](setup.sh).

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --uninstall
```

Removes only the `<!-- context-os -->` block from `CLAUDE.md` and files context-os wrote. Idempotent.

## Limitations

- On repos where prompts already name the exact class (`psf/requests` calling out `PreparedRequest`), well-tuned BM25 ties us. Lexical-ceiling regime.
- Live A/B is 36 calls on 6 prompts — `p < 1e-6` is real but not Anthropic-scale.
- Symbol extraction is regex-based and ships handlers for Python, TS/JS, Rust, Go. Other languages fall back to path-only ranking.
- Hook adds ~12–15% input overhead per turn; amortizes in 1–2 turns on non-trivial repos.
- Hook p99 latency 118 ms at 10k files, 589 ms at 50k.

Full caveats: [`docs/limitations.md`](docs/limitations.md).

## Compatible with

Claude Code on macOS + Linux. Requires `python3` (stdlib only). Optional Rust binary (`apps/cli`) adds output compression and session-memory hooks.

## License

MIT. See [LICENSE](LICENSE).
