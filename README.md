# Context OS

[![CI](https://github.com/sravan27/context-os/actions/workflows/ci.yml/badge.svg)](https://github.com/sravan27/context-os/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](https://github.com/sravan27/context-os/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-optimized-8A2BE2)](https://claude.com/code)

**Stop hitting Claude Code usage limits.** Every proven token optimization in one command.

```bash
cd your-project
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

Zero dependencies. Fully reversible. Works with Claude Pro, Max, and API.

## See what you'd save (no install)

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --measure
```

Scans your repo and estimates tokens saved per session. No writes, no config, no install. Sample:

```
  Source files:            342
  Noise files:             12,847

  Conservative per-session savings:

  Noise filtering:         ~50K tokens
  Response shaping:        ~20K tokens
  Thinking cap (8K):       ~15K tokens
  Haiku exploration:       ~10K tokens
  Output compression:      ~8K tokens
  ────────────────────────────────────
  TOTAL:                   ~103K tokens/session

  Pro/Max plan:            longer sessions before hitting 5-hr cap
  API users (Sonnet 4.6):  ~$0.61/session ($12/week @ 20 sessions)
```

## What it does, in order

This is the complete list. If another technique exists that measurably reduces Claude Code token consumption and we're missing it, [open an issue](https://github.com/sravan27/context-os/issues).

| # | Technique | What it does | Measured savings |
|---|-----------|-------------|------------------|
| 1 | **Response shaping** (CLAUDE.md) | Instructs Claude to drop preamble, recap, filler, tool announcements, over-explanation | 40-65% output tokens ([benchmark](https://github.com/JuliusBrussee/caveman)) |
| 2 | **Noise filtering** (.claudeignore) | Blocks Claude from reading `node_modules`, `dist`, `.next`, `target`, 60+ noise dirs and lock files | 30-40% context reduction in Next.js projects |
| 3 | **Secret exclusion** (.claudeignore) | Explicitly blocks `.env`, `*.pem`, `credentials.json`, SSH keys, AWS creds | Security + tokens |
| 4 | **Repo map** (CLAUDE.md) | Tells Claude your project structure upfront so it doesn't scan | Saves 3-10 Bash/Glob calls per session |
| 5 | **Thinking budget cap** (settings.json) | Sets `MAX_THINKING_TOKENS=8000` — caps extended thinking from 32K+ default | 50-70% on simple tasks |
| 6 | **Early compaction** (settings.json) | Sets `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80` (default is 95%) | Keeps context small, reduces per-turn cost |
| 7 | **Slash commands** (.claude/commands/) | `/compact` (save state), `/context` (check usage), `/ship` (test+commit+stop) | Structured efficiency |
| 8 | **Haiku subagent** (.claude/agents/explorer.md) | Exploration runs on Haiku (15x cheaper than Opus) in isolated context window | ~93% savings on exploration, main context stays clean |
| 9 | **Output compression** (hooks) | Test/build output wrapped through typed reducers before Claude sees it | 27-70% on test runs (50 passing tests → 1 line) |
| 10 | **Session memory** (hooks) | Decisions captured into restart packet before compaction/session end | Survives compaction and restarts — never re-explain |

Steps 1-8 need only `curl | bash`. Steps 9-10 need the optional binary.

## One command install

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

Sample output:

```
  context-os v0.3.0
  ═══════════════════════════════════════════════════
  Every proven Claude Code token optimization
  in one command. Zero dependencies. Reversible.

  scanning project...
  stack:  node, typescript, next.js
  source: 342 files
  noise:  12,847 files

  [1/7] created CLAUDE.md (response shaping + repo map)
  [2/7] created .claudeignore (84 patterns, secrets blocked)
  [3/7] created settings.json (MAX_THINKING_TOKENS=8000, AUTOCOMPACT=80%)
  [4/7] installed 3 slash commands (/compact, /context, /ship)
  [5/7] installed explorer subagent (Haiku — 15x cheaper)
  [6/7] hooks skipped (needs binary — optional)
  [7/7] added .context-os/ to .gitignore

  ── what's active ───────────────────────────────────

  ✓ noise filtering        12,847 files hidden (~2.5M tokens/search)
  ✓ response shaping       40-65% fewer output tokens
  ✓ repo map               Claude skips structure scanning
  ✓ thinking cap           8000 tokens max (saves on simple tasks)
  ✓ early compaction       at 80% (default is 95%)
  ✓ slash commands         /compact /context /ship
  ✓ haiku subagent         /explorer for cheap exploration
  ✓ secret filtering       .env, *.pem, credentials blocked
```

## With hooks (adds 2 more optimizations)

```bash
cargo install --git https://github.com/sravan27/context-os --path apps/cli
context-os init
```

Adds:
- **Output compression** — 27-70% reduction on test/build output. `cargo test`, `npm test`, `npx jest`, `pytest`, `go test`, `bun test`, `deno test`, `dotnet test`, `swift test`, `flutter test`, and 32 more commands.
- **Session memory** — PreCompact hook injects decisions before Claude forgets them. Stop hook writes handoff for manual recovery.

## Status and uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --status
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --uninstall
```

Uninstall preserves your existing CLAUDE.md content — only the `<!-- context-os -->` block is removed.

## Manual techniques (can't be automated, but worth knowing)

Context OS automates the things that can be automated. These are the manual techniques that round out the optimization stack:

- **`/clear`** between unrelated tasks. Stale context costs tokens on every message.
- **`/btw [question]`** for side questions that don't need to persist. Up to 50% savings vs asking in the main thread.
- **`/compact [instructions]`** to direct what to preserve: `/compact Focus on API changes`.
- **Plan mode** (`Shift+Tab`) for exploration without execution. Eliminates trial-and-error tokens.
- **Specific prompting.** `fix the null check in auth.ts:42` vs `improve the auth code`.
- **`@filename`** to reference files directly instead of making Claude search.
- **Writer/Reviewer pattern.** Session 1 implements. Fresh session 2 reviews. Avoids context bias.
- **Use the explorer subagent.** Tell Claude: "use the explorer subagent to find all callers of `authenticate`".

## Measured results

From our own benchmarks in `python/evals/reports/`:

- **71% reduction** on 50-test cargo output (48 passing tests collapsed, 2 failures preserved)
- **100% protected string recall** — no errors, paths, or versions dropped
- **5/5 concurrent PostToolUse writes** captured (lockfile prevents race conditions)
- **Full fail-edit-pass cycle** — decisions survive compaction with rationale intact
- **42 command patterns** matched including `cd /path && RUST_BACKTRACE=1 cargo test`

## Why this exists

Most Claude Code optimization tools do one thing well:

| Technique | Context OS | [caveman](https://github.com/JuliusBrussee/caveman) | [RTK](https://github.com/DiogenesOfSinope/RTK) | [claude-mem](https://github.com/khaliqgant/claude-mem) | [context-mode](https://github.com/brian-woodward/context-mode) |
|---|:-:|:-:|:-:|:-:|:-:|
| Response shaping (CLAUDE.md) | ✅ | ✅ | ❌ | ❌ | ❌ |
| Noise filtering (.claudeignore) | ✅ | ❌ | ❌ | ❌ | ✅ |
| Secret exclusion | ✅ | ❌ | ❌ | ❌ | ❌ |
| Repo map | ✅ | ❌ | ❌ | ❌ | ❌ |
| Thinking budget cap | ✅ | ❌ | ❌ | ❌ | ❌ |
| Early compaction threshold | ✅ | ❌ | ❌ | ❌ | ❌ |
| Slash commands | ✅ | ❌ | ❌ | ❌ | ❌ |
| Haiku subagent (explorer) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Output compression (hooks) | ✅ | ❌ | ✅ | ❌ | ❌ |
| Session memory | ✅ | ❌ | ❌ | ✅ | ❌ |
| One-command install | ✅ | ❌ | ✅ | ✅ | ❌ |
| Reversible uninstall | ✅ | ❌ | ❌ | ❌ | ❌ |
| `--measure` (no-install dry run) | ✅ | ❌ | ❌ | ❌ | ❌ |

None put them together. You end up installing four tools, maintaining four configs, and still missing techniques that need custom integration (env vars, secret filtering, Haiku subagents).

Context OS is one command. Every proven technique. If a new technique emerges, we add it here — you re-run the one curl command.

## Limitations

- Does not bypass Anthropic usage limits. Makes them hurt less.
- Response shaping effectiveness varies: 40-65% on explanation-heavy tasks, 13-21% on structured code.
- Haiku subagent quality varies by task. For complex reasoning, use the main session.
- Hook-based compression depends on Claude Code hook availability (PreToolUse, PostToolUse, PreCompact, SessionStart, Stop).
- The 12-15% overhead from our CLAUDE.md block pays for itself in 1-2 turns on any non-trivial session.

## Verify setup

```bash
context-os doctor   # if binary installed
# or
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --status
```

## Development

```bash
cargo test
python3 python/evals/runners/safe_mode_runner.py
python3 python/evals/runners/compaction_survival_runner.py
```

## Contributing

If you know a Claude Code optimization technique we're missing, please [open an issue](https://github.com/sravan27/context-os/issues) or send a PR. The goal is completeness — if a technique measurably reduces token consumption, it belongs here.

## Credits

Builds on research from:
- [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) — caveman prompting benchmark
- [drona23/claude-token-efficient](https://github.com/drona23/claude-token-efficient) — 63% output reduction measurements
- [Anthropic Claude Code docs](https://code.claude.com/docs/en/best-practices) — official best practices, env vars, hooks reference
- Community benchmarks at claudecodecamp.com on prompt caching

## License

MIT
