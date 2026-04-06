# STATUS

## What works

- **5 typed reducers**: stack traces (42% reduction), test logs (36%), build logs (~40%), JSON (13%), config (13%)
- **100% protected string recall** in safe mode across all benchmarks
- **Claude Code integration**: `context-os init` installs SessionStart + UserPromptSubmit + Stop hooks
- **Session continuity**: auto-handoff with git state (branch, diff, uncommitted files, recent commits)
- **Per-turn context injection**: `context-os status` runs on every UserPromptSubmit
- **Repo memory**: scans repo, generates CLAUDE.md with behavioral rules and structural map
- **Session memory**: structured state with objectives, decisions, failures, pinned facts, compaction
- **Prompt linter**: detects 6 waste patterns with structured rewrite suggestions
- **Local telemetry**: SQLite-backed, never leaves the machine
- **Benchmarks**: 5/5 gates passing, Python eval runners with JSON + Markdown reports
- **Doctor command**: validates setup, runs quick benchmark, shows status

## Verification

```
cargo test: 26+ tests passing
safe_mode_runner: 5/5 cases, 26.1% avg reduction, 100% recall
```

## Known limitations

- Token estimates are heuristic, not provider billing numbers
- Safe mode is conservative — prefers recall over compression
- Repo memory goes stale between `init` runs (no file watcher)
- Session compaction is lossy (3 recent turns, 5 failures retained)
- No dashboard UI yet (React scaffold exists)
- No response shaping yet (only request-side reduction)

## Architecture

8 Rust crates + CLI app + Python eval suite. Single binary, no runtime dependencies, no network calls.
