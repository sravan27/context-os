# Context OS — Security & privacy model

Short version: **nothing leaves your machine. No network, no telemetry, no opt-out needed because there's nothing to opt out of.** Details below for enterprise reviewers.

---

## What runs, where, and when

| Component | Trigger | Where | What it reads | What it writes | Network? |
|---|---|---|---|---|:-:|
| `build_repo_graph.py` | Install + `/refresh-graph`; background on staleness | Your machine, as your user | Source files in repo (ext allowlist) + `git log --name-only --since=90.days` | `.context-os/repo-graph.json` in repo root | No |
| `auto_context.py` | `UserPromptSubmit` hook, per prompt | Your machine, as your user | Prompt + `.context-os/repo-graph.json` | stdout (consumed by Claude Code) | No |
| `prewarm.py` | `SessionStart` hook | Your machine | `.context-os/repo-graph.json` + git metadata | stdout + background `build_repo_graph.py` on stale graph | No |
| `dedup_guard.py` | `PostToolUse` | Your machine | Recent Read/Glob/Grep tool-call log in session | `.context-os/dedup-cache.json` | No |
| `loop_guard.py` | `PostToolUse` | Your machine | Recent Edit tool-call log in session | `.context-os/loop-cache.json` | No |
| `file_size_guard.py` | `PreToolUse` (on Read) | Your machine | File size of target Read | stderr (warning) | No |
| `session_profile.py` | `Stop` | Your machine | Session tool-call log | `.context-os/session-reports/<ts>.md` | No |

**Every path is local.** Every hook is stdlib-only Python. No `requests`, no `urllib.urlopen`, no sockets, no external binaries beyond `git` (invoked with explicit `-C <repo>` and no shell).

---

## What is stored on disk

Everything lives under `.context-os/` in your repo root. Add it to `.gitignore` if you don't want to commit it (we don't auto-`.gitignore` because some teams intentionally commit the graph for shared tooling).

```
.context-os/
├── repo-graph.json            # symbols, imports, hot-files — from your source
├── dedup-cache.json           # recent (file, mtime) → hash for re-Read blocking
├── loop-cache.json            # edit-count-per-file for iteration guard
├── session-reports/<ts>.md    # per-session token-spend profile (local only)
└── handoff.md                 # optional; for cross-session continuity
```

Typical size: 50–200 KB for small repos, ~2 MB for a 5k-file repo. Entirely regenerable — you can `rm -rf .context-os/` and the tooling rebuilds on next prompt.

---

## What is in the graph

Per file indexed:
- **Relative path** (e.g. `src/api/router.py`)
- **Language** (inferred from extension)
- **Symbol names** (top-level `def/class/fn/struct/const` — identifier names only, **not function bodies**)
- **Line numbers** for those symbols (so the hook can output `file:42`)
- **Import paths** (module names — e.g. `src.db.queries`, not the imported values)
- **Line count** (size signal)

Per repo:
- **Hot files**: list of file paths with change counts from `git log --name-only --since=90.days`

**Not stored:** file contents, comments, string literals, variable values, commit messages, authorship, diffs, env vars, credentials, `.env` file contents, contents of any directory in `EXCLUDE_DIRS` (`node_modules`, `target`, `dist`, `.venv`, `__pycache__`, …).

---

## What the hook sends to Claude

On each prompt, `auto_context.py` emits to stdout a block like:

```
<context-os:autocontext>
Graph-matched candidates (structure only, no files read yet):
- `src/auth/login.py:42` · `validate_credentials` (def) · imports: src.utils.crypto, src.db.queries
- `src/utils/crypto.py:1` · `hash_password` (def)
- `src/api/router.py:12` · `APIRouter.add` (def) · hot (7 touches/90d)
</context-os:autocontext>
```

Claude Code prepends this to your prompt. Contents: **up to 5 file paths, symbol names you already declared, and their import edges.** Nothing from the function bodies, no stdout of any command, no environment data.

This is the only data the hook contributes to any Claude turn. You can inspect it yourself by running:

```bash
echo '{"prompt":"..."}' | python3 hooks/python/auto_context.py
```

---

## What the hook WON'T do

- **Will not read a file that's not already scanned during graph build.** The hook only consults the graph; it does not open any source file at query time.
- **Will not traverse outside `$CWD`.** `build_repo_graph.py` uses `os.walk(root)`; all relative paths are rooted at the repo.
- **Will not escape `.claudeignore` / `EXCLUDE_DIRS`.** Standard deny-list plus prefix denies for fixture directories (`autocontext_fixture*`).
- **Will not exec code.** Pure regex + `os.walk` for scanning; no `importlib`, no `eval`, no `exec`, no AST-walker that runs `__init__.py`.
- **Will not shell out with user data.** The only subprocess is `git log` with fixed args; the prompt never reaches a shell.

---

## Failure modes

- **Corrupt `.context-os/repo-graph.json`** → hook logs nothing, exits 0, Claude proceeds as if no hook ran. Validated by `robustness.md` (`corrupt-graph` case).
- **Missing `.context-os/` directory** → `build_repo_graph.py` creates it with `os.makedirs(exist_ok=True)`; if that fails (read-only FS), the hook exits 0.
- **Prompt contains adversarial characters** (null bytes, 100K chars, unicode, shell metacharacters, regex-bomb `a*`) → all 9 adversarial cases in `robustness.md` exit 0 in <25ms.
- **stdin empty / not JSON** → exit 0, no output. Caught in `robustness.md`.

The hook **cannot** crash Claude Code. Every code path is wrapped in `try/except` at `main()` level with `sys.exit(0)` on any unhandled exception. Verified by the robustness suite.

---

## Enterprise concerns

**Does the graph leak proprietary code?** It contains names (symbols, paths, imports). If your threat model considers function *names* and *file paths* as sensitive (rare, but possible), you can:

- Disable the hook: `CONTEXT_OS_AUTOCONTEXT=0` in `settings.json` env.
- Delete `.context-os/` between sessions.
- Add the directory to `.gitignore` (default — your choice whether to commit).

**Can the hook be used to exfiltrate data?** No network stack is imported; attempting to add one would be a code-level change visible in the git history. The hook is ~400 lines; a security review takes under an hour.

**Can I audit what was injected into Claude?** Yes:
```bash
echo '{"prompt":"<the exact prompt you used>"}' \
  | python3 hooks/python/auto_context.py
```
The output is the full injected block, byte-for-byte.

**Is the `dedup-cache.json` sensitive?** It stores `(file_path, mtime) → SHA256(file_contents_truncated_32KB)`. Hashes are salted by a per-install random secret; hashes leaking does not reveal content without a brute-force dictionary attack against your exact file. Delete the cache to rotate.

---

## Audit trail

- **`hooks/python/auto_context.py`** — 476 lines, one file, no dependencies outside stdlib. Review in ~30 minutes.
- **`hooks/python/build_repo_graph.py`** — 258 lines, one file, one subprocess (`git log`), no dependencies.
- **`python/evals/runners/robustness_test.py`** — 18 adversarial cases; CI-enforced.
- **No external telemetry or analytics anywhere in the codebase.** Searchable: `grep -r 'requests\|urllib.request\|http\.client\|socket\|sentry' hooks/ crates/` returns nothing.

If you find a security concern, email sridharsravan@icloud.com or open a GitHub issue. We'll respond within 24 hours and release a fix within 72.
