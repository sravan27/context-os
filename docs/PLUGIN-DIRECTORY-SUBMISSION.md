# Claude plugin directory submission notes

Context OS is packaged as a lightweight Claude Code marketplace plugin.

## What the marketplace profile enables

- `SessionStart`: runs `hooks/python/prewarm.py` from `${CLAUDE_PLUGIN_ROOT}`. It prints a compact local brief and builds `.context-os/repo-graph.json` in the background if the graph is missing or stale.
- `UserPromptSubmit`: runs `hooks/python/auto_context.py` from `${CLAUDE_PLUGIN_ROOT}`. It reads the current prompt plus `.context-os/repo-graph.json` and adds ranked `file:line` candidates as context.
- Skills: `context-os:init`, `context-os:doctor`, and `context-os:stats` use the official `skills/<name>/SKILL.md` layout.

## What it deliberately does not enable

The marketplace profile does not ship broad `PreToolUse`, `PostToolUse`, `Stop`, or `PreCompact` hooks. Those advanced local guards remain available through `setup.sh` for users who explicitly opt in from the repository README.

## Privacy and security review summary

- No network calls, servers, embeddings, or telemetry.
- Hook scripts are Python stdlib only.
- The prompt hook reads only hook stdin and `.context-os/repo-graph.json`.
- The graph stores paths, symbol names, import names, line counts, and git-hot file paths. It does not store file bodies, comments, string literals, environment variables, credentials, or `.env` contents.
- All hooks fail open: on malformed input, missing graph, or exceptions, they exit 0 and keep Claude Code running.

Review anchors:

- `hooks/hooks.json`
- `hooks/python/auto_context.py`
- `hooks/python/prewarm.py`
- `hooks/python/build_repo_graph.py`
- `docs/SECURITY.md`
