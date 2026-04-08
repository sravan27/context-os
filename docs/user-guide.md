# User Guide

## Current local workflow

- Run `context-os init` once per repo
- Let Claude Code hooks capture decisions, failures, and modified files while you work
- Use `context-os resume` if Claude compacts too aggressively or you need to start a new session
- Use `context-os handoff` when you want a human-readable recovery note
- Run safe reducers on known noisy artifacts
- Lint long prompts before sending them to Claude
- Compile repo memory artifacts for repeated onboarding tasks
- Validate config files and run local evals as needed

## Claude workflow example

```bash
context-os init
context-os doctor
```

Then work normally in Claude Code. If you need manual recovery:

```bash
context-os resume
context-os handoff
```

## Safe reducer example

```bash
cargo run -p context-os -- reduce \
  --kind stack-trace \
  --input examples/sample-logs/stack-trace-node.txt \
  --mode safe
```

## Project config example

Create `.context-os.json` in a project root or maintain a global config in `~/.context-os/config.json`.

## Prompt linter example

```bash
cargo run -p context-os -- prompt-lint \
  --input tests/fixtures/long-prompt.txt
```

## Repo memory example

```bash
cargo run -p context-os -- index \
  --root examples/sample-repos/mini-next \
  --out /tmp/context-os-mini-next-memory
```

## Session memory example

```bash
cp examples/sample-sessions/state.json /tmp/context-os-state.json
cargo run -p context-os -- session update \
  --state /tmp/context-os-state.json \
  --update examples/sample-sessions/update.json
```

## Restart packet example

```bash
cargo run -p context-os -- resume --root .
```
