#!/usr/bin/env bash
# context-os: Every known Claude Code token optimization in one command.
# Usage: curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
# Uninstall: curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --uninstall
set -euo pipefail

# ============================================================================
# Uninstall mode
# ============================================================================
if [ "${1:-}" = "--uninstall" ]; then
  echo "context-os: removing optimizations..."
  # Remove CLAUDE.md block (preserve user content)
  if [ -f CLAUDE.md ] && grep -q '<!-- context-os:start -->' CLAUDE.md; then
    python3 -c "
import re
text = open('CLAUDE.md').read()
text = re.sub(r'\n*<!-- context-os:start -->.*?<!-- context-os:end -->\n*', '', text, flags=re.DOTALL)
open('CLAUDE.md', 'w').write(text)
" 2>/dev/null && echo "  removed response shaping from CLAUDE.md" || echo "  could not update CLAUDE.md (remove <!-- context-os --> block manually)"
    # Delete CLAUDE.md if it's now empty
    if [ -f CLAUDE.md ] && [ ! -s CLAUDE.md ]; then
      rm CLAUDE.md && echo "  deleted empty CLAUDE.md"
    fi
  fi
  # Remove .claudeignore if we created it
  if [ -f .claudeignore ] && head -1 .claudeignore | grep -q 'context-os'; then
    rm .claudeignore && echo "  removed .claudeignore"
  fi
  # Remove hooks from settings
  if [ -f .claude/settings.local.json ]; then
    python3 -c "
import json
s = json.load(open('.claude/settings.local.json'))
s.pop('hooks', None)
if s:
    json.dump(s, open('.claude/settings.local.json', 'w'), indent=2)
else:
    import os; os.remove('.claude/settings.local.json')
" 2>/dev/null && echo "  removed hooks from .claude/settings.local.json"
  fi
  # Remove session state
  [ -d .context-os ] && rm -rf .context-os && echo "  removed .context-os/"
  echo "  done. Context OS fully removed."
  exit 0
fi

# ============================================================================
# Install mode
# ============================================================================
echo "context-os: scanning project..."

# ============================================================================
# 0. Detect project stack and count noise
# ============================================================================
NOISE_FILES=0
NOISE_DIRS=""

count_files_in() {
  if [ -d "$1" ]; then
    local c
    c=$(find "$1" -type f 2>/dev/null | head -10000 | wc -l | tr -d ' ')
    NOISE_FILES=$((NOISE_FILES + c))
    NOISE_DIRS="$NOISE_DIRS  $1/ ($c files)\n"
  fi
}

# Check all common noise directories
for dir in node_modules .next dist build out target/debug target/release \
           __pycache__ .venv venv .tox .mypy_cache .pytest_cache \
           coverage .nyc_output .gradle .idea .vs .vscode \
           vendor Pods .dart_tool .flutter-plugins \
           .git/objects .turbo .parcel-cache .cache; do
  count_files_in "$dir"
done

# Detect stack
STACK=""
[ -f package.json ] && STACK="$STACK node"
[ -f tsconfig.json ] && STACK="$STACK typescript"
[ -f next.config.js ] || [ -f next.config.mjs ] || [ -f next.config.ts ] && STACK="$STACK nextjs"
[ -f Cargo.toml ] && STACK="$STACK rust"
[ -f go.mod ] && STACK="$STACK go"
[ -f requirements.txt ] || [ -f pyproject.toml ] || [ -f setup.py ] && STACK="$STACK python"
[ -f Gemfile ] && STACK="$STACK ruby"
[ -f pom.xml ] || [ -f build.gradle ] || [ -f build.gradle.kts ] && STACK="$STACK java"
[ -f pubspec.yaml ] && STACK="$STACK flutter"
[ -f Package.swift ] && STACK="$STACK swift"
[ -f *.csproj ] 2>/dev/null && STACK="$STACK dotnet"
STACK="${STACK# }"  # trim leading space

if [ -n "$STACK" ]; then
  echo "  detected: $STACK"
fi
if [ "$NOISE_FILES" -gt 0 ]; then
  printf "  found %s files in noise directories:\n" "$NOISE_FILES"
  printf "$NOISE_DIRS"
fi
echo ""
echo "  configuring optimizations..."
echo ""

# ============================================================================
# 1. CLAUDE.md — Response shaping + repo rules
#    Research: terse instructions save 40-65% output tokens (caveman benchmark)
# ============================================================================
MARKER_START="<!-- context-os:start -->"
MARKER_END="<!-- context-os:end -->"

