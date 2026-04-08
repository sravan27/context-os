# STATUS

## Current direction

Context OS is being narrowed around one core promise:

**Claude limit resilience.**

The product now treats typed token reduction as supporting infrastructure for the main value:

- preserve the objective
- preserve the current subtask
- preserve validated decisions
- preserve failed approaches
- preserve modified files
- preserve next actions and pinned facts

through compaction and session resets.

## What works

- **Compaction-aware decision replay**
  - `.context-os/session.json` is the canonical structured session state
  - `.context-os/journal.jsonl` captures append-only hook events
  - `context-os resume` prints the deterministic restart packet
  - `PreCompact` and `resume` share the same renderer
- **Claude Code hook flow**
  - `context-os init` installs `PreToolUse`, `PostToolUse`, `PreCompact`, `SessionStart`, and `Stop`
  - `SessionStart` prefers `context-os resume` and falls back to `.context-os/handoff.md`
- **PostToolUse signal capture**
  - failing test signatures
  - failed approaches from compiler/build errors
  - modified files from `Edit` and `Write`
  - validated decisions after successful reruns
  - pinned “do not retry” style facts
- **Human-readable recovery**
  - `context-os handoff` writes a Markdown recovery note from the same underlying packet state
- **6 typed safe reducers**
  - stack traces
  - test logs
  - build logs
  - lint output
  - JSON
  - config files
- **Repo memory**
  - `context-os init` builds repo artifacts and updates `CLAUDE.md`
- **Prompt linter**
  - detects redundancy, overbreadth, missing scope, and missing acceptance criteria
- **Local telemetry foundation**
  - SQLite-backed, local-only
- **Benchmarks**
  - safe-mode reduction suite
  - compaction-survival suite
- **Doctor command**
  - checks binary visibility, hook registration, `.context-os` state files, restart packet rendering, and benchmark report pass/fail

## Verification

```text
cargo test: passing
safe_mode_runner: 7/7 cases passing, 27.3% avg reduction, 100% protected-string recall
compaction_survival_runner: 2/2 cases passing, 100% pinned-fact/current-subtask/latest-decision/modified-file retention in benchmark traces
```

## Known limitations

- Context OS does not bypass provider limits; it preserves continuity and reduces waste
- Hook support depends on Claude Code surfaces; `context-os resume` is the primary fallback
- Repo memory still goes stale between refreshes
- The dashboard is scaffolded but not wired to live telemetry yet
- Response shaping is still not implemented
- Session memory capture is heuristic and hook-driven, not semantic/LLM-based

## Next concrete steps

1. Harden Claude Code install and uninstall flows around the shipped hook set.
2. Add more compaction-survival fixtures and failure-mode evals.
3. Connect dashboard views to telemetry and benchmark reports.
4. Improve repo-memory freshness and incremental rebuild behavior.
5. Document demo workflows and limitations even more explicitly.
