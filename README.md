# Context OS

[![CI](https://github.com/sravan27/context-os/actions/workflows/ci.yml/badge.svg)](https://github.com/sravan27/context-os/actions/workflows/ci.yml)

**Make Claude Code use fewer tokens per task.** One command. No dependencies.

```bash
cd your-project
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

That's it. Start a new Claude Code session. Claude will be terser, skip noise dirs, and stop wasting tokens on verbose output.

For automatic test/build output reduction (hooks), install the full binary:

```bash
cargo install --git https://github.com/sravan27/context-os --path apps/cli
context-os init
```

## What it does

`context-os init` generates three files:

| File | What it does | Token impact |
|------|-------------|-------------|
| `CLAUDE.md` | Response shaping (be terse), repo map, session continuity | ~165 tokens/turn input, saves 40-65% output tokens |
| `.claudeignore` | Auto-detects `node_modules`, `dist`, `build`, etc. | Prevents Claude from searching noise dirs |
| `.claude/settings.local.json` | 5 hooks for automatic optimization | Reduces test/build output 27-70%, preserves decisions through compaction |

### The hooks (automatic, no action needed)

- **PreToolUse**: Wraps `cargo test`, `npm test`, `npx jest`, etc. (42 commands) — pipes output through typed reducers. 50 passing tests become 1 line. Errors fully preserved.
- **PostToolUse**: Captures test failures, compiler errors, file modifications, validated decisions into structured session state.
- **PreCompact**: Before Claude compacts, injects a restart packet so it remembers what worked, what failed, and why.
- **SessionStart**: Restores session state when starting a new conversation.
- **Stop**: Writes a human-readable handoff for manual recovery.

### Without hooks (CLAUDE.md only)

```bash
context-os init --no-hooks
```

Generates just `CLAUDE.md` and `.claudeignore`. No binary needed after init. No background processes.

## Does it actually work?

Measured:

- 71% reduction on 50-test cargo output (48 passing tests collapsed, 2 failures preserved)
- 100% protected string recall (no errors, paths, or versions dropped)
- 5/5 concurrent PostToolUse writes captured (lockfile prevents race conditions)
- Full fail-edit-pass cycle: decisions survive compaction with rationale
- Binary stdin passthrough (no crashes on non-UTF-8 output)
- 42 command patterns matched including `cd /path && RUST_BACKTRACE=1 cargo test`

Benchmarks: `cargo test` (35 tests), `python3 python/evals/runners/safe_mode_runner.py` (7/7), `python3 python/evals/runners/compaction_survival_runner.py` (2/2).

## Verify your setup

```bash
context-os doctor
```

## Limits

- Does not bypass Anthropic usage limits. Makes them hurt less.
- Hook availability depends on Claude Code surfaces.
- Repo memory is static between `context-os init` refreshes.
- Response shaping effectiveness varies by task type (13-21% on structured code, 40-65% on explanations).

## Development

```bash
cargo test
python3 python/evals/runners/safe_mode_runner.py
python3 python/evals/runners/compaction_survival_runner.py
```

## License

MIT
