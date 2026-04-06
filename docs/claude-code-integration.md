# Claude Code Integration

## Intended support paths

1. Local proxy path for Anthropic-compatible request forwarding
2. Hook-based integration fallback
3. Plugin-assisted UX where Claude Code surfaces permit it

## Current checkpoint

This repository currently provides:

- a reducer and telemetry foundation
- a prompt-linter and repo-memory CLI surface that future hooks can call
- a local interception pipeline the Claude Code integration can delegate to
- CLI primitives that future Claude Code hooks can call
- plugin scaffolding under `apps/plugin-claude`

## Integration notes to document fully in later phases

- install and uninstall flow
- doctor command
- debug logging
- interactions with `/clear`, `/compact`, `/context`, `/cost`, hooks, `CLAUDE.md`, and skills

## Honesty note

Any Claude Code limitation discovered during implementation will be documented explicitly rather than worked around with hidden behavior.
