# auto_context eval

_Generated 2026-04-19T09:40:48+00:00 · K=3 · N=12 prompts_

## Aggregate

| Metric | Value |
|---|---|
| Precision@3 | **0.611** |
| Recall@3 | **0.583** |
| MRR | **0.958** |
| Coverage (non-empty) | 1.000 |

Precision@K = fraction of top-K predicted files that are in expected.
Recall@K = fraction of expected files present in top-K predicted.
MRR = mean of 1/rank of first correct prediction (0 if none in top-K).

## Per-prompt

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

## Fixture

Realistic mini web-app: auth (login/session/middleware), api (router/rate_limit), config (settings/database), db (models/migrations/queries), utils (crypto/email/logging), plus importer-edge tests. 13 source files, 5 test files, ~30 symbols, genuine cross-file imports.

Ground truth was hand-labeled by enumerating which files a competent engineer would open first for each task. See `python/evals/autocontext_prompts.json`.
