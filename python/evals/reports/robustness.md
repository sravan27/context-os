# auto_context robustness tests

_Generated 2026-04-21T14:05:06+00:00 · 18/18 cases pass_

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
| 1 | `empty-dir` | ✓ | 0 | 22.1ms | — |
| 2 | `no-graph` | ✓ | 0 | 21.1ms | — |
| 3 | `corrupt-json` | ✓ | 0 | 23.2ms | — |
| 4 | `empty-graph` | ✓ | 0 | 20.9ms | — |
| 5 | `partial-graph` | ✓ | 0 | 21.3ms | — |
| 6 | `unicode-paths` | ✓ | 0 | 21.6ms | — |
| 7 | `huge-graph` | ✓ | 0 | 87.7ms | — |
| 8 | `empty-prompt` | ✓ | 0 | 42.5ms | — |
| 9 | `whitespace-prompt` | ✓ | 0 | 21.8ms | — |
| 10 | `mega-prompt` | ✓ | 0 | 22.6ms | — |
| 11 | `adversarial-regex` | ✓ | 0 | 21.1ms | — |
| 12 | `null-bytes-prompt` | ✓ | 0 | 20.9ms | — |
| 13 | `unicode-prompt` | ✓ | 0 | 20.6ms | — |
| 14 | `path-injection` | ✓ | 0 | 21.4ms | — |
| 15 | `ablate-all` | ✓ | 0 | 21.7ms | — |
| 16 | `disabled` | ✓ | 0 | 20.6ms | — |
| 17 | `stdin-not-json` | ✓ | 0 | 21.4ms | — |
| 18 | `stdin-empty` | ✓ | 0 | 20.7ms | — |

## Case details

### `empty-dir`

Hook invoked in an empty directory with no graph and no source.

- Status: pass
- Exit: 0
- Elapsed: 22.1ms

### `no-graph`

Source files exist but `.context-os/repo-graph.json` is missing.

- Status: pass
- Exit: 0
- Elapsed: 21.1ms

### `corrupt-json`

`.context-os/repo-graph.json` is present but contains invalid JSON.

- Status: pass
- Exit: 0
- Elapsed: 23.2ms

### `empty-graph`

Graph JSON parses but is an empty object `{}`.

- Status: pass
- Exit: 0
- Elapsed: 20.9ms

### `partial-graph`

Graph has only `files`, missing `symbol_index`/`imported_by`/`hot_files`.

- Status: pass
- Exit: 0
- Elapsed: 21.3ms

### `unicode-paths`

Graph has unicode file paths, symbols with accents, emoji modules.

- Status: pass
- Exit: 0
- Elapsed: 21.6ms

### `huge-graph`

Graph with 5,000 files and 5,000 symbols. Latency SLA applies.

- Status: pass
- Exit: 0
- Elapsed: 87.7ms
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
- Elapsed: 42.5ms

### `whitespace-prompt`

Prompt is pure whitespace.

- Status: pass
- Exit: 0
- Elapsed: 21.8ms

### `mega-prompt`

Prompt is 100,000 characters long.

- Status: pass
- Exit: 0
- Elapsed: 22.6ms

### `adversarial-regex`

Prompt contains regex metacharacters and long backslash sequences.

- Status: pass
- Exit: 0
- Elapsed: 21.1ms

### `null-bytes-prompt`

Prompt contains NUL bytes and control chars.

- Status: pass
- Exit: 0
- Elapsed: 20.9ms

### `unicode-prompt`

Prompt is in multiple languages and emoji.

- Status: pass
- Exit: 0
- Elapsed: 20.6ms
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
- Elapsed: 21.4ms

### `ablate-all`

All 8 ranker signals disabled via env var. Should still exit clean.

- Status: pass
- Exit: 0
- Elapsed: 21.7ms

### `disabled`

`CONTEXT_OS_AUTOCONTEXT=0` → hook must exit silently.

- Status: pass
- Exit: 0
- Elapsed: 20.6ms

### `stdin-not-json`

Hook invoked with non-JSON stdin.

- Status: pass
- Exit: 0
- Elapsed: 21.4ms

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
