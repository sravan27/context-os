# Multi-repo cross-generalization eval

Runs the dogfood methodology (auto_context + 5 lexical baselines) against three real OSS repos that are **not** in our fixture set. Prompts are hand-labeled, descriptive (most do not name the target file), and pinned to specific commits.

- Runner: `python/evals/runners/multi_repo_eval.py`
- Prompts: `python/evals/multi_repo_prompts/*.json`

## Summary

| Repo | Files | Symbols | Prompts | auto_context MRR | Best baseline | Δ MRR |
|---|---:|---:|---:|---:|---|---:|
| axios/axios | 214 | 100 | 12 | **0.382** | bm25-path (0.252) | **+0.130** |
| psf/requests | 36 | 205 | 12 | **0.750** | bm25-symbols (0.875) | **−0.125** |
| BurntSushi/ripgrep | 100 | 1686 | 12 | **0.503** | bm25-path (0.459) | **+0.044** |

**Weighted across 36 prompts / 3 repos — auto_context: MRR 0.545 · top-1 0.444 · P@3 0.236**

## axios/axios — 12 prompts

- Source root: `https://github.com/axios/axios.git` @ `afca61a070`
- Indexed 214 files, 100 symbols

| Method | MRR | Top-1 | P@3 | Coverage |
|---|---:|---:|---:|---:|
| **auto_context** | **0.382** | **0.250** | **0.167** | **1.000** |
| bm25-path | 0.252 | 0.083 | 0.111 | 1.000 |
| bm25-symbols | 0.226 | 0.083 | 0.083 | 1.000 |
| grep-count | 0.222 | 0.000 | 0.139 | 1.000 |
| naive-filename | 0.167 | 0.167 | 0.056 | 0.750 |
| random | 0.015 | 0.000 | 0.000 | 1.000 |

<details><summary>Per-prompt auto_context results</summary>

| Prompt | Expected | Predicted top-3 | RR |
|---|---|---|---:|
| manager that stores request and response interceptors and runs them in a chain | `lib/core/InterceptorManager.js` | `lib/core/InterceptorManager.js`, `tests/browser/interceptors.browser.test.js`, `tests/browser/requests.browser.test.js` | 1.000 |
| where is the function that actually sends the prepared request through the confi | `lib/core/dispatchRequest.js` | `lib/adapters/adapters.js`, `lib/adapters/fetch.js`, `lib/adapters/http.js` | 0.000 |
| adapter that uses Node http module to send requests | `lib/adapters/http.js` | `lib/adapters/http.js`, `tests/unit/adapters/http.test.js`, `lib/adapters/adapters.js` | 1.000 |
| adapter that uses XMLHttpRequest in the browser | `lib/adapters/xhr.js` | `lib/adapters/adapters.js`, `lib/adapters/fetch.js`, `lib/adapters/http.js` | 0.250 |
| adapter built on top of the fetch API | `lib/adapters/fetch.js` | `lib/adapters/fetch.js`, `lib/adapters/adapters.js`, `tests/unit/adapters/fetch.test.js` | 1.000 |
| the token-based request cancellation mechanism | `lib/cancel/CancelToken.js` | `tests/browser/requests.browser.test.js`, `lib/cancel/CancelToken.js`, `lib/core/dispatchRequest.js` | 0.500 |
| how are default config and per-request config merged | `lib/core/mergeConfig.js` | `lib/defaults/transitional.js`, `lib/defaults/index.js`, `tests/browser/defaults.browser.test.js` | 0.000 |
| the custom error class that carries request and response on failure | `lib/core/AxiosError.js` | `tests/browser/requests.browser.test.js`, `lib/cancel/CanceledError.js`, `lib/core/AxiosError.js` | 0.333 |
| the class that stores and normalizes HTTP headers | `lib/core/AxiosHeaders.js` | `lib/adapters/http.js`, `lib/core/AxiosHeaders.js`, `lib/helpers/HttpStatusCode.js` | 0.500 |
| helper that serializes a params object into a URL query string | `lib/helpers/buildURL.js` | `lib/helpers/AxiosURLSearchParams.js`, `lib/platform/browser/classes/URLSearchParams.js`, `lib/platform/node/classes/URLSearchParams.js` | 0.000 |
| combines baseURL and request URL into the final absolute URL | `lib/core/buildFullPath.js` | `lib/helpers/combineURLs.js`, `tests/browser/requests.browser.test.js`, `tests/unit/helpers/combineURLs.test.js` | 0.000 |
| resolves or rejects the promise based on the HTTP status code validator | `lib/core/settle.js` | `lib/helpers/validator.js`, `lib/helpers/HttpStatusCode.js`, `lib/adapters/http.js` | 0.000 |

