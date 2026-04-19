# Context OS

[![CI](https://github.com/sravan27/context-os/actions/workflows/ci.yml/badge.svg)](https://github.com/sravan27/context-os/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Context OS is a curated set of token optimizations for Claude Code, packaged as an idempotent, reversible installer. It writes `CLAUDE.md`, `.claudeignore`, `settings.json`, **ten slash commands** (four query a pre-built repo graph so Claude can skip grep, one aggregates token-spend patterns across sessions), an output style, a statusLine, a Haiku subagent, a **repo graph** (symbol index + import edges + hot files from `git log`), and **six zero-dependency Python hooks** — including **`auto_context`**, a UserPromptSubmit hook that performs static-analysis RAG against the graph before Claude sees your prompt, and **`prewarm`**, a SessionStart hook that hands Claude a one-paragraph brief (git state, hot files, last-session flags) at Turn 1. Not a wrapper, not a proxy, no runtime dependency besides `python3` for the hooks (with an optional Rust binary for two additional hook-based techniques).

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

## What it installs

**Twenty-seven techniques**, grouped by delivery mechanism. Evidence column is honest about where each number comes from.

| # | Technique | Mechanism | Evidence |
|---|-----------|-----------|----------|
| 1 | Response shaping | `CLAUDE.md` directives (drop preamble, recap, tool announcements) | Third-party benchmark ([caveman](https://github.com/JuliusBrussee/caveman)); ablation pending |
| 2 | Output style `terse` | `.claude/output-styles/terse.md` invoked via `/output-style terse` | [Documented behavior](https://docs.claude.com/en/docs/claude-code/output-styles) |
| 3 | Noise filtering | `.claudeignore` with 100+ patterns (`node_modules`, `dist`, `.next`, `target`) | Measured per-repo via `--measure`; end-to-end in [METHODOLOGY.md](docs/METHODOLOGY.md) |
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
| 25 | **`auto_context` (graph RAG)** | UserPromptSubmit hook — parses your prompt, looks up keywords/paths/symbols in `.context-os/repo-graph.json`, and prepends a compact `<context-os:autocontext>` block with `file:line · symbol (kind) · imports` candidates. **Claude's first turn starts with structure already in hand.** No embeddings, no server, ~50ms. Env-overridable. | Smoke-tested in CI; typical save on first turn is 5–10 exploratory tool calls |
| 26 | **`prewarm` (session brief)** | SessionStart hook — emits `<context-os:prewarm>`: handoff-packet reminder, git state (branch + uncommitted + ahead/behind), top-3 hot files, flags from the latest session report. **Turn 1 starts informed.** | Smoke-tested in CI; reuses graph + session-profile output |
| 27 | **`/insights`** | Slash command — aggregates `.context-os/session-reports/*.md`: recurring duplicate patterns, top token-sink files, one-line actionable suggestion. | Ships with session-profile; actionable on sessions ≥ 2 |

Techniques 1–17, 20–27 install via `setup.sh` (shell + Python stdlib only). Techniques 18–19 require the optional Rust binary.

## What it doesn't do

- No LLM routing, model swapping, or prompt rewriting.
- No proxy in front of Claude Code. Claude Code talks to Anthropic directly.
- No telemetry. No phone-home. No analytics. Read `setup.sh`.
- No attempt to outguess Anthropic's defaults where defaults are reasonable.

## Install

Per-project (recommended):

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

Global (response shaping + env vars to `~/.claude/`, applies to every project):

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --global
```

With the Rust binary (adds techniques 18–19, output compression + session memory):

```bash
cargo install --git https://github.com/sravan27/context-os --path apps/cli
context-os init
```

Stack auto-detection covers: Node/TypeScript, Next.js, Python, Rust, Go, Flutter/Dart. Stack-specific hints are appended to `CLAUDE.md`; generic hints otherwise.

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --uninstall
```

Removes only the `<!-- context-os -->` block from `CLAUDE.md` and files Context OS wrote. Pre-existing content is preserved. Idempotent.

## Measure

Dry-run estimator (no writes, no install):

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --measure
```

Scans the repo, counts source vs. noise files, and estimates per-session token savings from static config (noise filtering, thinking cap, response shaping, output compression). Output is an estimate from file counts, not a measurement of a live session.

Status check:

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --status
```

## Benchmarks

Methodology: [docs/METHODOLOGY.md](docs/METHODOLOGY.md). Raw reports: [python/evals/reports/](python/evals/reports/).

End-to-end measurement on a 2-file fixture (`/tmp/cos-bench-test`: one README and one `.js` file) via `scripts/benchmark.sh`, running the identical prompt through `claude --print` before and after install:

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Input tokens | 5 | 4 | −1 |
| Cached reads | 74,064 | 48,182 | −25,882 |
| Output tokens | 466 | 294 | −172 |
| Total tokens | 79,790 | 54,036 | −32.3% |
| Cost (USD, Sonnet 4.6) | $0.049 | $0.040 | −18.8% |

This is a trivial fixture. It is the floor, not the claim. A 2-file repo has almost nothing to filter; the 32% reduction comes mostly from response shaping and the thinking cap. On real repos with `node_modules`, `dist`, lockfiles, and longer sessions, the noise filtering and prompt caching contributions grow substantially. Reproduce against any repo:

```bash
git clone https://github.com/sravan27/context-os && cd context-os
scripts/benchmark.sh /path/to/your/repo --model sonnet
```

Requires `claude` on `PATH`. Results written to `/tmp/cos-last-benchmark.json`.

Component-level measurements (see METHODOLOGY.md for each):

- Output compression: 71% token reduction on 50-test cargo fixture; 48 passing tests collapsed to one line, 2 failures preserved verbatim.
- Protected-string recall: 100% on the reducer test corpus (paths, errors, versions).
- Concurrent writes: 5/5 PostToolUse writes captured under lockfile.
- Compaction survival: decisions and rationale survive a fail-edit-pass cycle across compaction boundary.
- Command pattern coverage: 42 test/build invocations matched including `cd /x && RUST_BACKTRACE=1 cargo test`.

## Architecture

`setup.sh` is a single shell script that writes 15 config-only techniques plus 6 Python hooks plus a repo graph builder. It detects stack, builds `.context-os/repo-graph.json` (symbol index + import edges + hot files), generates `CLAUDE.md` with a `<!-- context-os -->` block that embeds the graph summary, writes `.claudeignore`, merges `.claude/settings.json`, drops ten slash commands (`/compact`, `/context`, `/ship`, `/cheap`, `/find`, `/deps`, `/hot`, `/warm-clear`, `/relevant`, `/insights`) / output style / statusLine / explorer subagent into `.claude/`, and installs `.claude/hooks/{dedup_guard,loop_guard,file_size_guard,session_profile,auto_context,prewarm}.py` plus `.context-os/build_repo_graph.py` with merged entries (PreToolUse + UserPromptSubmit + SessionStart + Stop) in `.claude/settings.local.json`.

Two of the hooks are novel in Claude Code's ecosystem:

- **`auto_context.py` (UserPromptSubmit).** Static-analysis RAG, no embeddings. Parses the prompt, extracts symbols/paths/keywords, ranks against the graph (exact symbol match = 10, case-insensitive = 8, file-path hit = 8, importer edge = 5, hot-file boost = +2), and prepends the top N as a compact `<context-os:autocontext>` block. The prompt hits Claude with structure already attached — first turn typically skips 5-10 exploratory tool calls. `CONTEXT_OS_AUTOCONTEXT=0` disables.
- **`prewarm.py` (SessionStart).** Emits a 4-line session brief: handoff-packet reminder (if `.context-os/handoff.md` exists), git state (branch + dirty + ahead/behind), top-3 hot files, flags from the latest session report. `CONTEXT_OS_PREWARM=0` disables.

The Python hooks are zero-dependency (stdlib only), fail-open on any error (never break a user session), and store per-session state under `~/.context-os/state/`. Each hook is auditable — cat it and read 100 lines.

The optional Rust binary (`apps/cli`) installs two additional hooks wired in `hooks.json`:

- `PostToolUse` (hooks.json:12) for test/build output compression via reducer-engine.
- `PreCompact` (hooks.json:38) and `Stop` (hooks.json:51) for session memory handoff.

Rust crates: `reducer-engine` (typed output compression), `session-memory` (handoff writer), `token-estimator`, `config`, `telemetry` (local-only; writes to `.context-os/`, never leaves machine).

Manual techniques not automated but documented in `CLAUDE.md`: `/clear` between tasks, `/btw` for side questions, `/compact [instructions]`, plan mode (`Shift+Tab`), specific prompting, `@filename` references, writer/reviewer split, explicit explorer-subagent delegation.

## Contributing

To add a technique, open a PR with:

1. The config change (or hook code).
2. A test in `python/evals/` or `tests/` that exercises it.
3. An entry in the Evidence column pointing to a measurement or documented behavior. "Ablation pending" is acceptable for new entries; "this seems like it should help" is not.

Tests:

```bash
cargo test
python3 python/evals/runners/safe_mode_runner.py
python3 python/evals/runners/compaction_survival_runner.py
scripts/benchmark.sh /tmp/cos-bench-test --model sonnet
```

## Limitations

- Does not bypass usage limits.
- Response shaping effectiveness varies by task: 40–65% on explanation-heavy, 13–21% on structured code generation (third-party measurement; our ablation pending).
- Hook-based techniques depend on Claude Code exposing PreToolUse, PostToolUse, PreCompact, SessionStart, UserPromptSubmit, Stop.
- The `<!-- context-os -->` CLAUDE.md block costs ~12–15% input overhead per turn. Amortized across a session, it pays back in 1–2 turns on non-trivial repos.

## Acknowledgments

- [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) — response shaping benchmark.
- [Anthropic Claude Code documentation](https://docs.claude.com/en/docs/claude-code) — env vars, hooks, output styles, subagents.

## License

MIT. See [LICENSE](LICENSE).

## For the Claude Code team

If you work on Claude Code at Anthropic: see [docs/FOR-CLAUDE-CODE-TEAM.md](docs/FOR-CLAUDE-CODE-TEAM.md) for three findings and recommendations.
