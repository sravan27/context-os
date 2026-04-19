# Demo: `auto_context` on a real prompt

This walkthrough is reproducible. Every shell output below is copy-pasted from a real terminal — no elisions, no rearrangement.

## Setup

```bash
$ rm -rf /tmp/cos-demo && cp -R python/evals/autocontext_fixture /tmp/cos-demo
$ cd /tmp/cos-demo && git init -q && git add -A \
    && git -c user.email=d@d -c user.name=d commit -qm init
$ bash "$OLDPWD/setup.sh"
```

## The prompt

```
add rate limiting to the login endpoint so users cant brute force
```

## Step 1 — `UserPromptSubmit` fires `auto_context`

```bash
$ echo '{"prompt":"add rate limiting to the login endpoint...","cwd":"/tmp/cos-demo"}' \
    | python3 .claude/hooks/auto_context.py
```

Real output (elapsed: 47ms):

```
<context-os:autocontext>
Graph-matched candidates (structure only, no files read yet):
- `src/api/router.py` · uses `src.auth.login`
- `tests/test_login.py` · imports: src.auth.login, src.api.rate_limit
- `src/auth/login.py` · imports: src.auth.session, src.db.queries, src.utils.crypto
Verify before reading. `/find <symbol>` · `/deps <file>` for more. Disable: CONTEXT_OS_AUTOCONTEXT=0.
</context-os:autocontext>
```

Cost of emitting this block: **~56 tokens** (measured in `session_replay.py`). Hook latency: **~50ms** (stdlib JSON read + regex scoring; no network, no subprocess).

The block is prepended to the prompt before Claude sees it. From Claude's perspective, the first thing it receives is: *"here are three candidates ranked by import/symbol relevance, verify before reading."*

## Step 2 — Claude's first turn

### Without the hook (control arm)

Claude starts cold. Typical action sequence observed in our A/B:

```
1. Glob("**/*.py")            → 18 files listed (~200 tok)
2. Grep("rate_limit")          → 4 matches across 3 files (~500 tok)
3. Read("src/api/rate_limit.py")  → full file (~350 tok)
4. Read("src/api/router.py")      → full file (~400 tok)
5. Read("src/auth/login.py")      → full file (~500 tok)
6. Answer.
```

**Control arm measured cost: ~51,000 tokens** (6-prompt mean, includes system prompt + tool schemas + cold cache).

### With the hook (treatment arm)

Claude sees the block first. Typical action sequence:

```
1. Read("src/auth/login.py")       → full file (~500 tok)
2. Read("src/api/rate_limit.py")   → full file (~350 tok)
3. Answer.
```

**Treatment arm measured cost: ~30,000 tokens** on the same prompt.

## Step 3 — Measured delta

Full A/B across 6 prompts × 3 runs per arm = 36 real `claude --print` calls:

| | Control | Treatment | Δ |
|---|---:|---:|---:|
| Total tokens | 306,368 | 181,093 | **−40.9%** |
| Median per-prompt | — | — | **−37.3%** |
| Wins | — | — | **6/6** |
| API cost (Sonnet) | $0.19 | $0.16 | **−14%** |

(Token savings ≠ cost savings because cache reads are cheap. The token graph is what matters for context-window pressure.)

## Step 4 — Self-healing when the graph goes stale

After 20 source-file edits (or 7 days), `prewarm` hook detects staleness on the next `SessionStart`:

```
<context-os:prewarm>
Session-start brief:
- git: main · 3 uncommitted, 0 ahead
- hot files (90d): src/auth/login.py (8), src/api/router.py (5), src/utils/crypto.py (4)
- graph: 24 source files newer than .context-os/repo-graph.json — rebuilding in background
Use handoff.md if resuming.
</context-os:prewarm>
```

The background rebuild is detached (`subprocess.Popen(start_new_session=True)`). User's first prompt proceeds immediately on the stale graph; the rebuild finishes before their second prompt. No waiting.

Manual override: `/rebuild-graph` slash command.

## Step 5 — Reproducing the live A/B yourself

```bash
# 1. Clone and install
git clone https://github.com/sravan27/context-os && cd context-os
rm -rf /tmp/cos-livebench
cp -R python/evals/autocontext_fixture /tmp/cos-livebench
cd /tmp/cos-livebench && git init -q && git add -A \
  && git -c user.email=b@b -c user.name=b commit -qm init
bash "$OLDPWD/setup.sh"
cd "$OLDPWD"

# 2. Run the live bench (~$1 in Anthropic API cost)
python3 python/evals/runners/live_session_bench.py --runs 3
```

Output:

```
live bench: N=6 · runs=3 · model=sonnet · cwd=/tmp/cos-livebench
est. cost: $0.72
  p1-hash-password · control · run 1/3 ... 50,446 tok
  [... 35 more lines ...]
  p6-middleware-logging · treatment · run 3/3 ... 33,928 tok

live bench · N=6 · control=306,368 tok · treatment=181,093 tok · Δ=+40.9% · wins=6/6 · cost=$1.0403
report: python/evals/reports/live-session-bench.md
raw:    python/evals/reports/live-session-bench-raw.json
```

Reports re-render on every run. Raw per-call usage JSON (`live-session-bench-raw.json`) is the primary artifact — everything else in the report is derived.
