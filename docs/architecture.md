# Architecture

## Pipeline

```text
[agent workflow]
      |
      v
[integration layer or proxy]
      |
      v
[classifier]
      +--> [repo memory]
      +--> [typed reducers]
      +--> [prompt linter]
      +--> [session memory]
      +--> [telemetry]
      |
      v
[upstream endpoint]
      |
      v
[optional response shaper]
```

## Design principles

- Local-first by default
- Fail open on reducer or integration errors
- Deterministic transform ordering
- Explicit provenance for every transformation
- Benchmark gates for any lossy mode

## Current implementation scope

- Rust workspace foundations
- Typed reducer abstraction
- Safe-mode reducers for high-waste text classes
- Prompt-linter heuristics with structured rewrite suggestions
- Repo-memory compiler with deterministic JSON and Markdown artifact output
- Structured session-memory with file-backed state and compaction/diff flows
- Local proxy interception orchestration with reducer application, prompt linting, session-memory attachment, and telemetry writes
- Config schema and merge model
- Local SQLite telemetry schema
