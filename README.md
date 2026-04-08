# Context OS

[![CI](https://github.com/sravan27/context-os/actions/workflows/ci.yml/badge.svg)](https://github.com/sravan27/context-os/actions/workflows/ci.yml)

**Context OS is a local-first Claude Code resilience layer. It keeps the plan, failed attempts, and modified files alive through compaction and session resets.**

Context OS is not a generic prompt optimizer and not a cloud wrapper. It is a typed local utility for Claude Code workflows:

- `PreToolUse` reduces noisy Bash output before it bloats context.
- `PostToolUse` extracts decision-bearing signals from tests, builds, and edits.
- `PreCompact` emits a deterministic restart packet so key state survives compaction.
- `SessionStart` restores that packet with `context-os resume`.
- `Stop` writes a human-readable handoff for recovery and debugging.

Token reduction still matters, but it is supporting evidence, not the product story. The main promise is simple:

> **When Claude gets expensive, compacts, or you have to start a new session, you do not lose momentum.**

## Why this exists

Claude Code users do not just waste tokens on long logs. They lose momentum because compaction and session resets often drop:

- the current subtask
- why a chosen approach was accepted
- which approaches already failed
- which files were modified
- what should happen next

Most “context tips” are static advice. Context OS is local software that captures and replays that state automatically.

## What ships today

### 1. Compaction-aware decision replay

Context OS keeps `.context-os/session.json` as canonical structured state and `.context-os/journal.jsonl` as an append-only hook journal.

`PostToolUse` captures:

- failing test signatures
- compiler or build failures as failed approaches
- modified files from `Edit` and `Write`
- successful reruns as explicit decisions with rationale
- explicit “do not retry” style lines as pinned facts

`PreCompact` and `context-os resume` use the same renderer, so automatic recovery and manual fallback never drift.

### 2. Typed safe reducers

The reducer engine compresses noisy tool output conservatively:

- stack traces
- test logs
- build logs
- lint output
- JSON blobs
- config files

Safe mode preserves protected strings, commands, file paths, versions, and critical identifiers. Reducers fail open if they cannot reduce safely.

### 3. Repo memory

`context-os init` builds repo-memory artifacts and updates `CLAUDE.md` with a structural map so Claude spends less time rediscovering the repo.

### 4. Prompt linter

The prompt linter flags waste before it reaches Claude:

- redundant repeated constraints
- overbroad asks
- missing file scope
- missing acceptance criteria

### 5. Local benchmarks

Claims are benchmark-backed and local:

- safe reducers: `python/evals/runners/safe_mode_runner.py`
- compaction survival: `python/evals/runners/compaction_survival_runner.py`

Current checked-in reports show:

- safe-mode reducers: **27.3% average estimated token reduction** across reducer fixtures with **100% protected-string recall**
- compaction survival: **2/2 passing cases**
- compaction survival gates: **100% retention** for pinned facts, current subtask, latest accepted decision, and modified files in the benchmark traces

## Install

### Claude Code plugin

```text
/plugin marketplace add sravan27/context-os
/plugin install context-os@context-os
```

### Binary

Install the `context-os` binary into your `PATH`.

```bash
# From source
cargo install --git https://github.com/sravan27/context-os --path apps/cli
```

Then initialize inside a project:

```bash
cd your-project
context-os init
context-os doctor
```

`init` will:

- build `.context-os/repo-memory`
- create or update `CLAUDE.md`
- create `.context-os/session.json`
- create `.context-os/journal.jsonl`
- install Claude Code hooks in `.claude/settings.local.json`
- add `.context-os/` to `.gitignore`

## Hook flow

Context OS currently uses these Claude Code hooks:

- `PreToolUse` for Bash wrapping
- `PostToolUse` for Bash/Edit/Write signal capture
- `PreCompact` for restart-packet injection
- `SessionStart` for automatic recovery with `context-os resume`
- `Stop` for human-readable handoff generation

It does **not** rely on `UserPromptSubmit` for the core value proposition.

## Demo workflow

The intended loop looks like this:

1. A test fails.
2. `PostToolUse` records the failing signature and failed approach.
3. You edit a file.
4. `PostToolUse` records the modified file.
5. The focused rerun passes.
6. `PostToolUse` records the validated decision.
7. Claude compacts or you start a new session.
8. `PreCompact` or `context-os resume` restores the restart packet with the objective, subtask, decisions, failed approaches, modified files, next actions, and pinned facts.

## CLI

| Command | Purpose |
| --- | --- |
| `context-os init` | Build repo memory, create local state, install Claude hooks |
| `context-os resume` | Print the deterministic restart packet used for compaction recovery |
| `context-os handoff` | Write a human-readable handoff note from the same underlying session state |
| `context-os doctor` | Verify hooks, binary, state files, restart packet generation, and benchmark reports |
| `context-os pipe` | Reduce stdin using auto-detected safe reducers |
| `context-os reduce` | Run a specific reducer against a file |
| `context-os estimate` | Estimate token count for a file |
| `context-os prompt-lint` | Analyze a prompt for waste patterns |
| `context-os index` | Build repo-memory artifacts |
| `context-os inspect` | Print repo architecture as JSON |
| `context-os session ...` | Update, compact, diff, import, or export structured session state |

## Safety model

- Safe mode is the default.
- Context OS does not silently rewrite user intent in the core recovery path.
- Code fences and shell commands are not rewritten in safe mode.
- File paths, versions, flags, and protected identifiers are preserved.
- Reducers fail open on errors.
- Transformations carry reasons and before/after token estimates.
- Token counts are estimates, not billing numbers.

## Limits and honesty

- This does **not** bypass Anthropic limits.
- It makes limits hurt less by preserving continuity and trimming obvious waste.
- Hook availability depends on Claude Code surfaces; `context-os resume` is the first-class fallback when automatic injection is unavailable.
- Repo memory is static between refreshes.
- The dashboard exists only as an early scaffold today.
- Response shaping is not implemented yet.

## Development

```bash
cargo test
python3 python/evals/runners/safe_mode_runner.py
python3 python/evals/runners/compaction_survival_runner.py
```

## License

MIT
