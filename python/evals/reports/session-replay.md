# Session-replay token savings

_Generated 2026-04-19T14:56:31+00:00 · N=32 prompts across 3 fixtures_

## What this measures

Tokens Claude would burn on the "find + read" portion of each task, with vs without `auto_context`. Deterministic simulator — no live model calls — so the numbers are reproducible in CI.

### Cost model

- Glob call result: 200 tok (fixed)
- Grep call result: 500 tok (fixed)
- File read: file line count × 8 tok/line
- auto_context block: exact token count of the emitted block (whitespace-split × 1.3)

### Strategies

- **without**: Glob + Grep, then read files in naive-filename match order until the first ground-truth file is read.
- **with**: emit `auto_context` block, read files in predicted order until the first ground-truth file is read. If all top-K miss, fall back to the naive flow (paying Glob+Grep then).

## Aggregate

| Metric | Value |
|---|---|
| Total tokens (without) | **34,944** |
| Total tokens (with auto_context) | **6,908** |
| Total savings | **28,036 tok (80.2%)** |
| Median tokens (without) | 876 |
| Median tokens (with) | 210 |
| Median savings per prompt | **78.0%** |
| Mean auto_context block cost | 56 tok |
| Prompts where with < without | **32/32** |
| Prompts answered on first read (with) | **28/32** |

## Per-prompt

| fixture | id | without (tok, reads) | with (tok, reads) | savings |
|---|---|---|---|---|
| python | login-rate-limit | 844 (1) | 268 (1) | **+576 (+68.2%)** |
| python | hash-password-lookup | 1,236 (3) | 184 (1) | **+1,052 (+85.1%)** |
| python | session-ttl-config | 876 (1) | 242 (1) | **+634 (+72.4%)** |
| python | queries-async | 828 (1) | 195 (1) | **+633 (+76.4%)** |
| python | middleware-logging | 828 (1) | 189 (1) | **+639 (+77.2%)** |
| python | migrations-add-column | 876 (1) | 249 (2) | **+627 (+71.6%)** |
| python | router-new-endpoint | 876 (1) | 284 (1) | **+592 (+67.6%)** |
| python | email-on-signup | 876 (1) | 220 (1) | **+656 (+74.9%)** |
| python | db-connection-pool | 1,364 (4) | 143 (1) | **+1,221 (+89.5%)** |
| python | rate-limit-config | 908 (1) | 242 (1) | **+666 (+73.3%)** |
| python | verify-password-bug | 1,236 (3) | 184 (1) | **+1,052 (+85.1%)** |
| python | settings-env-var | 3,028 (16) | 241 (1) | **+2,787 (+92.0%)** |
| typescript | ts-login-rate-limit | 852 (1) | 249 (1) | **+603 (+70.8%)** |
| typescript | ts-hash-password-lookup | 1,020 (2) | 167 (1) | **+853 (+83.6%)** |
| typescript | ts-session-ttl | 828 (1) | 170 (1) | **+658 (+79.5%)** |
| typescript | ts-find-user-async | 868 (1) | 220 (1) | **+648 (+74.7%)** |
| typescript | ts-middleware-logging | 1,412 (5) | 193 (1) | **+1,219 (+86.3%)** |
| typescript | ts-migrations-add-column | 868 (1) | 296 (2) | **+572 (+65.9%)** |
| typescript | ts-router-logout | 828 (1) | 409 (2) | **+419 (+50.6%)** |
| typescript | ts-welcome-email | 804 (1) | 152 (1) | **+652 (+81.1%)** |
| typescript | ts-db-pool | 868 (1) | 121 (1) | **+747 (+86.1%)** |
| typescript | ts-app-bootstrap | 884 (1) | 227 (1) | **+657 (+74.3%)** |
| rust | rs-login-rate-limit | 932 (1) | 225 (1) | **+707 (+75.9%)** |
| rust | rs-hash-password-lookup | 1,276 (8) | 205 (1) | **+1,071 (+83.9%)** |
| rust | rs-session-ttl | 908 (1) | 165 (1) | **+743 (+81.8%)** |
| rust | rs-find-user-async | 1,420 (9) | 210 (1) | **+1,210 (+85.2%)** |
| rust | rs-middleware-logging | 812 (1) | 179 (1) | **+633 (+78.0%)** |
| rust | rs-migrations-add-column | 940 (5) | 123 (1) | **+817 (+86.9%)** |
| rust | rs-router-logout | 868 (1) | 235 (1) | **+633 (+72.9%)** |
| rust | rs-welcome-email | 844 (1) | 198 (1) | **+646 (+76.5%)** |
| rust | rs-db-pool | 1,428 (10) | 150 (1) | **+1,278 (+89.5%)** |
| rust | rs-settings-env | 2,508 (19) | 373 (2) | **+2,135 (+85.1%)** |

## Caveats

- Simulated reads consume the whole file (matches current Claude Read default).
- Fixtures are small — absolute numbers are smaller than real repos, but the relative gap is the point.
- Worst case counted assumes Claude eventually reads every fixture file; in practice it would stop sooner.