</details>

## psf/requests — 12 prompts

- Source root: `https://github.com/psf/requests.git` @ `f43f750ee1`
- Indexed 36 files, 205 symbols

| Method | MRR | Top-1 | P@3 | Coverage |
|---|---:|---:|---:|---:|
| bm25-symbols | 0.875 | 0.833 | 0.375 | 1.000 |
| **auto_context** | **0.750** | **0.667** | **0.319** | **0.917** |
| grep-count | 0.458 | 0.250 | 0.236 | 1.000 |
| bm25-path | 0.250 | 0.250 | 0.250 | 0.333 |
| naive-filename | 0.250 | 0.250 | 0.250 | 0.333 |
| random | 0.070 | 0.000 | 0.000 | 1.000 |

<details><summary>Per-prompt auto_context results</summary>

| Prompt | Expected | Predicted top-3 | RR |
|---|---|---|---:|
| where is the top-level get/post/put/delete request function that users call | `src/requests/api.py` | `src/requests/api.py`, `src/requests/compat.py`, `src/requests/__version__.py` | 1.000 |
| how does it persist cookies and connection pools across calls in one session | `src/requests/sessions.py` | `src/requests/cookies.py`, `src/requests/sessions.py`, `src/requests/compat.py` | 0.500 |
| transport adapter that handles retries and connection pooling | `src/requests/adapters.py` | `src/requests/adapters.py`, `tests/test_adapters.py`, `tests/test_requests.py` | 1.000 |
| the PreparedRequest and Response classes and how the request body is prepared | `src/requests/models.py` | `src/requests/models.py`, `src/requests/api.py`, `src/requests/compat.py` | 1.000 |
| how are cookies stored and converted between jar formats | `src/requests/cookies.py` | `src/requests/cookies.py`, `src/requests/compat.py`, `tests/test_requests.py` | 1.000 |
| basic and digest authentication handlers | `src/requests/auth.py` | `src/requests/auth.py`, `tests/test_requests.py` | 1.000 |
| the hierarchy of exceptions like ConnectionError, Timeout, HTTPError | `src/requests/exceptions.py` | `src/requests/exceptions.py`, `src/requests/__init__.py`, `src/requests/models.py` | 1.000 |
| lookup table mapping HTTP status codes to their names | `src/requests/status_codes.py` | `src/requests/status_codes.py`, `src/requests/compat.py` | 1.000 |
| helpers for encoding URL parameters and handling unicode in headers | `src/requests/utils.py` | — | 0.000 |
| python 2 vs 3 compatibility shim | `src/requests/compat.py` | `src/requests/compat.py`, `tests/compat.py` | 1.000 |
| response hook dispatching mechanism | `src/requests/hooks.py` | `tests/test_hooks.py`, `src/requests/hooks.py`, `src/requests/models.py` | 0.500 |
| case-insensitive dict used to store HTTP headers | `src/requests/structures.py` | `src/requests/compat.py` | 0.000 |

</details>

## BurntSushi/ripgrep — 12 prompts

- Source root: `https://github.com/BurntSushi/ripgrep.git` @ `4519153e5e`
- Indexed 100 files, 1686 symbols

| Method | MRR | Top-1 | P@3 | Coverage |
|---|---:|---:|---:|---:|
| **auto_context** | **0.503** | **0.417** | **0.222** | **1.000** |
| bm25-path | 0.459 | 0.333 | 0.250 | 0.917 |
| naive-filename | 0.403 | 0.333 | 0.278 | 0.667 |
| grep-count | 0.313 | 0.167 | 0.111 | 1.000 |
| bm25-symbols | 0.282 | 0.083 | 0.167 | 1.000 |
| random | 0.028 | 0.000 | 0.000 | 1.000 |

