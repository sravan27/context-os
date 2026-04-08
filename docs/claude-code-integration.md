# Claude Code Integration

## Supported path today

Context OS currently ships a **hook-based Claude Code integration** with a local sidecar binary.

The install path is:

1. install the `context-os` binary locally
2. run `context-os init` in the project root
3. let Context OS write `.claude/settings.local.json`

## Installed hooks

`context-os init` installs:

- `PreToolUse`
- `PostToolUse`
- `PreCompact`
- `SessionStart`
- `Stop`

Context OS does **not** rely on `UserPromptSubmit` for its main value proposition.

## Hook behavior

### `PreToolUse`

- matches `Bash`
- wraps noisy test/build/lint commands through `context-os pipe`
- preserves the original command exit code

### `PostToolUse`

- matches `Bash`, `Edit`, and `Write`
- updates `.context-os/session.json`
- appends hook events to `.context-os/journal.jsonl`
- records:
  - failing signatures
  - failed approaches
  - modified files
  - validated decisions
  - pinned “do not retry” facts

### `PreCompact`

- renders the deterministic restart packet
- emits the same packet as `context-os resume`
- exists to preserve the plan, decisions, and file state through Claude compaction

### `SessionStart`

- first tries `context-os resume`
- falls back to `.context-os/handoff.md`

### `Stop`

- writes a human-readable handoff note with git state plus the same underlying recovery state

## State files

Context OS currently uses:

- `.context-os/session.json`
- `.context-os/journal.jsonl`
- `.context-os/handoff.md`
- `.context-os/repo-memory/`

`session.json` is the canonical structured state. `handoff.md` is the human-readable recovery view.

## Operational commands

- `context-os init`
- `context-os resume`
- `context-os handoff`
- `context-os doctor`

## Doctor checks

`context-os doctor` verifies:

- the running binary path
- git repository presence
- `.context-os/`
- `CLAUDE.md`
- hook registration
- `.gitignore`
- `session.json`
- `journal.jsonl`
- restart packet generation
- benchmark report pass/fail

## Known limitations

- Context OS does not bypass Anthropic limits
- recovery depends on the hook surfaces Claude Code exposes
- if `PreCompact` is unavailable or changes, `context-os resume` is the fallback path
- the plugin metadata and CLI are Claude-first today; broader agent support is future work

## Honest boundary

This integration improves continuity and reduces wasted context. It does not claim to change provider billing, unlock hidden limits, or silently rewrite user intent.
