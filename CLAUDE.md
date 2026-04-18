<!-- context-os:start -->
# Response rules

- Ultra-concise. No preamble, recap, or filler.
- Code > explanation. Show diff, not rationale.
- 1-2 sentence plan then execute. No pre-explanation.
- Fragments ok. Drop articles. Be direct.
- NEVER announce tool calls. Just call them.
- NEVER repeat what the user said back to them.
- If fixing a bug, show only the fix. Skip root-cause unless asked.
- Prefer Edit over Write. Diffs use fewer tokens than full files.
- Skip imports in code snippets unless they're the change.
- On success: state what was done in ≤1 sentence. No celebration.

# Repo rules

- Read only files you will change.
- Batch edits: one response, multiple files.
- On errors: show error only. Skip passing output.
- Run tests once to verify, not to explore.
- Use Grep/Glob tools over shell find/grep — they're cheaper.
- Read files with offset+limit when you only need part.
- For broad exploration, delegate to the `explorer` subagent (runs on Haiku, 15x cheaper).

- `cargo check` is faster than `cargo build` for type errors.
- Use `cargo test -p <crate>` to target one crate, not the whole workspace.

# Project structure

```
.claude-plugin/
.github/
Formula/ (1 files)
apps/ (2 files) — cli plugin-claude 
bin/
commands/
crates/ (8 files) — config prompt-linter proxy-core reducer-engine repo-memory session-memory telemetry token-estimator 
docs/
examples/ (2 files) — sample-configs sample-logs sample-repos sample-sessions stacks 
hooks/
python/ (8 files) — __pycache__ evals scripts 
schemas/
scripts/
skills/
tests/
```

# Session continuity

If a restart packet or `.context-os/handoff.md` exists, read it first.
Resume from there. Don't re-attempt failed approaches.
Use `/compact` before context fills up to save state.

# Token guards (hooks — installed at .claude/hooks/)

- `dedup_guard.py` blocks duplicate Read/Glob/Grep within 10min — if you see
  "[context-os] Skipping duplicate", use the previous result from history,
  don't re-Read.
- `loop_guard.py` warns at edit #5 / blocks at edit #8 on the same file. If it
  warns, stop editing and re-read the full file or run tests to see real errors.
- `session_profile.py` writes a Stop-time report to `.context-os/session-reports/`.
  Check it after long sessions to see where tokens went.
<!-- context-os:end -->
