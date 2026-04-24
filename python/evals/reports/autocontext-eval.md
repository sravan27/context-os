# auto_context eval

_Generated 2026-04-22T13:47:27+00:00 · K=3 · N=32 prompts across 3 fixtures_

## Aggregate (auto_context)

| Metric | Value |
|---|---|
| Precision@3 | **0.703** |
| Recall@3 | **0.682** |
| MRR | **0.969** |
| Coverage (non-empty) | 1.000 |

## Per-fixture (auto_context)

| Fixture | N | P@3 | R@3 | MRR | Coverage |
|---|---|---|---|---|---|
| python | 12 | 0.708 | 0.694 | 1.000 | 1.000 |
| typescript | 10 | 0.733 | 0.700 | 0.950 | 1.000 |
| rust | 10 | 0.667 | 0.650 | 0.950 | 1.000 |

## Per-prompt (auto_context)

### fixture: python

| id | P@K | R@K | RR | predicted (top-K) |
|---|---|---|---|---|
| login-rate-limit | 1.00 | 1.00 | 1.00 | `src/api/rate_limit.py`, `src/auth/login.py`, `src/api/router.py` |
| hash-password-lookup | 1.00 | 0.50 | 1.00 | `src/utils/crypto.py` |
| session-ttl-config | 0.67 | 1.00 | 1.00 | `src/auth/session.py`, `src/config/settings.py`, `src/db/models.py` |
| queries-async | 0.67 | 0.67 | 1.00 | `src/db/queries.py`, `src/config/database.py`, `src/utils/email.py` |
| middleware-logging | 0.33 | 0.33 | 1.00 | `src/auth/middleware.py`, `src/db/models.py`, `src/api/router.py` |
| migrations-add-column | 0.50 | 0.50 | 1.00 | `src/db/migrations.py`, `tests/test_migrations.py` |
| router-new-endpoint | 0.67 | 1.00 | 1.00 | `src/auth/session.py`, `src/api/router.py`, `src/db/models.py` |
| email-on-signup | 0.50 | 0.50 | 1.00 | `src/utils/email.py`, `src/db/models.py` |
| db-connection-pool | 1.00 | 0.33 | 1.00 | `src/config/database.py` |
| rate-limit-config | 0.67 | 1.00 | 1.00 | `src/api/rate_limit.py`, `src/config/settings.py`, `tests/test_rate_limit.py` |
| verify-password-bug | 1.00 | 0.50 | 1.00 | `src/utils/crypto.py` |
| settings-env-var | 0.50 | 1.00 | 1.00 | `src/config/settings.py`, `src/config/database.py` |

### fixture: typescript

| id | P@K | R@K | RR | predicted (top-K) |
|---|---|---|---|---|
| ts-login-rate-limit | 1.00 | 1.00 | 1.00 | `src/auth/login.ts`, `src/server/router.ts`, `src/api/rateLimit.ts` |
| ts-hash-password-lookup | 1.00 | 0.50 | 1.00 | `src/utils/crypto.ts` |
| ts-session-ttl | 0.67 | 1.00 | 1.00 | `src/auth/session.ts`, `src/config/settings.ts`, `src/auth/login.ts` |
| ts-find-user-async | 0.50 | 0.33 | 0.50 | `src/utils/email.ts`, `src/db/users.ts` |
| ts-middleware-logging | 0.67 | 0.67 | 1.00 | `src/auth/middleware.ts`, `src/utils/logging.ts`, `src/db/users.ts` |
| ts-migrations-add-column | 0.67 | 1.00 | 1.00 | `src/db/users.ts`, `src/auth/login.ts`, `src/db/migrations.ts` |
| ts-router-logout | 0.67 | 1.00 | 1.00 | `src/server/router.ts`, `src/auth/session.ts`, `src/auth/login.ts` |
| ts-welcome-email | 0.50 | 0.50 | 1.00 | `src/utils/email.ts`, `src/db/users.ts` |
| ts-db-pool | 1.00 | 0.33 | 1.00 | `src/config/database.ts` |
| ts-app-bootstrap | 0.67 | 0.67 | 1.00 | `src/server/router.ts`, `src/server/app.ts`, `src/config/database.ts` |

### fixture: rust

| id | P@K | R@K | RR | predicted (top-K) |
|---|---|---|---|---|
| rs-login-rate-limit | 0.67 | 0.67 | 1.00 | `src/api/rate_limit.rs`, `src/auth/login.rs`, `src/auth/mod.rs` |
| rs-hash-password-lookup | 1.00 | 0.50 | 1.00 | `src/utils/crypto.rs` |
| rs-session-ttl | 0.67 | 1.00 | 1.00 | `src/config/settings.rs`, `src/auth/session.rs`, `src/auth/mod.rs` |
| rs-find-user-async | 0.33 | 0.33 | 0.50 | `src/utils/email.rs`, `src/db/queries.rs`, `src/utils/mod.rs` |
| rs-middleware-logging | 0.67 | 0.67 | 1.00 | `src/auth/middleware.rs`, `src/auth/mod.rs`, `src/utils/logging.rs` |
| rs-migrations-add-column | 1.00 | 0.50 | 1.00 | `src/db/migrations.rs` |
| rs-router-logout | 0.67 | 1.00 | 1.00 | `src/api/router.rs`, `src/auth/session.rs`, `src/auth/mod.rs` |
| rs-welcome-email | 0.33 | 0.50 | 1.00 | `src/utils/email.rs`, `src/utils/mod.rs`, `src/db/models.rs` |
| rs-db-pool | 1.00 | 0.33 | 1.00 | `src/config/database.rs` |
| rs-settings-env | 0.33 | 1.00 | 1.00 | `src/config/settings.rs`, `src/lib.rs`, `src/config/database.rs` |

## Fixtures

Three parallel mini web-apps: `python`, `typescript`, `rust`. Each has the same module layout — auth/api/config/db/utils — with cross-module imports the graph builder must resolve per language. Ground truth hand-labeled: for each prompt, which files a competent engineer would open first.

Prompts: `python/evals/autocontext_prompts.json`. Runner: `python/evals/runners/autocontext_eval.py`.

Precision@K = fraction of top-K predicted files that are in expected.
Recall@K = fraction of expected files present in top-K predicted.
MRR = mean of 1/rank of first correct prediction (0 if none in top-K).