<details><summary>Per-prompt auto_context results</summary>

| Prompt | Expected | Predicted top-3 | RR |
|---|---|---|---:|
| where is the main entry point that ripgrep starts from | `crates/core/main.rs` | `crates/core/main.rs`, `crates/grep/examples/simplegrep.rs`, `crates/ignore/examples/walk.rs` | 1.000 |
| parser and matcher for .gitignore-style patterns | `crates/ignore/src/gitignore.rs` | `crates/core/flags/parse.rs`, `crates/ignore/src/dir.rs`, `crates/pcre2/src/matcher.rs` | 0.000 |
| parallel directory walker that respects ignore rules | `crates/ignore/src/walk.rs` | `crates/ignore/src/dir.rs`, `crates/ignore/src/lib.rs`, `crates/ignore/src/walk.rs` | 0.333 |
| compiles glob expressions into a matcher | `crates/globset/src/glob.rs` | `crates/globset/src/glob.rs`, `crates/globset/src/lib.rs`, `crates/pcre2/src/matcher.rs` | 1.000 |
| buffered reader that yields lines for the searcher | `crates/searcher/src/line_buffer.rs` | `crates/searcher/src/lines.rs`, `crates/searcher/src/sink.rs`, `crates/core/search.rs` | 0.000 |
| printer that outputs matches with ANSI color codes | `crates/printer/src/color.rs`, `crates/printer/src/standard.rs` | `crates/printer/src/color.rs`, `crates/printer/src/lib.rs`, `crates/printer/src/stats.rs` | 1.000 |
| emits matches as JSON Lines for integration with other tools | `crates/printer/src/json.rs` | `crates/searcher/src/lines.rs`, `crates/printer/src/json.rs`, `crates/searcher/src/sink.rs` | 0.500 |
| how the regex matcher is configured with case sensitivity and word boundaries | `crates/regex/src/config.rs`, `crates/regex/src/matcher.rs` | `crates/regex/src/matcher.rs`, `crates/pcre2/src/matcher.rs`, `crates/regex/src/config.rs` | 1.000 |
| file-type detection that maps extensions to language names | `crates/ignore/src/types.rs`, `crates/ignore/src/default_types.rs` | `crates/ignore/src/types.rs`, `crates/core/flags/hiargs.rs`, `crates/ignore/src/dir.rs` | 1.000 |
| the trait that consumes matches produced by the searcher | `crates/searcher/src/sink.rs` | `crates/core/search.rs`, `crates/core/main.rs`, `crates/searcher/src/line_buffer.rs` | 0.000 |
| alternative regex backend using PCRE2 | `crates/pcre2/src/matcher.rs` | `crates/core/flags/defs.rs`, `crates/pcre2/src/error.rs`, `crates/regex/src/error.rs` | 0.200 |
| tracks match count, byte count, and line count statistics during a search | `crates/printer/src/stats.rs` | `crates/core/search.rs`, `crates/searcher/src/sink.rs`, `crates/searcher/src/lines.rs` | 0.000 |

</details>

## Weighted aggregate (across all 36 prompts)

| Method | Weighted MRR | Δ vs auto_context |
|---|---:|---:|
| **auto_context** | **0.545** |  |
| bm25-symbols | 0.461 | −0.084 |
| grep-count | 0.331 | −0.214 |
| bm25-path | 0.320 | −0.225 |
| naive-filename | 0.273 | −0.272 |
| random | 0.038 | −0.507 |

---

## Acceptance criterion (v2.8)

1. **Weighted-aggregate** auto_context MRR across all repos must exceed every lexical baseline's weighted aggregate.
2. **Per-repo**, auto_context MRR must beat the *average* of the five lexical baselines.

On a single repo where prompts use exact class names (e.g. `PreparedRequest`, `HTTPError` in psf/requests), `bm25-symbols` can match or exceed auto_context — the lexical-retrieval ceiling regime. We accept that loss honestly: aggregate quality is what matters for a ranker that ships across many repos.

This script exits non-zero if either check fails.