BLOCK="$MARKER_START
# Response rules

- Ultra-concise. No preamble, recap, or filler.
- Code > explanation. Show diff, not rationale.
- 1-2 sentence plan then execute. No pre-explanation.
- Fragments ok. Drop articles. Be direct.
- NEVER announce tool calls. Just call them.
- NEVER repeat what the user said back to them.
- If fixing a bug, show only the fix. Skip root-cause unless asked.
- Prefer Edit over Write. Diffs use fewer tokens than full files.

# Repo rules

- Read only files you will change.
- Batch edits. One response, multiple files.
- On errors: show error only. Skip passing output.
- Run tests once to verify, not to explore.

# Session continuity

If a restart packet or \`.context-os/handoff.md\` exists, read it first.
Resume from there. Don't re-attempt failed approaches.
$MARKER_END"

if [ -f CLAUDE.md ]; then
  if grep -q "$MARKER_START" CLAUDE.md; then
    # Use sed-based approach to avoid Python quoting issues
    # Write new block to temp file, then use Python to do the replacement reading from files
    TMPBLOCK=$(mktemp)
    printf '%s' "$BLOCK" > "$TMPBLOCK"
    python3 -c "
import re
text = open('CLAUDE.md').read()
block = open('$TMPBLOCK').read()
text = re.sub(r'<!-- context-os:start -->.*?<!-- context-os:end -->', block, text, flags=re.DOTALL)
open('CLAUDE.md', 'w').write(text)
" 2>/dev/null && echo "  [1/4] updated CLAUDE.md response shaping" || echo "  [1/4] CLAUDE.md exists (could not update, skipping)"
    rm -f "$TMPBLOCK"
  else
    printf '\n\n%s\n' "$BLOCK" >> CLAUDE.md
    echo "  [1/4] appended response shaping to CLAUDE.md"
  fi
else
  printf '%s\n' "$BLOCK" > CLAUDE.md
  echo "  [1/4] created CLAUDE.md with response shaping"
fi

# ============================================================================
# 2. .claudeignore — Stop Claude from searching noise directories
#    Every file Claude reads = tokens burned
# ============================================================================
if [ ! -f .claudeignore ]; then
  IGNORES=""
  for dir in node_modules .next dist build out target/debug target/release \
             __pycache__ .venv venv .tox .mypy_cache .pytest_cache \
             coverage .nyc_output .gradle .idea .vs .vscode \
             vendor Pods .dart_tool .flutter-plugins \
             .git/objects .turbo .parcel-cache .cache; do
    [ -d "$dir" ] && IGNORES="$IGNORES$dir/
"
  done

  # Always ignore these file patterns (huge, never useful to Claude)
  IGNORES="${IGNORES}*.lock
*.min.js
*.min.css
*.map
*.chunk.js
*.bundle.js
package-lock.json
yarn.lock
pnpm-lock.yaml
Cargo.lock
poetry.lock
Gemfile.lock
*.wasm
*.pb.go
*.generated.*
*.snap
"
  printf '# Generated by context-os — prevents Claude from searching noise\n%s' "$IGNORES" > .claudeignore
  echo "  [2/4] created .claudeignore (filtering $NOISE_FILES files)"
else
  echo "  [2/4] .claudeignore already exists"
fi

# ============================================================================
# 3. .claude/settings.local.json — Hooks for output compression + memory
#    Only if full binary is available
# ============================================================================
BIN=""
if command -v context-os &>/dev/null; then
  BIN="context-os"
elif [ -f "./target/debug/context-os" ]; then
  BIN="$(cd . && pwd)/target/debug/context-os"
elif [ -f "./target/release/context-os" ]; then
  BIN="$(cd . && pwd)/target/release/context-os"
fi

if [ -n "$BIN" ]; then
  mkdir -p .claude
  SETTINGS=".claude/settings.local.json"
  ROOT="$(pwd)"

  # Build hooks JSON
  HOOKS=$(cat <<HOOKEOF
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "$BIN hook pre-tool-use", "timeout": 2}]
      }
    ],
    "PostToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "$BIN hook post-tool-use", "timeout": 5}]},
      {"matcher": "Edit", "hooks": [{"type": "command", "command": "$BIN hook post-tool-use", "timeout": 5}]},
      {"matcher": "Write", "hooks": [{"type": "command", "command": "$BIN hook post-tool-use", "timeout": 5}]}
    ],
    "PreCompact": [
      {"matcher": "", "hooks": [{"type": "command", "command": "$BIN hook pre-compact 2>/dev/null || true", "timeout": 5}]}
    ],
    "SessionStart": [
      {"matcher": "", "hooks": [{"type": "command", "command": "$BIN resume --root \"$ROOT\" 2>/dev/null || cat \"$ROOT/.context-os/handoff.md\" 2>/dev/null || true", "timeout": 5}]}
    ],
    "Stop": [
      {"matcher": "", "hooks": [{"type": "command", "command": "$BIN handoff --root \"$ROOT\" 2>/dev/null || true", "timeout": 10}]}
    ]
  }
}
HOOKEOF
)

  if [ -f "$SETTINGS" ]; then
    # Merge hooks into existing settings (pipe JSON via stdin to avoid quoting issues)
    printf '%s' "$HOOKS" | python3 -c "
import json, sys
existing = json.load(open('$SETTINGS'))
new_hooks = json.load(sys.stdin)
existing['hooks'] = new_hooks['hooks']
json.dump(existing, open('$SETTINGS', 'w'), indent=2)
" 2>/dev/null && echo "  [3/4] updated hooks in .claude/settings.local.json" || echo "  [3/4] could not merge hooks (settings.local.json may need manual update)"
  else
    printf '%s' "$HOOKS" | python3 -m json.tool > "$SETTINGS" 2>/dev/null || printf '%s' "$HOOKS" > "$SETTINGS"
    echo "  [3/4] installed 5 hooks in .claude/settings.local.json"
  fi

  # Create session state
  mkdir -p .context-os
  [ -f .context-os/session.json ] || printf '{"schema_version":1}' > .context-os/session.json
  [ -f .context-os/journal.jsonl ] || touch .context-os/journal.jsonl
else
  echo "  [3/4] hooks skipped (install binary for output compression + session memory)"
fi

# ============================================================================
# 4. .gitignore — Keep local state out of version control
# ============================================================================
if [ -f .gitignore ]; then
  if ! grep -q '.context-os' .gitignore 2>/dev/null; then
    printf '\n# Context OS local state\n.context-os/\n' >> .gitignore
    echo "  [4/4] added .context-os/ to .gitignore"
  else
    echo "  [4/4] .gitignore already has .context-os/"
  fi
else
  printf '# Context OS local state\n.context-os/\n' > .gitignore
  echo "  [4/4] created .gitignore"
fi

# ============================================================================
# Impact summary
# ============================================================================
echo ""
echo "  ── impact ──────────────────────────────────────────"
echo ""

# Estimate token savings
# Average file = ~200 tokens for Claude to process (path + content sample)
# Response shaping saves ~50% on explanation-heavy tasks
TOKENS_SAVED=0
if [ "$NOISE_FILES" -gt 0 ]; then
  TOKENS_SAVED=$((NOISE_FILES * 200))
  if [ "$TOKENS_SAVED" -ge 1000000 ]; then
    DISPLAY_TOKENS="$(echo "scale=1; $TOKENS_SAVED / 1000000" | bc 2>/dev/null || echo "$((TOKENS_SAVED / 1000000))")M"
  elif [ "$TOKENS_SAVED" -ge 1000 ]; then
    DISPLAY_TOKENS="$(echo "scale=0; $TOKENS_SAVED / 1000" | bc 2>/dev/null || echo "$((TOKENS_SAVED / 1000))")K"
  else
    DISPLAY_TOKENS="$TOKENS_SAVED"
  fi
  echo "  .claudeignore: $NOISE_FILES noise files hidden (~${DISPLAY_TOKENS} tokens/search saved)"
else
  echo "  .claudeignore: active (no noise dirs detected yet)"
fi

echo "  CLAUDE.md:     response shaping active (40-65% output reduction)"

if [ -n "$BIN" ]; then
  echo "  hooks:         5 active (output compression + session memory)"
else
  echo "  hooks:         inactive (optional — install binary for 27-70% output compression)"
fi

echo ""
echo "  Start a new Claude Code session to activate."
if [ -z "$BIN" ]; then
  echo ""
  echo "  Want hooks too? cargo install --git https://github.com/sravan27/context-os --path apps/cli"
fi
echo ""
echo "  Uninstall: curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --uninstall"
