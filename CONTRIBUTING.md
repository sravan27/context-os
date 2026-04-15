# Contributing to Context OS

The goal is completeness: **every proven Claude Code token optimization in one command.** If a technique measurably reduces Claude Code token consumption, it belongs here.

## The bar for new techniques

We merge techniques that meet all of these:

1. **Measurable.** You can show before/after token counts on a real or reproducible workload. Not vibes, not "feels faster."
2. **Automatable.** It can be done by writing files, setting env vars, adding hooks, or installing subagents — not "just prompt Claude better."
3. **Reversible.** `setup.sh --uninstall` must be able to remove it cleanly.
4. **Idempotent.** Running `setup.sh` twice must not duplicate, conflict, or break.
5. **Zero-dependency for the base install.** Optional binary enhancements are fine (hooks, compression). The `curl | bash` path must stay dependency-free.
6. **Safe by default.** No secret leakage, no destructive rewrites, no surprise network calls.

## How to propose a technique

1. Open a [Technique submission issue](https://github.com/sravan27/context-os/issues/new?template=technique_submission.yml).
2. Include the measurement. Link the script or the raw numbers.
3. Describe the integration: what file gets written, which settings change, what hook fires.
4. Credit prior art — if this is from RTK, Caveman, claude-mem, or a blog post, say so.

If the technique clearly fits, we'll tag it `accepted` and you (or we) can send a PR.

## How to send a PR

1. Fork, branch off `main`.
2. Implement the technique in **both** places:
   - `setup.sh` for the zero-dependency path
   - `apps/cli/src/main.rs` (`run_init`) for the binary path
3. Add a test:
   - Bash integration: extend `.github/workflows/ci.yml` `setup-sh` job
   - Rust: a `#[test]` in the relevant crate
4. Update `README.md`'s technique table with the measured savings.
5. Run locally:
   ```bash
   cargo test
   bash setup.sh --measure   # on a test fixture
   bash setup.sh             # on a test fixture, should be idempotent
   bash setup.sh --uninstall # must cleanly remove
   ```
6. Open the PR. Link the issue.

## Code style

- Bash: `set -euo pipefail` at the top. Quote all variables. No `eval`.
- Rust: `cargo fmt` + `cargo clippy -- -D warnings`.
- No emojis in code or docs unless explicitly asked.
- Keep CLAUDE.md additions terse. Every token in that file costs users money on every turn.

## What we reject

- Techniques without measurement.
- Techniques that only work with a specific IDE extension or paid service.
- Techniques that require network calls during setup.
- Techniques that modify git history, push to remotes, or touch `~/.claude/` without explicit consent.
- "AI-generated" PRs that re-describe existing techniques without adding new ones.

## Philosophy

Context OS is not a framework. It is a **curated set of defaults**. Every kilobyte we add to CLAUDE.md is a tax on every user's every turn. Every hook we ship is a surface for bugs. So:

- Smaller is better. Delete what's redundant.
- Precise is better. Cite the benchmark.
- Boring is better. No clever macros, no DSLs, no auto-upgrading.

If you make Context OS 1% smaller without losing coverage, that is the best PR you can send.
