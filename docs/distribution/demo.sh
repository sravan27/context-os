#!/usr/bin/env bash
# One-command demo recording for context-os.
# Records a clean, honest ~60-second walkthrough of the hook + eval.
#
# Usage:   asciinema rec demo.cast --command "bash docs/distribution/demo.sh" --idle-time-limit 1.5
# Upload:  asciinema upload demo.cast
#
# The recording is meant for the README + Show HN + X thread. Don't edit it.

set -euo pipefail
clear
PS1='$ '

say() { printf '\n%s\n' "$*"; sleep 0.4; }

say "context-os v2.8.0 — live demo (no edits)"
say "Goal: cut Claude Code's first-turn token spend"
sleep 1

# 1. What's installed
say "→ The hook is ~400 lines of stdlib Python:"
wc -l hooks/python/auto_context.py | awk '{printf "  %s lines · %s\n", $1, $2}'

# 2. The graph
say "→ The repo graph (built at install time, ~50 ms cold):"
python3 - <<'PY'
import json, os
g = json.load(open('.context-os/repo-graph.json'))
print(f"  files indexed  : {len(g.get('files', []))}")
sym = g.get('symbol_index', {})
total = sum(len(sym[k]) for k in sym)
print(f"  symbols        : {total}")
print(f"  import edges   : {sum(len(v) for v in g.get('imports', {}).values())}")
print(f"  hot files      : {len(g.get('hot_files', []))}")
print(f"  size on disk   : {os.path.getsize('.context-os/repo-graph.json'):,} bytes")
PY

# 3. What gets injected when Claude submits a prompt
say "→ Prompt: \"where is the auto_context hook\""
say "→ What the UserPromptSubmit hook prepends to Claude's input:"
printf '%s\n' '{"prompt":"where is the auto_context hook"}' \
  | python3 hooks/python/auto_context.py 2>/dev/null

# 4. Cross-repo eval — 3 unseen OSS repos
say "→ Cross-repo eval (axios, ripgrep, requests · 36 prompts):"
python3 python/evals/runners/multi_repo_eval.py --skip-clone 2>&1 \
  | grep -E 'MRR|weighted|wrote' \
  || echo "  (re-run setup.sh first if this fails)"

# 5. Regression floor
say "→ 9 CI-enforced regression floors:"
python3 python/evals/runners/ranker_floor.py 2>&1 \
  | grep -E 'PASS|FAIL|all floors' \
  | head -12

# 6. Outro
say "github.com/sravan27/context-os · MIT · stdlib Python · no embeddings"
