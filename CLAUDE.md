<!-- context-os:start -->
# Response rules

- Ultra-concise. No preamble, no recap, no filler.
- Code > explanation. Show the diff, not why you chose it.
- 1-2 sentence plan, then execute. Never explain what you're about to do.
- If asked to explain, use fragments. Drop articles. Be direct.

# Repo rules

- Use the map below. Don't explore or scan.
- Read only files you'll change.
- Batch edits. One response, multiple files.
- On errors, show only the error. Skip passing output.

# Session continuity

If a restart packet or `.context-os/handoff.md` exists, read it first. Resume from there. Don't re-attempt failed approaches.

# Repo map

**rust-workspace** | 32 source files | 44 configs | dirs: .claude, .claude-plugin, .context-os, .github, apps, bin, commands, crates, docs, examples, hooks, python, schemas, scripts, skills, tests

## Source

**apps/**: 4 files, entry: apps/cli/src/main.rs
**crates/**: 14 files, entry: crates/config/src/lib.rs, crates/prompt-linter/src/lib.rs, crates/proxy-core/src/lib.rs, crates/reducer-engine/src/lib.rs, crates/repo-memory/src/lib.rs, crates/session-memory/src/lib.rs, crates/telemetry/src/lib.rs, crates/token-estimator/src/lib.rs
**examples/**: 5 files
**python/**: 5 files
**tests**: 1 test files (not listed, find by convention)

## Components

App, NavBar

## Key dependencies

anyhow@1.0, clap@{ features = [derive], version = 4.5 }, regex@1.11, rusqlite@{ features = [bundled], version = 0.31 }, serde@{ features = [derive], version = 1.0 }, serde_json@1.0, serde_yaml@0.9, tempfile@3.15, thiserror@2.0, toml@0.8
<!-- context-os:end -->
