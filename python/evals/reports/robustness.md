# auto_context robustness tests

_Generated 2026-04-22T13:47:28+00:00 · 18/18 cases pass_

## Why this exists

The hook runs on every prompt. Any crash, stderr spew, or non-zero
exit is user-visible noise. This suite throws pathological inputs
at the hook and asserts:

1. Exit code = 0 (fail-open).
2. stdout is empty or a well-formed `<context-os:autocontext>` block.
3. No Python tracebacks on stderr.
4. Wall time under 1 second per invocation.

## Results

| # | case | status | exit | elapsed | stderr |
|---|---|:---:|---:|---:|---|
| 1 | `empty-dir` | ✓ | 0 | 20.7ms | — |
| 2 | `no-graph` | ✓ | 0 | 21.1ms | — |
| 3 | `corrupt-json` | ✓ | 0 | 21.1ms | — |
| 4 | `empty-graph` | ✓ | 0 | 21.3ms | — |
| 5 | `partial-graph` | ✓ | 0 | 20.1ms | — |
| 6 | `unicode-paths` | ✓ | 0 | 21.5ms | — |
| 7 | `huge-graph` | ✓ | 0 | 68.3ms | — |
| 8 | `empty-prompt` | ✓ | 0 | 21.1ms | — |
| 9 | `whitespace-prompt` | ✓ | 0 | 20.6ms | — |
| 10 | `mega-prompt` | ✓ | 0 | 21.3ms | — |
| 11 | `adversarial-regex` | ✓ | 0 | 21.0ms | — |
| 12 | `null-bytes-prompt` | ✓ | 0 | 20.9ms | — |
| 13 | `unicode-prompt` | ✓ | 0 | 21.3ms | — |
| 14 | `path-injection` | ✓ | 0 | 20.9ms | — |
| 15 | `ablate-all` | ✓ | 0 | 20.5ms | — |
| 16 | `disabled` | ✓ | 0 | 20.9ms | — |
| 17 | `stdin-not-json` | ✓ | 0 | 20.6ms | — |
| 18 | `stdin-empty` | ✓ | 0 | 20.7ms | — |

## Case details

### `empty-dir`

Hook invoked in an empty directory with no graph and no source.

- Status: pass
- Exit: 0
- Elapsed: 20.7ms

### `no-graph`

Source files exist but `.context-os/repo-graph.json` is missing.

- Status: pass
- Exit: 0
- Elapsed: 21.1ms

### `corrupt-json`

`.context-os/repo-graph.json` is present but contains invalid JSON.

- Status: pass
- Exit: 0
- Elapsed: 21.1ms

### `empty-graph`

Graph JSON parses but is an empty object `{}`.

- Status: pass
- Exit: 0
- Elapsed: 21.3ms

### `partial-graph`

Graph has only `files`, missing `symbol_index`/`imported_by`/`hot_files`.

- Status: pass
- Exit: 0
- Elapsed: 20.1ms

### `unicode-paths`

Graph has unicode file paths, symbols with accents, emoji modules.

- Status: pass
- Exit: 0
- Elapsed: 21.5ms

### `huge-graph`

Graph with 5,000 files and 5,000 symbols. Latency SLA applies.

- Status: pass
- Exit: 0
- Elapsed: 68.3ms
- stdout (first 200 chars):

  ```
  <context-os:autocontext>
  Graph-matched candidates (structure only, no files read yet):
  - `src/pkg12/mod_01234.py` · fn_1234 (function)
  Verify before reading. `/find <symbol>` · `/deps <file>` fo
  ```

### `empty-prompt`

Prompt is the empty string.

- Status: pass
- Exit: 0
- Elapsed: 21.1ms

### `whitespace-prompt`

Prompt is pure whitespace.

- Status: pass
- Exit: 0
- Elapsed: 20.6ms

### `mega-prompt`

Prompt is 100,000 characters long.

- Status: pass
- Exit: 0
- Elapsed: 21.3ms

### `adversarial-regex`

Prompt contains regex metacharacters and long backslash sequences.

- Status: pass
- Exit: 0
- Elapsed: 21.0ms

### `null-bytes-prompt`

Prompt contains NUL bytes and control chars.

- Status: pass
- Exit: 0
- Elapsed: 20.9ms

### `unicode-prompt`

Prompt is in multiple languages and emoji.

- Status: pass
- Exit: 0
- Elapsed: 21.3ms
- stdout (first 200 chars):

  ```
  <context-os:autocontext>
  Graph-matched candidates (structure only, no files read yet):
  - `src/münchen_café.py` · imports: 🚀.rocket
  Verify before reading. `/find <symbol>` · `/deps <file>` for mo
  ```

### `path-injection`

Prompt contains shell metacharacters that must not be expanded.

- Status: pass
- Exit: 0
- Elapsed: 20.9ms

### `ablate-all`

All 8 ranker signals disabled via env var. Should still exit clean.

- Status: pass
- Exit: 0
- Elapsed: 20.5ms

### `disabled`

`CONTEXT_OS_AUTOCONTEXT=0` → hook must exit silently.

- Status: pass
- Exit: 0
- Elapsed: 20.9ms

### `stdin-not-json`

Hook invoked with non-JSON stdin.

- Status: pass
- Exit: 0
- Elapsed: 20.6ms

### `stdin-empty`

Hook invoked with completely empty stdin.

- Status: pass
- Exit: 0
- Elapsed: 20.7ms

## Reproduce

```bash
python3 python/evals/runners/robustness_test.py
```

Non-zero exit if any case fails.
