# Techniques

Twenty-eight techniques, grouped by delivery mechanism. Evidence column is honest about where each number comes from.

| # | Technique | Mechanism | Evidence |
|---|-----------|-----------|----------|
| 1 | Response shaping | `CLAUDE.md` directives (drop preamble, recap, tool announcements) | Third-party benchmark ([caveman](https://github.com/JuliusBrussee/caveman)); ablation pending |
| 2 | Output style `terse` | `.claude/output-styles/terse.md` invoked via `/output-style terse` | [Documented behavior](https://docs.claude.com/en/docs/claude-code/output-styles) |
| 3 | Noise filtering | `.claudeignore` with 100+ patterns (`node_modules`, `dist`, `.next`, `target`) | Measured per-repo via `--measure`; end-to-end in [METHODOLOGY.md](METHODOLOGY.md) |
| 4 | Secret exclusion | `.claudeignore` blocks `.env`, `*.pem`, `credentials.json`, SSH/AWS | Documented behavior |
| 5 | Repo map + stack hints | `CLAUDE.md` block generated from stack detection | Ablation pending |
| 6 | Thinking budget cap | `MAX_THINKING_TOKENS=8000` in `settings.json` | [Documented env var](https://docs.claude.com/en/docs/claude-code/settings#environment-variables) |
| 7 | Early compaction | `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80` (default 95) | Documented env var |
| 8 | Prompt caching 1h TTL | `ENABLE_PROMPT_CACHING_1H=1` | [Documented env var](https://docs.claude.com/en/docs/claude-code/settings#environment-variables) |
| 9 | Non-essential traffic off | `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` | Documented env var |
| 10 | Context cap | `CLAUDE_CODE_MAX_CONTEXT_TOKENS=150000` | Documented env var |
| 11 | Permission auto-grant | `settings.json` allowlist for Read/Glob/Grep/git/test runners | Documented behavior |
| 12 | statusLine | `.claude/statusline.sh` (model · branch · context-os marker) | Documented behavior |
| 13 | Slash commands (core) | `/compact`, `/context`, `/ship`, `/cheap` in `.claude/commands/` | Documented behavior |
| 14 | Haiku subagent | `.claude/agents/explorer.md` delegates exploration to Haiku | Model pricing ratio (Sonnet:Haiku); ablation pending |
| 15 | **Dedup guard** | PreToolUse hook: blocks duplicate `Read`/`Glob`/`Grep` within 10min | Smoke-tested in CI; session-profile reports list how many duplicates were caught |
| 16 | **Loop guard** | PreToolUse hook: warns at 5 edits, blocks at 8 edits on same file per session | Smoke-tested in CI; addresses a pattern called out in Claude Code best-practices |
| 17 | **Session profiler** | Stop hook: writes per-session token breakdown to `.context-os/session-reports/` — surfaces duplicate tool calls, edit loops, oversized results | Deterministic transcript parser; no telemetry phones home |
| 18 | Output compression (Rust) | PostToolUse hook wraps test/build output through typed reducers | Measured on 50-test cargo fixture (see METHODOLOGY.md §4) |
| 19 | Session memory (Rust) | PreCompact + Stop hooks write restart packet | Measured on fail-edit-pass cycle (see METHODOLOGY.md §5) |
| 20 | **Repo graph** | Install-time `.context-os/repo-graph.json`: top-level symbols, import edges, hot files from `git log --since=90d`. Walker is pure stdlib regex — Rust/Python/JS/TS/Go. No LSP, no tree-sitter. | Smoke-tested in CI; ~67KB on this 36-file repo |
| 21 | **File-size guard** | PreToolUse hook: blocks `Read` on files > 1500 lines without `offset/limit`. Nudges Claude to use a slice or delegate to explorer subagent. | Smoke-tested in CI; env-overridable threshold |
| 22 | **`/find <symbol>`** | Slash command: lookup in `symbol_index` → `file:line (kind)`. No grep. | Ships with graph — trivial Claude-side JSON parse |
| 23 | **`/deps <file>`** | Slash command: lookup imports + importers. Surfaces dependency subgraph without reading source. | Ships with graph |
| 24 | **`/hot`, `/warm-clear`, `/relevant <query>`** | `/hot` = top files by git change frequency. `/warm-clear` = write handoff before `/clear`. `/relevant` = TF-IDF-lite relevance score from graph (no reads, no grep). | Ships with graph |
| 25 | **`auto_context` (graph RAG)** | UserPromptSubmit hook — parses your prompt, looks up keywords/paths/symbols in `.context-os/repo-graph.json`, and prepends a compact `<context-os:autocontext>` block with `file:line · symbol (kind) · imports` candidates. **Claude's first turn starts with structure already in hand.** No embeddings, no server, ~50ms. Env-overridable. | **Live Claude A/B (36 `claude --print` calls, 3 runs per arm): −40.9% aggregate tokens, 6/6 prompts win, median −37.3%** (`python/evals/reports/live-session-bench.md`). Offline eval on 32 hand-labeled prompts across Python + TS + Rust fixtures: **P@3 = 0.604, MRR = 0.938, coverage = 1.00, +0.375 MRR lift over naive-filename baseline**. Session-replay simulation: −80.2% tokens to first relevant file, 32/32 wins. Reports: `autocontext-eval.md`, `session-replay.md`, `live-session-bench.md`. CI-gated (offline + replay), live-bench reproducible via `python3 python/evals/runners/live_session_bench.py`. |
| 26 | **`prewarm` (session brief + graph autobuild)** | SessionStart hook — emits `<context-os:prewarm>`: handoff-packet reminder, git state (branch + uncommitted + ahead/behind), top-3 hot files, flags from the latest session report. **Also detects stale graphs** (`>7d` or `>20` source files newer) and rebuilds in background — next session's auto-context uses the fresh index. | Smoke-tested in CI (stale + autobuild paths); reuses graph + session-profile output |
| 27 | **`/insights`** | Slash command — aggregates `.context-os/session-reports/*.md`: recurring duplicate patterns, top token-sink files, one-line actionable suggestion. | Ships with session-profile; actionable on sessions ≥ 2 |
| 28 | **`/rebuild-graph`** | Slash command — runs `build_repo_graph.py` from the repo root and confirms the fresh index is live. Use when prewarm flags staleness, or after large refactors. | Ships with graph; tested in CI |
| 29 | **Receipts: `savings_tracker` + `/savings`** | Turns auto_context's *invisible* savings into a visible, personal number — **measured causally, not estimated**. A Stop hook reconstructs each prompt's first turn from the transcript and classifies it *assisted* (first action was a `Read` of a surfaced file, no Glob/Grep) vs *explored* (it searched first). The exploration cost is read off real `tool_result` sizes, so each avoided search is credited the average a search *actually cost in that session* (clamped ≤15k; labelled 8k fallback when nothing's there to measure). statusLine shows a live `💰 2.3M saved · 5d🔥` meter; `/savings` prints a dashboard — searches avoided, the measured per-search cost, day-streak, dollar value, rate-limit runway, and a copy-paste shareable card. **The in-product, per-user version of the live A/B.** | 29-check correctness gate in CI (`python3 python/evals/runners/savings_test.py`): causal assisted-vs-explored classification, measured-vs-estimate per-hit, exploration-cost measurement, session-isolation, milestone, streak, fail-open. Under-claims by design. |

Techniques 1–17, 20–29 install via `setup.sh` (shell + Python stdlib only). Techniques 18–19 require the optional Rust binary.

## Architecture

`setup.sh` is a single shell script that writes 15 config-only techniques plus 7 Python hooks plus a repo graph builder. It detects stack, builds `.context-os/repo-graph.json` (symbol index + import edges + hot files), generates `CLAUDE.md` with a `<!-- context-os -->` block that embeds the graph summary, writes `.claudeignore`, merges `.claude/settings.json`, drops twelve slash commands (`/compact`, `/context`, `/ship`, `/cheap`, `/find`, `/deps`, `/hot`, `/warm-clear`, `/relevant`, `/insights`, `/rebuild-graph`, `/savings`) / output style / statusLine / explorer subagent into `.claude/`, and installs `.claude/hooks/{dedup_guard,loop_guard,file_size_guard,session_profile,auto_context,prewarm,savings_tracker}.py` plus `.context-os/build_repo_graph.py` and `.context-os/scripts/savings_report.py` with merged entries (PreToolUse + UserPromptSubmit + SessionStart + Stop) in `.claude/settings.local.json`.

Three of the hooks are novel in Claude Code's ecosystem:

- **`auto_context.py` (UserPromptSubmit).** Static-analysis RAG, no embeddings. Parses the prompt, extracts symbols/paths/keywords, ranks against the graph (exact symbol match = 10, case-insensitive = 8, file-path hit = 8, importer edge = 5, hot-file boost = +2), and prepends the top N as a compact `<context-os:autocontext>` block. The prompt hits Claude with structure already attached — first turn typically skips 5–10 exploratory tool calls. `CONTEXT_OS_AUTOCONTEXT=0` disables.
- **`prewarm.py` (SessionStart).** Emits a session brief: handoff-packet reminder (if `.context-os/handoff.md` exists), git state (branch + dirty + ahead/behind), graph staleness + background rebuild when stale, top-3 hot files, flags from the latest session report. Staleness thresholds: `CONTEXT_OS_GRAPH_MAX_AGE_DAYS=7`, `CONTEXT_OS_GRAPH_MAX_CHANGED=20`. `CONTEXT_OS_GRAPH_AUTOBUILD=0` disables the background rebuild (shows `/rebuild-graph` hint instead). `CONTEXT_OS_PREWARM=0` disables the whole hook.
- **`savings_tracker.py` (Stop).** The visibility layer, and the most rigorous part. auto_context saves ~40% of first-turn tokens — but silently. This hook reconstructs each prompt's first-turn behaviour from the transcript: an *assisted* prompt opened a surfaced file as its first action with no `Glob`/`Grep`; an *explored* prompt searched first, and its token cost is measured directly from the real `tool_result` sizes. Each avoided search is credited the **measured** average exploration cost from that same session (clamped to [1.5k, 15k]); only sessions with no exploration to calibrate against fall back to a labelled 8k estimate. It maintains `.context-os/savings/{ledger.jsonl,total.json}`, prints a one-line receipt (`1 prompt went straight to the right file → ~5,000 tokens saved (a search cost ~5,000 tok here, measured)`) plus a milestone celebration. The statusLine reads the cached total for a live meter; `/savings` (backed by `.context-os/scripts/savings_report.py`) renders the dashboard — searches avoided, measured per-search cost, streak, runway, dollar value — and a shareable card. `CONTEXT_OS_SAVINGS=0` disables; `CONTEXT_OS_SAVINGS_PER_HIT` overrides the per-hit credit.

The Python hooks are zero-dependency (stdlib only), fail-open on any error (never break a user session), and store per-session state under `~/.context-os/state/`. Each hook is auditable — cat it and read 100 lines.

The optional Rust binary (`apps/cli`) installs two additional hooks wired in `hooks.json`:

- `PostToolUse` (hooks.json:12) for test/build output compression via reducer-engine.
- `PreCompact` (hooks.json:38) and `Stop` (hooks.json:51) for session memory handoff.

Rust crates: `reducer-engine` (typed output compression), `session-memory` (handoff writer), `token-estimator`, `config`, `telemetry` (local-only; writes to `.context-os/`, never leaves machine).

Manual techniques not automated but documented in `CLAUDE.md`: `/clear` between tasks, `/btw` for side questions, `/compact [instructions]`, plan mode (`Shift+Tab`), specific prompting, `@filename` references, writer/reviewer split, explicit explorer-subagent delegation.
