# User Guide

## Current local workflow

- Use the CLI to inspect token estimates
- Run safe reducers on known noisy artifacts
- Lint long prompts before sending them to an agent
- Compile repo memory artifacts for repeated onboarding tasks
- Persist and compact structured session memory between turns
- Run local interception passes that update state and telemetry
- Initialize the local telemetry database
- Validate global or project config files against the typed config loader

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

## Interception example

```bash
cargo run -p context-os -- intercept request \
  --session-id demo-session \
  --input tests/fixtures/test-log-jest.txt \
  --mode safe \
  --session-state /tmp/context-os-session.json \
  --telemetry-db /tmp/context-os-telemetry.db
```
