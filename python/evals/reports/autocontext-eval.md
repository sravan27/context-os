# auto_context eval

_Generated 2026-04-19T14:56:30+00:00 · K=3 · N=32 prompts across 3 fixtures_

## Aggregate (auto_context)

| Metric | Value |
|---|---|
| Precision@3 | **0.604** |
| Recall@3 | **0.599** |
| MRR | **0.938** |
| Coverage (non-empty) | 1.000 |

## Baseline vs auto_context (lift)

Baseline = naive filename substring match. Ranks files purely by how many prompt tokens appear in the filename — no graph, no import traversal, no hot-file boost. This is the floor any useful static RAG must clear.

| Fixture | Baseline P@3 | auto_context P@3 | Δ | Baseline MRR | auto_context MRR | Δ |
|---|---|---|---|---|---|---|
| python | 0.431 | 0.611 | **+0.181** | 0.583 | 0.958 | **+0.375** |
| typescript | 0.550 | 0.600 | **+0.050** | 0.600 | 0.900 | **+0.300** |
| rust | 0.500 | 0.600 | **+0.100** | 0.500 | 0.950 | **+0.450** |
| **aggregate** | **0.490** | **0.604** | **+0.115** | **0.562** | **0.938** | **+0.375** |

## Per-fixture (auto_context)

| Fixture | N | P@3 | R@3 | MRR | Coverage |
|---|---|---|---|---|---|
| python | 12 | 0.611 | 0.583 | 0.958 | 1.000 |
| typescript | 10 | 0.600 | 0.533 | 0.900 | 1.000 |
| rust | 10 | 0.600 | 0.683 | 0.950 | 1.000 |

## Per-prompt (auto_context)

### fixture: python

| id | P@K | R@K | RR | predicted (top-K) |
|---|---|---|---|---|
| login-rate-limit | 0.67 | 0.67 | 1.00 | `src/api/router.py`, `tests/test_login.py`, `src/auth/login.py` |
| hash-password-lookup | 1.00 | 0.50 | 1.00 | `src/utils/crypto.py` |
| session-ttl-config | 0.33 | 0.50 | 1.00 | `src/config/settings.py`, `src/db/models.py`, `src/auth/login.py` |
| queries-async | 0.67 | 0.67 | 1.00 | `src/db/queries.py`, `src/db/models.py`, `src/auth/login.py` |
| middleware-logging | 0.33 | 0.33 | 1.00 | `src/auth/middleware.py`, `src/db/models.py`, `src/api/router.py` |
| migrations-add-column | 0.50 | 0.50 | 0.50 | `tests/test_migrations.py`, `src/db/migrations.py` |
| router-new-endpoint | 0.33 | 0.50 | 1.00 | `src/api/router.py`, `src/db/models.py`, `src/auth/login.py` |
| email-on-signup | 0.50 | 0.50 | 1.00 | `src/utils/email.py`, `src/db/models.py` |
| db-connection-pool | 1.00 | 0.33 | 1.00 | `src/config/database.py` |
| rate-limit-config | 0.67 | 1.00 | 1.00 | `src/config/settings.py`, `src/api/rate_limit.py`, `src/config/database.py` |
| verify-password-bug | 1.00 | 0.50 | 1.00 | `src/utils/crypto.py` |
| settings-env-var | 0.33 | 1.00 | 1.00 | `src/config/settings.py`, `src/auth/session.py`, `src/db/migrations.py` |

### fixture: typescript

| id | P@K | R@K | RR | predicted (top-K) |
|---|---|---|---|---|
| ts-login-rate-limit | 0.67 | 0.67 | 1.00 | `src/server/router.ts`, `tests/login.test.ts`, `src/auth/login.ts` |
| ts-hash-password-lookup | 1.00 | 0.50 | 1.00 | `src/utils/crypto.ts` |
| ts-session-ttl | 0.33 | 0.50 | 1.00 | `src/config/settings.ts`, `src/auth/login.ts`, `src/auth/middleware.ts` |
| ts-find-user-async | 0.50 | 0.33 | 1.00 | `src/db/users.ts`, `src/utils/email.ts` |
| ts-middleware-logging | 0.67 | 0.67 | 1.00 | `src/auth/middleware.ts`, `src/utils/logging.ts`, `src/db/users.ts` |
| ts-migrations-add-column | 0.67 | 1.00 | 0.50 | `src/auth/login.ts`, `src/db/migrations.ts`, `src/db/users.ts` |
| ts-router-logout | 0.33 | 0.50 | 0.50 | `src/server/app.ts`, `src/server/router.ts`, `src/auth/login.ts` |
| ts-welcome-email | 0.50 | 0.50 | 1.00 | `src/utils/email.ts`, `src/db/users.ts` |
| ts-db-pool | 1.00 | 0.33 | 1.00 | `src/config/database.ts` |
| ts-app-bootstrap | 0.33 | 0.33 | 1.00 | `src/server/app.ts`, `src/auth/session.ts`, `src/db/migrations.ts` |

### fixture: rust

| id | P@K | R@K | RR | predicted (top-K) |
|---|---|---|---|---|
| rs-login-rate-limit | 0.67 | 0.67 | 1.00 | `src/api/router.rs`, `src/auth/mod.rs`, `src/api/rate_limit.rs` |
| rs-hash-password-lookup | 0.33 | 0.50 | 1.00 | `src/auth/login.rs`, `src/api/router.rs`, `src/auth/middleware.rs` |
| rs-session-ttl | 0.33 | 0.50 | 1.00 | `src/config/settings.rs`, `src/auth/mod.rs`, `src/auth/login.rs` |
| rs-find-user-async | 1.00 | 1.00 | 1.00 | `src/auth/login.rs`, `src/db/queries.rs`, `src/config/database.rs` |
| rs-middleware-logging | 0.67 | 0.67 | 1.00 | `src/auth/middleware.rs`, `src/utils/logging.rs`, `src/auth/mod.rs` |
| rs-migrations-add-column | 1.00 | 0.50 | 1.00 | `src/db/migrations.rs` |
| rs-router-logout | 0.33 | 0.50 | 1.00 | `src/api/router.rs`, `src/auth/mod.rs`, `src/auth/login.rs` |
| rs-welcome-email | 0.33 | 0.50 | 1.00 | `src/utils/email.rs`, `src/utils/mod.rs`, `src/db/models.rs` |
| rs-db-pool | 1.00 | 1.00 | 1.00 | `src/config/database.rs`, `src/db/migrations.rs`, `src/db/queries.rs` |
| rs-settings-env | 0.33 | 1.00 | 0.50 | `src/auth/session.rs`, `src/config/settings.rs`, `src/lib.rs` |

## Fixtures

Three parallel mini web-apps: `python`, `typescript`, `rust`. Each has the same module layout — auth/api/config/db/utils — with cross-module imports the graph builder must resolve per language. Ground truth hand-labeled: for each prompt, which files a competent engineer would open first.

Prompts: `python/evals/autocontext_prompts.json`. Runner: `python/evals/runners/autocontext_eval.py`.

Precision@K = fraction of top-K predicted files that are in expected.
Recall@K = fraction of expected files present in top-K predicted.
MRR = mean of 1/rank of first correct prediction (0 if none in top-K).
