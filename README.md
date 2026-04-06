# Context OS

**Get 2-5x more out of every Claude Code session.**

Context OS is a local-first context optimizer for Claude Code. It automatically compresses bloated tool outputs (stack traces, test logs, build output, JSON blobs), injects structured repo context into every session, and preserves continuity across usage limit resets — so you spend tokens on work, not waste.

## The problem

Claude Code users hit usage limits fast. Most token spend isn't on useful code generation — it's on Claude re-reading the same 500-line test log, re-discovering the repo structure, or losing context after compaction. Research shows compressed context [actually outperforms uncompressed](https://arxiv.org/abs/2509.19228) at 50K+ tokens. Less noise = better output.

## What it does

```
$ context-os init
indexed 847 source files, 12 configs
created CLAUDE.md with repo map
installed hooks (SessionStart, UserPromptSubmit, Stop)
added .context-os/ to .gitignore
done. Claude Code will now start sessions with repo context loaded.
```

After init, Context OS works invisibly through Claude Code hooks:

- **SessionStart** — loads handoff notes from the previous session (objective, modified files, decisions, failures, git state)
- **UserPromptSubmit** — injects compact status (branch, uncommitted files, objective) on every turn, surviving context compaction
- **Stop** — auto-saves session state with git diff, branch, uncommitted changes for the next session

### Typed reducers

When you pipe tool output through `context-os pipe`, it auto-detects the content type and compresses it:

| Content type | What it does | Safe-mode reduction |
|---|---|---|
| Stack traces | Collapses duplicate frames, keeps root error + file paths | **42%** |
| Test logs | Collapses passing tests to count, preserves all failures | **36%** |
| JSON blobs | Deduplicates arrays, samples unique items, compacts nested objects | **13%** |
| Config files | Strips comments, preserves keys + protected values | **13%** |
| Build logs | Collapses "Compiling..." lines, keeps errors/warnings | **~40%** |

All reductions are **safe by default**: 100% protected string recall, fail-open on uncertainty, provenance tracking on every transformation.

### Session continuity

When you hit a usage limit and start a new session, Claude reads the auto-generated handoff:

```markdown
# Session Handoff

## Git state
Branch: `feature/auth-middleware`
Last commit: `a1b2c3d fix: session token validation`
Uncommitted changes: 3 files
  - src/middleware/auth.rs
  - tests/auth_test.rs
  - Cargo.lock

## Objective
Implement JWT refresh token rotation

## Next steps
- Add token rotation endpoint
- Write integration test for expired refresh tokens

## Failed approaches (don't retry)
- Using cookie-based sessions (blocked by CORS policy)
```

No manual work. No forgetting what you were doing.

### Repo context in CLAUDE.md

Context OS scans your repo and generates a structured map that Claude reads at session start:

- Framework detection (Rust workspace, Next.js, Go, Python, Java)
- Entry points, modules, and dependency graph
- Behavioral rules that reduce wasted exploration messages
- Test file counts (not full listings)
- Capped at what fits in ~1K tokens

## Setup

```bash
# Build from source
cargo install --path apps/cli

# Initialize in your project
cd your-project
context-os init

# Verify everything is wired up
context-os doctor
```

That's it. Claude Code picks up the hooks automatically.

## How it works

Context OS never touches the network. Everything runs locally:

1. **Hooks** inject context at session boundaries and on every user prompt
2. **Reducers** compress specific content types with type-aware rules (not generic summarization)
3. **Repo memory** generates a structural map of your codebase for CLAUDE.md
4. **Session memory** tracks objectives, decisions, and failures across sessions
5. **Handoff** auto-gathers git state and session context for the next session

### Safety model

- **Safe mode** (default): 100% protected string recall required. Reducers fail open — if uncertain, return original content unchanged
- Every transformation records provenance (what was changed, why, before/after token counts)
- Token estimates are honest heuristics, not fake billing numbers
- All data stays on your machine (SQLite telemetry, file-based state)

## Benchmarks

Benchmarks run as CI gates, not marketing claims:

```
$ python3 python/evals/runners/safe_mode_runner.py

Passed: 5/5
Average reduction: 26.1%
Protected string recall: 100%

| Case              | Recall | Reduction % | Before | After |
|-------------------|--------|-------------|--------|-------|
| stack_trace_safe  | 1.00   | 42.28       | 149    | 86    |
| test_log_safe     | 1.00   | 36.20       | 163    | 104   |
| json_safe         | 1.00   | 13.07       | 199    | 173   |
| config_safe       | 1.00   | 12.99       | 77     | 67    |
| prompt_lint       | 1.00   | (linter)    | -      | -     |
```

## CLI commands

| Command | What it does |
|---|---|
| `context-os init` | Scan repo, generate CLAUDE.md, install hooks |
| `context-os pipe` | Read stdin, auto-detect, reduce, write to stdout |
| `context-os status` | Print compact context line (for UserPromptSubmit hook) |
| `context-os handoff` | Save session state + git state for next session |
| `context-os doctor` | Validate setup, run quick benchmark |
| `context-os reduce` | Reduce a specific file with a chosen reducer |
| `context-os estimate` | Estimate token count for a file |
| `context-os prompt-lint` | Analyze a prompt for waste patterns |
| `context-os index` | Build repo memory artifacts |
| `context-os inspect` | Print repo architecture as JSON |

## Architecture

```
context-os/
  apps/cli/          — Single binary CLI
  crates/
    reducer-engine/  — Typed reducers with confidence scoring
    repo-memory/     — Repo scanner and CLAUDE.md generator
    session-memory/  — Structured state with compaction
    proxy-core/      — Payload classification and orchestration
    prompt-linter/   — Prompt waste pattern detection
    token-estimator/ — Heuristic token counting
    telemetry/       — Local SQLite event store
    config/          — Typed configuration with merge semantics
  python/evals/      — Benchmark runners and scorers
  tests/fixtures/    — Test data for reducers and benchmarks
```

## Why not just use a bigger context window?

Research shows that LLMs [perform worse with longer contexts](https://arxiv.org/abs/2502.12962) when they can't rely on surface-level pattern matching (NoLiMa, ICML 2025). 11 of 13 models dropped below 50% baseline at just 32K tokens. More context is not better context. Compressed, relevant context produces better results AND costs fewer tokens.

## Limitations

- Token estimates are heuristic (not provider billing numbers)
- Safe mode prioritizes recall over compression — reductions are conservative
- Repo memory can go stale between `context-os init` runs
- Session memory compaction is lossy (keeps last 3 turns, 5 failures)
- Only 5 reducer types shipped (stack traces, test logs, JSON, config, build logs)

## Development

```bash
cargo test                                         # Run all 26+ tests
python3 python/evals/runners/safe_mode_runner.py   # Run benchmarks
```

## License

MIT
