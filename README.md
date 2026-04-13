# Context OS

[![CI](https://github.com/sravan27/context-os/actions/workflows/ci.yml/badge.svg)](https://github.com/sravan27/context-os/actions/workflows/ci.yml)

**Stop hitting Claude Code usage limits.** One command. Zero dependencies. Reversible.

```bash
cd your-project
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

Output:
```
context-os: scanning project...
  detected: node typescript
  found 12,847 files in noise directories:
    node_modules/ (12,431 files)
    dist/ (416 files)

  configuring optimizations...

  [1/4] created CLAUDE.md with response shaping
  [2/4] created .claudeignore (filtering 12,847 files)
  [3/4] hooks skipped (install binary for output compression + session memory)
  [4/4] created .gitignore

  ── impact ──────────────────────────────────────────

  .claudeignore: 12,847 noise files hidden (~2.5M tokens/search saved)
  CLAUDE.md:     response shaping active (40-65% output reduction)
```

Start a new Claude Code session. That's it.

## What it does

| Layer | File | Token impact |
|-------|------|-------------|
| **Response shaping** | `CLAUDE.md` | 40-65% fewer output tokens. Claude stops prefacing, recapping, and over-explaining. |
| **Noise filtering** | `.claudeignore` | Auto-detects `node_modules`, `dist`, `build`, etc. Prevents Claude from reading thousands of irrelevant files. |
| **Output compression** | `.claude/settings.local.json` | 27-70% reduction on test/build output via typed reducers. 50 passing tests become 1 line. |
| **Session memory** | hooks | Decisions survive compaction and session restarts. No re-explaining what you already tried. |

The first two layers work instantly with zero dependencies. The last two require the binary.

## With hooks (optional)

```bash
cargo install --git https://github.com/sravan27/context-os --path apps/cli
context-os init
```

Hooks are automatic — no action needed after install:

- **PreToolUse**: Wraps `cargo test`, `npm test`, `npx jest`, etc. (42 commands) through typed reducers. Errors fully preserved.
- **PostToolUse**: Captures test failures, compiler errors, file modifications into structured session state.
- **PreCompact**: Injects restart packet before compaction so Claude remembers what worked and what failed.
- **SessionStart**: Restores session state when starting a new conversation.
- **Stop**: Writes human-readable handoff for manual recovery.

## Uninstall

Fully reversible. Preserves your existing CLAUDE.md content.

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --uninstall
```

## Measured results

- 71% reduction on 50-test cargo output (48 passing tests collapsed, 2 failures preserved)
- 100% protected string recall (no errors, paths, or versions dropped)
- 5/5 concurrent PostToolUse writes captured (lockfile prevents race conditions)
- Full fail-edit-pass cycle: decisions survive compaction with rationale
- 42 command patterns matched including `cd /path && RUST_BACKTRACE=1 cargo test`

## Verify your setup

```bash
context-os doctor
```

## Limits

- Does not bypass Anthropic usage limits. Makes them hurt less.
- Response shaping effectiveness varies by task type (13-21% on structured code, 40-65% on explanations).
- Hook availability depends on Claude Code surfaces.

## Development

```bash
cargo test
python3 python/evals/runners/safe_mode_runner.py
python3 python/evals/runners/compaction_survival_runner.py
```

## License

MIT
