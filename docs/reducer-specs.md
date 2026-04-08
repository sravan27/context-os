# Reducer Specs

## Modes

- `safe`: preserve protected strings, commands, file paths, versions, and code blocks
- `balanced`: allow more summarization while retaining high-signal entities
- `aggressive`: explicitly opt-in only after benchmark validation

## Implemented reducers in this checkpoint

- `stack_trace_reducer`
- `test_log_reducer`
- `build_log_reducer`
- `lint_output_reducer`
- `json_reducer`
- `config_reducer`

## Core reducer contract

Each reducer exposes:

- detection confidence
- token savings estimate
- reduction result with provenance
- human-readable explanation
- risk classification

## Safe-mode contract

- Never mutate fenced code blocks
- Never silently drop commands, file paths, or version strings
- Append protected-value blocks when summarization would otherwise omit them
- Fail open if parsing or transformation fails
