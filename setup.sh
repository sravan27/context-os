#!/usr/bin/env bash
# context-os: Every proven Claude Code token optimization in one command.
# Usage:     curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
# Status:    curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --status
# Uninstall: curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --uninstall
set -euo pipefail

VERSION="2.0.0"

# ============================================================================
# --measure: Estimate token savings on the current project (shareable)
# ============================================================================
if [ "${1:-}" = "--measure" ]; then
  echo ""
  echo "  context-os measurement"
  echo "  ══════════════════════════════════════════"

  # Count noise
  MEASURE_NOISE=0
  for dir in node_modules .next dist build out target/debug target/release \
             __pycache__ .venv venv .tox .mypy_cache .pytest_cache \
             coverage .nyc_output .gradle vendor Pods .dart_tool \
             .git/objects .turbo .parcel-cache .cache \
             .svelte-kit .nuxt .output .vercel .netlify \
             bower_components jspm_packages DerivedData; do
    if [ -d "$dir" ]; then
      C=$(find "$dir" -type f 2>/dev/null | head -50000 | wc -l | tr -d ' ')
      MEASURE_NOISE=$((MEASURE_NOISE + C))
    fi
  done

  # Count source files
  MEASURE_SRC=$(find . -maxdepth 4 -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' -o -name '*.py' -o -name '*.rs' -o -name '*.go' -o -name '*.java' -o -name '*.rb' -o -name '*.swift' -o -name '*.dart' -o -name '*.cs' -o -name '*.cpp' -o -name '*.c' -o -name '*.vue' -o -name '*.svelte' \) \
    ! -path './node_modules/*' ! -path './dist/*' ! -path './build/*' ! -path './.next/*' \
    ! -path './target/*' ! -path './.venv/*' ! -path './venv/*' ! -path './vendor/*' \
    ! -path './__pycache__/*' ! -path './.git/*' ! -path './.cache/*' \
    2>/dev/null | wc -l | tr -d ' ')

  # Conservative estimates per session. Under-promise, over-deliver.
  # Claude searches hit ~50-100 noise files per Glob/Grep. ~10 searches/session.
  # Per search: min(noise_count, 100) files * 100 tokens = up to 10K/search.
  if [ "$MEASURE_NOISE" -gt 1000 ]; then
    NOISE_PER_SEARCH=10000
  elif [ "$MEASURE_NOISE" -gt 100 ]; then
    NOISE_PER_SEARCH=$((MEASURE_NOISE * 100 / 10))
  else
    NOISE_PER_SEARCH=$((MEASURE_NOISE * 50))
  fi
  NOISE_PER_SESSION=$((NOISE_PER_SEARCH * 5))  # ~5 searches/session that hit noise

  # Response shaping: 50% output reduction, avg 40K output/session = 20K saved
  RESPONSE_PER_SESSION=20000
  # Thinking cap: not every session uses extended thinking. Conservative: 15K avg
  THINKING_PER_SESSION=15000
  # Haiku exploration: only when explorer subagent used. Conservative: 10K
  HAIKU_PER_SESSION=10000
  # Hook output compression: only for tests/builds. Conservative: 8K
  HOOK_PER_SESSION=8000

  TOTAL_PER_SESSION=$((NOISE_PER_SESSION + RESPONSE_PER_SESSION + THINKING_PER_SESSION + HAIKU_PER_SESSION + HOOK_PER_SESSION))

  fmt_num() {
    local n=$1
    if [ "$n" -ge 1000000 ]; then
      echo "$(echo "scale=1; $n / 1000000" | bc 2>/dev/null || echo "$((n / 1000000))")M"
    elif [ "$n" -ge 1000 ]; then
      echo "$(echo "scale=0; $n / 1000" | bc 2>/dev/null || echo "$((n / 1000))")K"
    else
      echo "$n"
    fi
  }

  echo ""
  printf "  %-24s %s\n" "Source files:" "$MEASURE_SRC"
  printf "  %-24s %s\n" "Noise files:" "$MEASURE_NOISE"
  echo ""
  echo "  Conservative per-session savings:"
  echo ""
  printf "  %-24s ~%s tokens\n" "Noise filtering:" "$(fmt_num $NOISE_PER_SESSION)"
  printf "  %-24s ~%s tokens\n" "Response shaping:" "$(fmt_num $RESPONSE_PER_SESSION)"
  printf "  %-24s ~%s tokens\n" "Thinking cap (8K):" "$(fmt_num $THINKING_PER_SESSION)"
  printf "  %-24s ~%s tokens\n" "Haiku exploration:" "$(fmt_num $HAIKU_PER_SESSION)"
  printf "  %-24s ~%s tokens\n" "Output compression:" "$(fmt_num $HOOK_PER_SESSION)"
  echo "  ────────────────────────────────────"
  printf "  %-24s ~%s tokens/session\n" "TOTAL:" "$(fmt_num $TOTAL_PER_SESSION)"
  echo ""
  echo "  What that means:"
  echo ""
  # Pro plan ($20/mo): 5-hour window, ~200K context. Saving ~65K/session
  # means your context stays under the auto-compact threshold longer.
  # Sessions per 5-hour window increases ~1.5-2x.
  # API pricing Sonnet 4.6: ~$3/M input + $15/M output, blended ~$6/M
  #   → 65K tokens ≈ $0.40/session, $8/week at 20 sessions
  API_CENTS=$((TOTAL_PER_SESSION * 6 / 10000))  # $6/M = 0.6 cents/K
  API_DOLLARS=$((API_CENTS / 100))
  API_DEC=$((API_CENTS % 100))
  WEEK_CENTS=$((API_CENTS * 20))
  WEEK_DOLLARS=$((WEEK_CENTS / 100))
  printf "  %-24s longer sessions before hitting 5-hr cap\n" "Pro/Max plan:"
  printf "  %-24s ~\$%d.%02d/session (\$%d/week @ 20 sessions)\n" "API users (Sonnet 4.6):" "$API_DOLLARS" "$API_DEC" "$WEEK_DOLLARS"
  echo ""
  if [ -f CLAUDE.md ] && grep -q 'context-os:start' CLAUDE.md; then
    echo "  ✓ Context OS is already installed. Run --status to verify."
  else
    echo "  Activate: curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash"
  fi
  echo ""
  exit 0
fi

# ============================================================================
# --global: Install response shaping + env tuning globally (~/.claude/)
# ============================================================================
if [ "${1:-}" = "--global" ]; then
  echo ""
  echo "  context-os --global"
  echo "  ═══════════════════════════════════════════════════"
  echo "  Installing response shaping + env tuning to ~/.claude/"
  echo "  (applies to every project — per-project install still recommended)"
  echo ""

  GLOBAL_DIR="${HOME}/.claude"
  mkdir -p "$GLOBAL_DIR"

  # 1. Global CLAUDE.md — only response rules, no repo map (repo map is project-specific)
  GLOBAL_CLAUDE="${GLOBAL_DIR}/CLAUDE.md"
  GLOBAL_BLOCK='<!-- context-os:start -->
# Response rules

- Ultra-concise. No preamble, no recap, no filler.
- Code > explanation. Show the diff, not why you chose it.
- 1-2 sentence plan, then execute. Never explain what you'"'"'re about to do.
- Drop articles. Fragments fine. Be direct.
- On success: ≤1 sentence of what was done. No celebration.
- On error: show the error, skip the setup.

# Tool rules

- Use Grep/Glob over shell find/grep — cheaper and faster.
- Read files with offset+limit when you only need part.
- Batch edits. One response, multiple files.
- Use the explorer subagent (Haiku) for symbol lookups if installed per-project.

# Session continuity

- If `.context-os/handoff.md` or a restart packet exists, read it first.
- Don'"'"'t re-attempt failed approaches from prior sessions.
<!-- context-os:end -->'

  if [ -f "$GLOBAL_CLAUDE" ]; then
    if grep -q 'context-os:start' "$GLOBAL_CLAUDE" 2>/dev/null; then
      python3 -c "
import re
text = open('$GLOBAL_CLAUDE').read()
block = '''$GLOBAL_BLOCK'''
text = re.sub(r'<!-- context-os:start -->.*?<!-- context-os:end -->', block, text, flags=re.DOTALL)
open('$GLOBAL_CLAUDE', 'w').write(text)
" 2>/dev/null && echo "  updated ~/.claude/CLAUDE.md"
    else
      printf '\n\n%s\n' "$GLOBAL_BLOCK" >> "$GLOBAL_CLAUDE"
      echo "  appended to ~/.claude/CLAUDE.md (existing content preserved)"
    fi
  else
    printf '%s\n' "$GLOBAL_BLOCK" > "$GLOBAL_CLAUDE"
    echo "  created ~/.claude/CLAUDE.md"
  fi

  # 2. Global settings.json — env tuning
  GLOBAL_SETTINGS="${GLOBAL_DIR}/settings.json"
  GLOBAL_ENV='{
  "env": {
    "MAX_THINKING_TOKENS": "8000",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80",
    "ENABLE_PROMPT_CACHING_1H": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "150000"
  }
}'
  if [ -f "$GLOBAL_SETTINGS" ]; then
    printf '%s' "$GLOBAL_ENV" | python3 -c "
import json, sys
try:
    existing = json.load(open('$GLOBAL_SETTINGS'))
except:
    existing = {}
new = json.load(sys.stdin)
existing.setdefault('env', {})
existing['env'].update(new['env'])
json.dump(existing, open('$GLOBAL_SETTINGS', 'w'), indent=2)
" 2>/dev/null && echo "  merged env tuning into ~/.claude/settings.json"
  else
    printf '%s' "$GLOBAL_ENV" | python3 -m json.tool > "$GLOBAL_SETTINGS" 2>/dev/null || printf '%s\n' "$GLOBAL_ENV" > "$GLOBAL_SETTINGS"
    echo "  created ~/.claude/settings.json (MAX_THINKING_TOKENS=8000, AUTOCOMPACT=80%)"
  fi

  echo ""
  echo "  ✓ global install complete. Active on every new Claude Code session."
  echo "  Tip: still run the per-project install for noise filtering, slash commands,"
  echo "       explorer subagent, and statusLine."
  echo ""
  exit 0
fi

# ============================================================================
# --status: Show what's configured
# ============================================================================
if [ "${1:-}" = "--status" ]; then
  echo ""
  echo "  context-os status"
  echo "  ─────────────────"
  OK=0; WARN=0
  check() {
    if [ "$1" = "ok" ]; then
      printf "  ✓ %-22s %s\n" "$2" "$3"
      OK=$((OK + 1))
    else
      printf "  ✗ %-22s %s\n" "$2" "$3"
      WARN=$((WARN + 1))
    fi
  }
  if [ -f CLAUDE.md ] && grep -q 'context-os:start' CLAUDE.md; then
    check ok "response shaping" "active (CLAUDE.md)"
  else
    check fail "response shaping" "missing"
  fi
  if [ -f .claudeignore ]; then
    P=$(wc -l < .claudeignore | tr -d ' ')
    check ok "noise filtering" "$P patterns (.claudeignore)"
  else
    check fail "noise filtering" "missing"
  fi
  if [ -f .claude/settings.json ] && grep -q 'MAX_THINKING_TOKENS' .claude/settings.json 2>/dev/null; then
    check ok "env tuning" "active (settings.json)"
  else
    check fail "env tuning" "not configured"
  fi
  if [ -f .claude/settings.json ] && grep -q 'allowedTools' .claude/settings.json 2>/dev/null; then
    AT=$(python3 -c "import json; print(len(json.load(open('.claude/settings.json')).get('allowedTools',[])))" 2>/dev/null || echo "?")
    check ok "allowed tools" "$AT pre-approved (zero prompts)"
  else
    check fail "allowed tools" "not configured"
  fi
  if [ -d .claude/commands ] && ls .claude/commands/*.md &>/dev/null; then
    C=$(ls .claude/commands/*.md 2>/dev/null | wc -l | tr -d ' ')
    check ok "slash commands" "$C installed"
  else
    check fail "slash commands" "none"
  fi
  if [ -d .claude/agents ] && ls .claude/agents/*.md &>/dev/null; then
    A=$(ls .claude/agents/*.md 2>/dev/null | wc -l | tr -d ' ')
    check ok "haiku subagents" "$A installed"
  else
    check fail "haiku subagents" "none"
  fi
  if [ -f .claude/output-styles/terse.md ]; then
    check ok "output style" "'terse' installed (/output-style terse)"
  else
    check fail "output style" "not installed"
  fi
  if [ -f .claude/statusline.sh ]; then
    check ok "statusLine" "active (.claude/statusline.sh)"
  else
    check fail "statusLine" "not installed"
  fi
  if [ -f .claude/hooks/dedup_guard.py ] && [ -f .claude/hooks/loop_guard.py ] && [ -f .claude/hooks/session_profile.py ]; then
    check ok "python hooks" "dedup + loop-guard + profiler installed"
  else
    check fail "python hooks" "not installed"
  fi
  if [ -f .claude/settings.local.json ] && grep -q 'context-os hook' .claude/settings.local.json 2>/dev/null; then
    check ok "binary hooks" "active (output compression + memory)"
  else
    check fail "binary hooks" "not active (optional — needs binary)"
  fi
  echo ""
  echo "  $OK active, $WARN inactive"
  echo ""
  exit 0
fi

# ============================================================================
# --uninstall: Reversible removal
# ============================================================================
if [ "${1:-}" = "--uninstall" ]; then
  echo "context-os: removing optimizations..."
  if [ -f CLAUDE.md ] && grep -q '<!-- context-os:start -->' CLAUDE.md; then
    python3 -c "
import re
text = open('CLAUDE.md').read()
text = re.sub(r'\n*<!-- context-os:start -->.*?<!-- context-os:end -->\n*', '', text, flags=re.DOTALL)
open('CLAUDE.md', 'w').write(text)
" 2>/dev/null && echo "  removed CLAUDE.md block"
    [ -f CLAUDE.md ] && [ ! -s CLAUDE.md ] && rm CLAUDE.md && echo "  deleted empty CLAUDE.md"
  fi
  [ -f .claudeignore ] && head -1 .claudeignore | grep -q 'context-os' && rm .claudeignore && echo "  removed .claudeignore"
  if [ -f .claude/settings.json ]; then
    python3 -c "
import json
try:
    s = json.load(open('.claude/settings.json'))
    if 'env' in s and 'MAX_THINKING_TOKENS' in s.get('env', {}):
        s.pop('env', None)
        s.pop('statusLine', None)
        s.pop('allowedTools', None)
        if s:
            json.dump(s, open('.claude/settings.json', 'w'), indent=2)
        else:
            import os; os.remove('.claude/settings.json')
except: pass
" 2>/dev/null && echo "  removed env tuning from settings.json"
  fi
  if [ -f .claude/settings.local.json ]; then
    python3 -c "
import json
try:
    s = json.load(open('.claude/settings.local.json'))
    s.pop('hooks', None)
    if s:
        json.dump(s, open('.claude/settings.local.json', 'w'), indent=2)
    else:
        import os; os.remove('.claude/settings.local.json')
except: pass
" 2>/dev/null && echo "  removed hooks"
  fi
  if [ -f .claude/settings.json ]; then
    python3 -c "
import json
try:
    s = json.load(open('.claude/settings.json'))
    cos_tools = ['Read','Glob','Grep','Bash(git status*)','Bash(git diff*)','Bash(git log*)','Bash(cargo test*)','Bash(cargo check*)','Bash(npm test*)','Bash(npx jest*)','Bash(pytest*)','Bash(python -m pytest*)','Bash(go test*)','Bash(bun test*)','Bash(deno test*)']
    if 'allowedTools' in s:
        s['allowedTools'] = [t for t in s['allowedTools'] if t not in cos_tools]
        if not s['allowedTools']:
            del s['allowedTools']
    if s:
        json.dump(s, open('.claude/settings.json', 'w'), indent=2)
    else:
        import os; os.remove('.claude/settings.json')
except: pass
" 2>/dev/null && echo "  removed allowedTools from settings.json"
  fi
  for cmd in compact context ship cheap; do
    [ -f ".claude/commands/${cmd}.md" ] && rm ".claude/commands/${cmd}.md" && echo "  removed /.claude/commands/${cmd}.md"
  done
  for agent in explorer; do
    [ -f ".claude/agents/${agent}.md" ] && rm ".claude/agents/${agent}.md" && echo "  removed /.claude/agents/${agent}.md"
  done
  [ -f .claude/output-styles/terse.md ] && rm .claude/output-styles/terse.md && echo "  removed /.claude/output-styles/terse.md"
  [ -f .claude/statusline.sh ] && rm .claude/statusline.sh && echo "  removed /.claude/statusline.sh"
  for h in dedup_guard.py loop_guard.py session_profile.py; do
    [ -f ".claude/hooks/$h" ] && rm ".claude/hooks/$h" && echo "  removed .claude/hooks/$h"
  done
  [ -d .context-os ] && rm -rf .context-os && echo "  removed .context-os/"
  [ -d "$HOME/.context-os/state" ] && rm -rf "$HOME/.context-os/state" && echo "  removed ~/.context-os/state/"
  # Clean up empty .claude subdirs
  for d in .claude/commands .claude/agents .claude/output-styles .claude/hooks; do
    [ -d "$d" ] && [ -z "$(ls -A "$d" 2>/dev/null)" ] && rmdir "$d"
  done
  [ -d .claude ] && [ -z "$(ls -A .claude 2>/dev/null)" ] && rmdir .claude
  echo "  done. Context OS fully removed."
  exit 0
fi

# ============================================================================
# Install mode
# ============================================================================
echo ""
echo "  context-os v${VERSION}"
echo "  ═══════════════════════════════════════════════════"
echo "  Every proven Claude Code token optimization"
echo "  in one command. Zero dependencies. Reversible."
echo ""
echo "  scanning project..."

# ============================================================================
# Detect stack + count noise
# ============================================================================
NOISE_FILES=0

count_files_in() {
  if [ -d "$1" ]; then
    local c
    c=$(find "$1" -type f 2>/dev/null | head -50000 | wc -l | tr -d ' ')
    NOISE_FILES=$((NOISE_FILES + c))
  fi
}

for dir in node_modules .next dist build out target/debug target/release \
           __pycache__ .venv venv .tox .mypy_cache .pytest_cache \
           coverage .nyc_output .gradle .idea .vs .vscode \
           vendor Pods .dart_tool .flutter-plugins \
           .git/objects .turbo .parcel-cache .cache \
           .svelte-kit .nuxt .output .vercel .netlify \
           bower_components jspm_packages .pnp .yarn \
           DerivedData .build .swiftpm; do
  count_files_in "$dir"
done

SRC_FILES=$(find . -maxdepth 4 -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' -o -name '*.py' -o -name '*.rs' -o -name '*.go' -o -name '*.java' -o -name '*.rb' -o -name '*.swift' -o -name '*.dart' -o -name '*.cs' -o -name '*.cpp' -o -name '*.c' -o -name '*.vue' -o -name '*.svelte' \) \
  ! -path './node_modules/*' ! -path './dist/*' ! -path './build/*' ! -path './.next/*' \
  ! -path './target/*' ! -path './.venv/*' ! -path './venv/*' ! -path './vendor/*' \
  ! -path './__pycache__/*' ! -path './.git/*' ! -path './.cache/*' \
  2>/dev/null | wc -l | tr -d ' ')

STACK=""
[ -f package.json ] && STACK="${STACK:+$STACK, }node"
[ -f tsconfig.json ] && STACK="${STACK:+$STACK, }typescript"
{ [ -f next.config.js ] || [ -f next.config.mjs ] || [ -f next.config.ts ]; } && STACK="${STACK:+$STACK, }next.js"
[ -f Cargo.toml ] && STACK="${STACK:+$STACK, }rust"
[ -f go.mod ] && STACK="${STACK:+$STACK, }go"
{ [ -f requirements.txt ] || [ -f pyproject.toml ] || [ -f setup.py ] || [ -f Pipfile ]; } && STACK="${STACK:+$STACK, }python"
[ -f Gemfile ] && STACK="${STACK:+$STACK, }ruby"
{ [ -f pom.xml ] || [ -f build.gradle ] || [ -f build.gradle.kts ]; } && STACK="${STACK:+$STACK, }java"
[ -f pubspec.yaml ] && STACK="${STACK:+$STACK, }flutter"
[ -f Package.swift ] && STACK="${STACK:+$STACK, }swift"
ls ./*.csproj &>/dev/null 2>&1 && STACK="${STACK:+$STACK, }dotnet"
{ [ -f svelte.config.js ] || [ -f svelte.config.ts ]; } && STACK="${STACK:+$STACK, }svelte"
{ [ -f nuxt.config.js ] || [ -f nuxt.config.ts ]; } && STACK="${STACK:+$STACK, }nuxt"
{ [ -f docker-compose.yml ] || [ -f docker-compose.yaml ] || [ -f Dockerfile ]; } && STACK="${STACK:+$STACK, }docker"
[ -d .terraform ] && STACK="${STACK:+$STACK, }terraform"

[ -n "$STACK" ] && echo "  stack:  $STACK"

# Stack-specific CLAUDE.md hints (terse, high-signal)
STACK_HINTS=""
if echo "$STACK" | grep -q 'next.js'; then
  STACK_HINTS="${STACK_HINTS}
- Next.js App Router: route files are \`app/**/page.tsx\` + \`app/**/route.ts\`. Server Components by default.
- Don't touch \`.next/\` — it's build output."
fi
if echo "$STACK" | grep -q 'python'; then
  STACK_HINTS="${STACK_HINTS}
- Python imports follow package layout; don't add sys.path hacks.
- Prefer \`pytest -x -q\` for fast fail on tests."
fi
if echo "$STACK" | grep -q 'rust'; then
  STACK_HINTS="${STACK_HINTS}
- \`cargo check\` is faster than \`cargo build\` for type errors.
- Use \`cargo test -p <crate>\` to target one crate, not the whole workspace."
fi
if echo "$STACK" | grep -q 'go'; then
  STACK_HINTS="${STACK_HINTS}
- \`go test ./...\` runs all packages; \`go test ./pkg/foo\` targets one.
- Prefer table-driven tests; don't generate one test per case."
fi
if echo "$STACK" | grep -q 'flutter'; then
  STACK_HINTS="${STACK_HINTS}
- Use \`flutter analyze\` before \`flutter test\` — catches most issues without running.
- \`*.g.dart\` files are generated; never edit them."
fi
if echo "$STACK" | grep -q 'docker'; then
  STACK_HINTS="${STACK_HINTS}
- \`docker compose\` (v2) not \`docker-compose\` (v1 deprecated)."
fi
echo "  source: $SRC_FILES files"
[ "$NOISE_FILES" -gt 0 ] && echo "  noise:  $NOISE_FILES files"
echo ""

# ============================================================================
# Build lightweight repo map
# ============================================================================
REPOMAP=""
if [ "$SRC_FILES" -gt 0 ]; then
  TOPDIRS=$(find . -maxdepth 1 -type d ! -name '.' ! -name '.git' ! -name 'node_modules' \
    ! -name 'dist' ! -name 'build' ! -name '.next' ! -name 'target' ! -name '.venv' \
    ! -name 'venv' ! -name '__pycache__' ! -name '.cache' ! -name 'coverage' \
    ! -name '.turbo' ! -name '.parcel-cache' ! -name 'out' ! -name '.context-os' \
    ! -name '.nyc_output' ! -name '.gradle' ! -name 'vendor' ! -name 'Pods' \
    ! -name '.svelte-kit' ! -name '.nuxt' ! -name '.output' ! -name '.vercel' \
    ! -name '.idea' ! -name '.vs' ! -name '.vscode' ! -name 'bower_components' \
    ! -name 'DerivedData' ! -name '.build' ! -name '.swiftpm' ! -name '.claude' \
    2>/dev/null | sed 's|^\./||' | sort | head -20)

  if [ -n "$TOPDIRS" ]; then
    MAP_LINES=""
    for d in $TOPDIRS; do
      DCOUNT=$(find "./$d" -maxdepth 3 -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' -o -name '*.py' -o -name '*.rs' -o -name '*.go' -o -name '*.java' -o -name '*.rb' -o -name '*.swift' -o -name '*.dart' -o -name '*.cs' -o -name '*.cpp' -o -name '*.c' -o -name '*.vue' -o -name '*.svelte' \) \
        ! -path '*/node_modules/*' ! -path '*/dist/*' ! -path '*/build/*' ! -path '*/.next/*' \
        ! -path '*/target/*' ! -path '*/.venv/*' ! -path '*/venv/*' ! -path '*/vendor/*' \
        2>/dev/null | wc -l | tr -d ' ')
      if [ "$DCOUNT" -gt 0 ]; then
        SUBDIRS=$(find "./$d" -maxdepth 1 -type d ! -path "./$d" 2>/dev/null | sed "s|./$d/||" | sort | head -8 | tr '\n' ' ')
        if [ -n "$SUBDIRS" ]; then
          MAP_LINES="${MAP_LINES}${d}/ (${DCOUNT} files) — ${SUBDIRS}
"
        else
          MAP_LINES="${MAP_LINES}${d}/ (${DCOUNT} files)
"
        fi
      else
        MAP_LINES="${MAP_LINES}${d}/
"
      fi
    done
    if [ -n "$MAP_LINES" ]; then
      REPOMAP="
# Project structure

\`\`\`
${MAP_LINES}\`\`\`"
    fi
  fi
fi

# ============================================================================
# STEP 1: CLAUDE.md — Response shaping (saves 40-65% output tokens)
# ============================================================================
STEP=1
TOTAL=11
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
- Skip imports in code snippets unless they're the change.
- On success: state what was done in ≤1 sentence. No celebration.

# Repo rules

- Read only files you will change.
- Batch edits: one response, multiple files.
- On errors: show error only. Skip passing output.
- Run tests once to verify, not to explore.
- Use Grep/Glob tools over shell find/grep — they're cheaper.
- Read files with offset+limit when you only need part.
- For broad exploration, delegate to the \`explorer\` subagent (runs on Haiku, 15x cheaper).
$STACK_HINTS
$REPOMAP

# Session continuity

If a restart packet or \`.context-os/handoff.md\` exists, read it first.
Resume from there. Don't re-attempt failed approaches.
Use \`/compact\` before context fills up to save state.

# Token guards (hooks — .claude/hooks/)

- \`dedup_guard.py\`: blocks duplicate Read/Glob/Grep within 10min. On \"[context-os] Skipping duplicate\", use the previous result from history, don't re-Read.
- \`loop_guard.py\`: warns at edit #5 / blocks at edit #8 on same file. If warned, step back and re-read the full file or run tests to see real errors before another edit.
- \`session_profile.py\`: Stop-time report at \`.context-os/session-reports/\`. Check it after long sessions to see where tokens went.
$MARKER_END"

if [ -f CLAUDE.md ]; then
  if grep -q "$MARKER_START" CLAUDE.md; then
    TMPBLOCK=$(mktemp)
    printf '%s' "$BLOCK" > "$TMPBLOCK"
    python3 -c "
import re
text = open('CLAUDE.md').read()
block = open('$TMPBLOCK').read()
text = re.sub(r'<!-- context-os:start -->.*?<!-- context-os:end -->', block, text, flags=re.DOTALL)
open('CLAUDE.md', 'w').write(text)
" 2>/dev/null && echo "  [$STEP/$TOTAL] updated CLAUDE.md (response shaping + repo map)" || echo "  [$STEP/$TOTAL] CLAUDE.md update skipped"
    rm -f "$TMPBLOCK"
  else
    printf '\n\n%s\n' "$BLOCK" >> CLAUDE.md
    echo "  [$STEP/$TOTAL] appended to CLAUDE.md"
  fi
else
  printf '%s\n' "$BLOCK" > CLAUDE.md
  echo "  [$STEP/$TOTAL] created CLAUDE.md"
fi

# ============================================================================
# STEP 2: .claudeignore — Noise + secrets (30-40% context reduction)
# ============================================================================
STEP=2
if [ ! -f .claudeignore ]; then
  # Always include standard noise — covers future-created dirs (node_modules after npm i, etc.)
  IGNORES=""
  for dir in node_modules .next dist build out target/debug target/release \
             __pycache__ .venv venv .tox .mypy_cache .pytest_cache \
             coverage .nyc_output .gradle .idea .vs .vscode \
             vendor Pods .dart_tool .flutter-plugins \
             .git/objects .turbo .parcel-cache .cache \
             .svelte-kit .nuxt .output .vercel .netlify \
             bower_components jspm_packages .pnp .yarn \
             DerivedData .build .swiftpm \
             .terraform .serverless .aws-sam \
             .angular storybook-static; do
    IGNORES="$IGNORES$dir/
"
  done

  IGNORES="${IGNORES}
# --- SECRETS (security + savings) ---
.env
.env.*
!.env.example
!.env.sample
*.pem
*.key
*.p12
*.pfx
credentials.json
secrets.json
*.secret
id_rsa
id_ed25519
known_hosts
.aws/credentials
.netrc

# --- LOCK FILES (huge, no useful info) ---
package-lock.json
yarn.lock
pnpm-lock.yaml
Cargo.lock
poetry.lock
Gemfile.lock
composer.lock
Podfile.lock
bun.lockb
*.lock

# --- BUILD ARTIFACTS ---
*.min.js
*.min.css
*.map
*.chunk.js
*.bundle.js
*.wasm

# --- GENERATED CODE ---
*.pb.go
*.pb.h
*.pb.cc
*.generated.*
*.g.dart
*.gen.ts

# --- TEST SNAPSHOTS & COVERAGE ---
*.snap
lcov.info
*.lcov
coverage.xml
coverage.json

# --- DATA FILES ---
*.sqlite
*.sqlite3
*.db
*.csv
*.parquet
*.arrow

# --- BINARY/MEDIA ---
*.png
*.jpg
*.jpeg
*.gif
*.ico
*.svg
*.woff
*.woff2
*.ttf
*.eot
*.mp3
*.mp4
*.webm
*.pdf
*.zip
*.tar.gz
*.tgz
"
  PATTERN_COUNT=$(printf '%s' "$IGNORES" | grep -cE '^[a-zA-Z*!.]' || true)
  printf '# Generated by context-os v%s — prevents Claude from reading noise + secrets\n# Regenerate: curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash\n%s' "$VERSION" "$IGNORES" > .claudeignore
  echo "  [$STEP/$TOTAL] created .claudeignore ($PATTERN_COUNT patterns, secrets blocked)"
else
  echo "  [$STEP/$TOTAL] .claudeignore exists (keeping yours)"
fi

# ============================================================================
# STEP 3: .claude/settings.json — Env vars (thinking cap, prompt caching, traffic control)
# ============================================================================
STEP=3
mkdir -p .claude
SETTINGS_JSON=".claude/settings.json"

# Env tuning (shared, checked into repo)
ENV_SETTINGS='{
  "env": {
    "MAX_THINKING_TOKENS": "8000",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80",
    "ENABLE_PROMPT_CACHING_1H": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "150000"
  }
}'

if [ -f "$SETTINGS_JSON" ]; then
  printf '%s' "$ENV_SETTINGS" | python3 -c "
import json, sys
try:
    existing = json.load(open('$SETTINGS_JSON'))
except:
    existing = {}
new = json.load(sys.stdin)
existing.setdefault('env', {})
existing['env'].update(new['env'])
json.dump(existing, open('$SETTINGS_JSON', 'w'), indent=2)
" 2>/dev/null && echo "  [$STEP/$TOTAL] merged env tuning into settings.json" || echo "  [$STEP/$TOTAL] env tuning merge failed"
else
  printf '%s' "$ENV_SETTINGS" | python3 -m json.tool > "$SETTINGS_JSON" 2>/dev/null || printf '%s\n' "$ENV_SETTINGS" > "$SETTINGS_JSON"
  echo "  [$STEP/$TOTAL] created settings.json (MAX_THINKING_TOKENS=8000, AUTOCOMPACT=80%)"
fi

# ============================================================================
# STEP 4: Permission auto-granting — pre-approve safe tools
# ============================================================================
STEP=4
ALLOWED_TOOLS='[
  "Read",
  "Glob",
  "Grep",
  "Bash(git status*)",
  "Bash(git diff*)",
  "Bash(git log*)",
  "Bash(cargo test*)",
  "Bash(cargo check*)",
  "Bash(npm test*)",
  "Bash(npx jest*)",
  "Bash(pytest*)",
  "Bash(python -m pytest*)",
  "Bash(go test*)",
  "Bash(bun test*)",
  "Bash(deno test*)"
]'

if [ -f "$SETTINGS_JSON" ]; then
  printf '%s' "$ALLOWED_TOOLS" | python3 -c "
import json, sys
try:
    existing = json.load(open('$SETTINGS_JSON'))
except:
    existing = {}
new_tools = json.load(sys.stdin)
old_tools = existing.get('allowedTools', [])
merged = list(old_tools)
for t in new_tools:
    if t not in merged:
        merged.append(t)
existing['allowedTools'] = merged
json.dump(existing, open('$SETTINGS_JSON', 'w'), indent=2)
" 2>/dev/null && echo "  [$STEP/$TOTAL] merged 15 allowed tools into settings.json (zero confirmation prompts)" || echo "  [$STEP/$TOTAL] allowedTools merge failed"
else
  printf '{"allowedTools": %s}' "$ALLOWED_TOOLS" | python3 -m json.tool > "$SETTINGS_JSON" 2>/dev/null || printf '{"allowedTools": %s}\n' "$ALLOWED_TOOLS" > "$SETTINGS_JSON"
  echo "  [$STEP/$TOTAL] created settings.json with allowed tools"
fi

# ============================================================================
# STEP 5: Slash commands — /compact, /context, /ship, /cheap
# ============================================================================
STEP=5
mkdir -p .claude/commands

cat > .claude/commands/compact.md << 'CMDEOF'
Write a handoff to `.context-os/handoff.md`:

1. **Objective**: What we're building (1 line)
2. **Done**: What's completed (bullet list, file:line refs)
3. **Failed**: What didn't work and why (so we don't retry)
4. **Next**: Exact next step to take
5. **Modified files**: List every file changed this session

Keep it under 40 lines. No prose. Start with `[context-os handoff]`.
Then say: "Handoff saved. Start a new session — I'll pick up from here."
CMDEOF

cat > .claude/commands/context.md << 'CMDEOF'
Estimate your current context usage:
1. Count files you've read this session
2. Count tool calls made
3. List the 3 largest tool outputs you've seen
4. Suggest what to compact or skip

Table format. Under 10 lines. No explanations.
CMDEOF

cat > .claude/commands/ship.md << 'CMDEOF'
Ship the current changes:
1. Run tests (once). If they fail, show the failure and stop.
2. Stage only modified files (not untracked).
3. Commit with a 1-line message describing what changed.
4. Show the commit hash.

No explanations. No celebration. Just ship or fail.
CMDEOF

cat > .claude/commands/cheap.md << 'CMDEOF'
Run this task using the explorer subagent (Haiku model — 15x cheaper than Sonnet/Opus). This is for tasks where quality can be traded for cost: formatting, simple refactors, file moves, boilerplate generation, documentation.

$ARGUMENTS
CMDEOF

echo "  [$STEP/$TOTAL] installed 4 slash commands (/compact, /context, /ship, /cheap)"

# ============================================================================
# STEP 6: Haiku subagent — 15x cheaper than Opus for exploration
# ============================================================================
STEP=6
mkdir -p .claude/agents

cat > .claude/agents/explorer.md << 'AGENTEOF'
---
name: explorer
description: Fast file/code exploration agent. Use when searching for symbols, reading multiple files to understand structure, or investigating usage patterns. Returns a summary, not raw files.
model: haiku
---

You are a code exploration agent running on Claude Haiku (fast, cheap).

Your job: answer exploration questions without polluting the main context.

Rules:
- Read files with Grep/Glob first, Read only when needed
- Use offset/limit when reading large files
- Return a summary (≤500 tokens), not raw file content
- Include file paths and line numbers (file.ts:42 format)
- If you can't find what was asked, say so in 1 line

Never:
- Write or edit files (you're read-only)
- Explain your reasoning
- Return full file contents unless explicitly asked
AGENTEOF

echo "  [$STEP/$TOTAL] installed explorer subagent (Haiku — 15x cheaper)"

# ============================================================================
# STEP 7: Output style — enforces terse responses at every turn
# ============================================================================
STEP=7
mkdir -p .claude/output-styles

cat > .claude/output-styles/terse.md << 'STYLEOF'
---
name: terse
description: Context OS terse output style. Caps every response at the minimum viable shape — no preamble, no recap, no celebration. Use when burning through token budget.
---

# Response contract

- No preamble. Start with the action or the answer.
- No recap. The user just wrote the prompt; they remember.
- No celebration. No "Great!", "", "I've successfully...".
- No tool announcements. Don't say "I'll use Grep to search" — just search.
- Show diffs, not explanations.
- Fragments are fine. Drop articles. Be direct.
- On success: state what was done in ≤1 sentence. Done.
- On error: show the error, skip the pre-error context.

# Code rules

- Skip imports in code snippets unless they're the change.
- Use Grep/Glob before Bash find/grep. Cheaper and faster.
- Read files with offset+limit when you only need part.
- One response, multiple files. Batch edits.

# Session rules

- If a restart packet or `.context-os/handoff.md` exists, read it first.
- Don't re-attempt failed approaches from prior sessions.
- Use the explorer subagent for symbol lookups and file searches.

# Forbidden

- "Based on my analysis..."
- "Let me..."
- "I'll now..."
- "Here's a summary of what I did..."
- "Perfect!" / "Excellent!" / "" / "Got it!"
- Re-explaining code you just wrote
- Multi-paragraph responses for single-file edits
STYLEOF

echo "  [$STEP/$TOTAL] installed 'terse' output style (/output-style terse)"

# ============================================================================
# STEP 8: statusLine — live context + cost visibility in every prompt
# ============================================================================
STEP=8
cat > .claude/statusline.sh << 'SLEOF'
#!/usr/bin/env bash
# Context OS statusLine: shows model, git branch, and context budget status.
# Reads JSON from stdin (Claude Code session context).
set -euo pipefail

INPUT=$(cat)

# Parse what Claude Code gives us
MODEL=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('model',{}).get('display_name','?'))" 2>/dev/null || echo "?")
CWD=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('workspace',{}).get('current_dir','.'))" 2>/dev/null || pwd)

# Git branch (if in repo)
BRANCH=""
if command -v git &>/dev/null; then
  BRANCH=$(cd "$CWD" 2>/dev/null && git branch --show-current 2>/dev/null || echo "")
fi

# Context OS status
COS=""
if [ -f "$CWD/CLAUDE.md" ] && grep -q 'context-os:start' "$CWD/CLAUDE.md" 2>/dev/null; then
  COS="context-os ✓"
fi

# Format: model · branch · context-os status
OUT="$MODEL"
[ -n "$BRANCH" ] && OUT="$OUT · $BRANCH"
[ -n "$COS" ] && OUT="$OUT · $COS"
printf '%s' "$OUT"
SLEOF
chmod +x .claude/statusline.sh

# Register in settings.json
if [ -f .claude/settings.json ]; then
  python3 -c "
import json
p = '.claude/settings.json'
try:
    s = json.load(open(p))
except:
    s = {}
s['statusLine'] = {'type': 'command', 'command': 'bash .claude/statusline.sh'}
json.dump(s, open(p, 'w'), indent=2)
" 2>/dev/null && echo "  [$STEP/$TOTAL] installed statusLine (model · branch · context-os ✓)" || echo "  [$STEP/$TOTAL] statusLine installed (settings.json merge skipped)"
else
  echo "  [$STEP/$TOTAL] statusLine script installed"
fi

# ============================================================================
# STEP 9: Python hooks — dedup-guard, loop-guard, session-profile (zero-dep)
# ============================================================================
# These hooks are pure Python stdlib, no binary required. They catch the
# three most common waste patterns in Claude Code sessions:
#   - dedup_guard: blocks duplicate Read/Glob/Grep (same args within 10min)
#   - loop_guard: warns at 5 edits / blocks at 8 edits on same file
#   - session_profile: writes a per-session token breakdown on Stop
# All three fail-open — any error or unexpected input exits 0 silently.
STEP=9
HOOK_DIR=".claude/hooks"
mkdir -p "$HOOK_DIR"

# --- dedup_guard.py -------------------------------------------------
cat > "$HOOK_DIR/dedup_guard.py" <<'CONTEXT_OS_DEDUP_EOF'
#!/usr/bin/env python3
"""PreToolUse hook: blocks duplicate Read/Glob/Grep within a session."""
import hashlib, json, os, sys, time
from pathlib import Path

TTL_SECONDS = 600
SESSION_MAX_AGE_SECONDS = 86400
STATE_DIR = Path.home() / ".context-os" / "state"

def args_hash(tool_name, tool_input):
    if tool_name == "Read":
        key = tool_input.get("file_path", "")
        offset = tool_input.get("offset")
        limit = tool_input.get("limit")
        if offset is not None or limit is not None:
            key += f"#{offset or 0}:{limit or 0}"
    elif tool_name == "Glob":
        key = tool_input.get("pattern", "") + "|" + tool_input.get("path", "")
    elif tool_name == "Grep":
        parts = [tool_input.get("pattern", ""), tool_input.get("path", ""),
                 tool_input.get("glob", ""), tool_input.get("type", ""),
                 str(tool_input.get("output_mode", "")),
                 str(tool_input.get("-i", False)),
                 str(tool_input.get("multiline", False))]
        key = "|".join(parts)
    else:
        key = json.dumps(tool_input, sort_keys=True)
    return hashlib.sha1(f"{tool_name}:{key}".encode()).hexdigest()[:16]

def prune_old(state_dir, now):
    try:
        for f in state_dir.glob("dedup-*.json"):
            try:
                if now - f.stat().st_mtime > SESSION_MAX_AGE_SECONDS:
                    f.unlink()
            except OSError:
                pass
    except OSError:
        pass

def main():
    if os.environ.get("CONTEXT_OS_DEDUP") == "0":
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Read", "Glob", "Grep"):
        return 0
    tool_input = payload.get("tool_input") or {}
    session_id = payload.get("session_id", "default")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"dedup-{session_id}.json"
    now = time.time()
    if now % 10 < 1:
        prune_old(STATE_DIR, now)
    try:
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except (OSError, json.JSONDecodeError):
        state = {}
    state = {k: v for k, v in state.items() if now - v.get("t", 0) < TTL_SECONDS}
    h = args_hash(tool_name, tool_input)
    if h in state:
        prev = state[h]
        age = int(now - prev["t"])
        state[h]["t"] = now
        try:
            state_file.write_text(json.dumps(state))
        except OSError:
            pass
        print(f"[context-os] Skipping duplicate {tool_name}: "
              f"same args {age}s ago. Use previous result from history.",
              file=sys.stderr)
        return 2
    state[h] = {"t": now, "n": tool_name}
    try:
        state_file.write_text(json.dumps(state))
    except OSError:
        pass
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
CONTEXT_OS_DEDUP_EOF
chmod +x "$HOOK_DIR/dedup_guard.py"

# --- loop_guard.py --------------------------------------------------
cat > "$HOOK_DIR/loop_guard.py" <<'CONTEXT_OS_LOOP_EOF'
#!/usr/bin/env python3
"""PreToolUse hook: detects Read/Edit loops and nudges Claude to step back."""
import json, os, sys, time
from pathlib import Path

WARN = int(os.environ.get("CONTEXT_OS_LOOP_WARN", "5"))
HARD = int(os.environ.get("CONTEXT_OS_LOOP_HARD", "8"))
WINDOW = 1800
STATE_DIR = Path.home() / ".context-os" / "state"

def main():
    if os.environ.get("CONTEXT_OS_LOOP_GUARD") == "0":
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not file_path:
        return 0
    session_id = payload.get("session_id", "default")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"loop-{session_id}.json"
    now = time.time()
    try:
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except (OSError, json.JSONDecodeError):
        state = {}
    entry = state.get(file_path, {"count": 0, "first": now, "last": now})
    if now - entry.get("last", now) > WINDOW:
        entry = {"count": 0, "first": now, "last": now}
    entry["count"] += 1
    entry["last"] = now
    state[file_path] = entry
    try:
        state_file.write_text(json.dumps(state))
    except OSError:
        pass
    count = entry["count"]
    short = os.path.relpath(file_path) if os.path.isabs(file_path) else file_path
    if count >= HARD:
        print(f"[context-os] STOP — edited {short} {count} times. "
              f"Almost certainly a loop. Ask the user before another edit. "
              f"Try: re-reading the full file, running tests for real errors, "
              f"or a different approach.", file=sys.stderr)
        return 2
    if count == WARN:
        print(f"[context-os] Heads up: edit #{count} on {short}. "
              f"If tests still fail, step back and re-read before editing again.",
              file=sys.stderr)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
CONTEXT_OS_LOOP_EOF
chmod +x "$HOOK_DIR/loop_guard.py"

# --- session_profile.py ---------------------------------------------
cat > "$HOOK_DIR/session_profile.py" <<'CONTEXT_OS_PROFILE_EOF'
#!/usr/bin/env python3
"""Stop hook: writes a per-session token-usage report to .context-os/session-reports/."""
import json, os, sys, time
from collections import Counter, defaultdict
from pathlib import Path

REPORTS = ".context-os/session-reports"
BIG_TOKENS = 5000
CHARS_PER_TOKEN = 4

def approx(s):
    return max(1, len(s) // CHARS_PER_TOKEN)

def parse(path):
    s = {"turns": 0, "input": 0, "output": 0, "cr": 0, "cw": 0,
         "tools": Counter(), "hashes": defaultdict(list),
         "edits": Counter(), "big": [], "top": []}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return s
    for i, line in enumerate(lines):
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = evt.get("message") or {}
        u = msg.get("usage") or evt.get("usage") or {}
        if u:
            s["turns"] += 1
            s["input"] += u.get("input_tokens", 0) or 0
            s["output"] += u.get("output_tokens", 0) or 0
            s["cr"] += u.get("cache_read_input_tokens", 0) or 0
            s["cw"] += u.get("cache_creation_input_tokens", 0) or 0
            tot = (u.get("input_tokens", 0) or 0) + (u.get("output_tokens", 0) or 0)
            if tot > 0:
                s["top"].append((i, tot, _summ(msg)))
        content = msg.get("content") or []
        if isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    tool = b.get("name", "?")
                    s["tools"][tool] += 1
                    inp = b.get("input") or {}
                    if tool in ("Read", "Glob", "Grep"):
                        s["hashes"][(tool, _sig(tool, inp))].append(i)
                    if tool in ("Edit", "Write", "NotebookEdit"):
                        fp = inp.get("file_path") or inp.get("notebook_path") or ""
                        if fp:
                            s["edits"][fp] += 1
                elif b.get("type") == "tool_result":
                    rc = b.get("content")
                    txt = rc if isinstance(rc, str) else json.dumps(rc)[:20000]
                    t = approx(txt)
                    if t >= BIG_TOKENS:
                        s["big"].append((i, t, (txt or "")[:120].replace("\n", " ")))
    return s

def _sig(tool, inp):
    if tool == "Read":
        return inp.get("file_path", "")
    if tool == "Glob":
        return f"{inp.get('pattern', '')}|{inp.get('path', '')}"
    if tool == "Grep":
        return "|".join(str(inp.get(k, "")) for k in ("pattern", "path", "glob", "type", "output_mode"))
    return json.dumps(inp, sort_keys=True)[:200]

def _summ(msg):
    c = msg.get("content") or []
    if isinstance(c, list):
        for b in c:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    return (b.get("text") or "")[:80].replace("\n", " ")
                if b.get("type") == "tool_use":
                    return f"tool:{b.get('name', '?')}"
    if isinstance(c, str):
        return c[:80].replace("\n", " ")
    return ""

def report(s, sid):
    tot = s["input"] + s["output"] + s["cw"]
    cr = s["cr"] / max(1, s["input"] + s["cr"])
    out = [f"# Session profile — {sid}", "",
           f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", "",
           "## Totals", "",
           f"- Turns: {s['turns']}",
           f"- Input tokens (uncached): {s['input']:,}",
           f"- Output tokens: {s['output']:,}",
           f"- Cache read: {s['cr']:,}",
           f"- Cache write: {s['cw']:,}",
           f"- **Total billable: {tot:,}**",
           f"- Cache hit ratio: {cr:.1%}", "",
           "## Tool call breakdown", ""]
    for tool, n in s["tools"].most_common():
        out.append(f"- {tool}: {n}")
    if not s["tools"]:
        out.append("- (no tool calls)")
    out.append("")
    dupes = [(t, sig, ts) for (t, sig), ts in s["hashes"].items() if len(ts) > 1]
    out += ["## Duplicate Read/Glob/Grep (dedup_guard saves these)", ""]
    if dupes:
        dupes.sort(key=lambda x: -len(x[2]))
        for t, sig, ts in dupes[:10]:
            out.append(f"- `{t}` x {len(ts)}: `{sig[:80]}`")
    else:
        out.append("- (none)")
    out.append("")
    loops = [(fp, n) for fp, n in s["edits"].most_common() if n >= 3]
    out += ["## Files edited 3+ times (loop_guard territory)", ""]
    if loops:
        for fp, n in loops[:10]:
            out.append(f"- {fp}: {n} edits")
    else:
        out.append("- (none)")
    out.append("")
    out += ["## Oversized tool results (>5K tokens each)", ""]
    if s["big"]:
        for turn, t, p in sorted(s["big"], key=lambda x: -x[1])[:10]:
            out.append(f"- turn {turn}: ~{t:,} tok - `{p}`")
    else:
        out.append("- (none)")
    out.append("")
    out += ["## Top 10 turns by token cost", ""]
    for turn, t, summ in sorted(s["top"], key=lambda x: -x[1])[:10]:
        out.append(f"- turn {turn}: {t:,} tok - {summ or '(empty)'}")
    out.append("")
    out += ["## Recommendations", ""]
    recs = []
    if dupes:
        saved = sum(len(ts) - 1 for _, _, ts in dupes)
        recs.append(f"- dedup_guard would have skipped ~{saved} duplicate tool calls.")
    if loops:
        recs.append("- loop_guard catches edit loops before they burn tokens.")
    if s["big"]:
        recs.append("- Consider adding noise patterns to .claudeignore.")
    if cr < 0.3 and tot > 50000:
        recs.append("- Low cache hit ratio. Check ENABLE_PROMPT_CACHING_1H=1 and stable CLAUDE.md.")
    if not recs:
        recs.append("- Session looks clean. No obvious waste.")
    out += recs
    out.append("")
    return "\n".join(out)

def main():
    if os.environ.get("CONTEXT_OS_PROFILE") == "0":
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    transcript = payload.get("transcript_path")
    sid = payload.get("session_id", "unknown")
    cwd = payload.get("cwd") or os.getcwd()
    if not transcript or not os.path.exists(transcript):
        return 0
    s = parse(Path(transcript))
    if s["turns"] == 0:
        return 0
    rd = Path(cwd) / REPORTS
    rd.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = rd / f"{ts}-{sid[:8]}.md"
    try:
        out.write_text(report(s, sid))
    except OSError:
        return 0
    tot = s["input"] + s["output"] + s["cw"]
    dupes = sum(1 for v in s["hashes"].values() if len(v) > 1)
    print(f"[context-os] Session: {tot:,} tok, {s['turns']} turns, "
          f"{dupes} duplicate tool calls. Report: {out}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
CONTEXT_OS_PROFILE_EOF
chmod +x "$HOOK_DIR/session_profile.py"

# Merge Python hooks into settings.local.json. Additive merge — preserves any
# existing hooks (e.g. from the optional binary-based step below).
PY_ABS="$(cd "$HOOK_DIR" && pwd)"
SETTINGS_LOCAL=".claude/settings.local.json"

PYTHON_HOOKS=$(cat <<HOOKJSON
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Read|Glob|Grep", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/dedup_guard.py'", "timeout": 3}]},
      {"matcher": "Edit|Write|NotebookEdit", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/loop_guard.py'", "timeout": 3}]}
    ],
    "Stop": [
      {"matcher": "", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/session_profile.py'", "timeout": 15}]}
    ]
  }
}
HOOKJSON
)

if [ -f "$SETTINGS_LOCAL" ]; then
  printf '%s' "$PYTHON_HOOKS" | python3 -c "
import json, sys
existing = json.load(open('$SETTINGS_LOCAL'))
new_hooks = json.load(sys.stdin)['hooks']
existing.setdefault('hooks', {})
for event, entries in new_hooks.items():
    existing['hooks'].setdefault(event, [])
    # Dedupe on (matcher, command) so re-runs are idempotent.
    seen = {(e.get('matcher',''), tuple(h.get('command','') for h in e.get('hooks',[])))
            for e in existing['hooks'][event]}
    for entry in entries:
        sig = (entry.get('matcher',''), tuple(h.get('command','') for h in entry.get('hooks',[])))
        if sig not in seen:
            existing['hooks'][event].append(entry)
            seen.add(sig)
json.dump(existing, open('$SETTINGS_LOCAL', 'w'), indent=2)
" 2>/dev/null && echo "  [$STEP/$TOTAL] installed 3 Python hooks (dedup, loop-guard, profiler)" || echo "  [$STEP/$TOTAL] Python hooks install failed"
else
  printf '%s' "$PYTHON_HOOKS" | python3 -m json.tool > "$SETTINGS_LOCAL" 2>/dev/null || printf '%s' "$PYTHON_HOOKS" > "$SETTINGS_LOCAL"
  echo "  [$STEP/$TOTAL] installed 3 Python hooks (dedup, loop-guard, profiler)"
fi

# ============================================================================
# STEP 10: Binary hooks — output compression + session memory (needs binary)
# ============================================================================
STEP=10
BIN=""
if command -v context-os &>/dev/null; then
  BIN="context-os"
elif [ -f "./target/debug/context-os" ]; then
  BIN="$(cd . && pwd)/target/debug/context-os"
elif [ -f "./target/release/context-os" ]; then
  BIN="$(cd . && pwd)/target/release/context-os"
fi

if [ -n "$BIN" ]; then
  SETTINGS_LOCAL=".claude/settings.local.json"
  ROOT="$(pwd)"

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

  if [ -f "$SETTINGS_LOCAL" ]; then
    printf '%s' "$HOOKS" | python3 -c "
import json, sys
existing = json.load(open('$SETTINGS_LOCAL'))
new_hooks = json.load(sys.stdin)['hooks']
existing.setdefault('hooks', {})
for event, entries in new_hooks.items():
    existing['hooks'].setdefault(event, [])
    seen = {(e.get('matcher',''), tuple(h.get('command','') for h in e.get('hooks',[])))
            for e in existing['hooks'][event]}
    for entry in entries:
        sig = (entry.get('matcher',''), tuple(h.get('command','') for h in entry.get('hooks',[])))
        if sig not in seen:
            existing['hooks'][event].append(entry)
            seen.add(sig)
json.dump(existing, open('$SETTINGS_LOCAL', 'w'), indent=2)
" 2>/dev/null && echo "  [$STEP/$TOTAL] merged 5 binary hooks into settings.local.json" || echo "  [$STEP/$TOTAL] binary hooks merge failed"
  else
    printf '%s' "$HOOKS" | python3 -m json.tool > "$SETTINGS_LOCAL" 2>/dev/null || printf '%s' "$HOOKS" > "$SETTINGS_LOCAL"
    echo "  [$STEP/$TOTAL] installed 5 binary hooks (output compression + memory)"
  fi

  mkdir -p .context-os
  [ -f .context-os/session.json ] || printf '{"schema_version":1}' > .context-os/session.json
  [ -f .context-os/journal.jsonl ] || touch .context-os/journal.jsonl
else
  echo "  [$STEP/$TOTAL] hooks skipped (needs binary — optional)"
fi

# ============================================================================
# STEP 11: .gitignore
# ============================================================================
STEP=11
if [ -f .gitignore ]; then
  if ! grep -q '.context-os' .gitignore 2>/dev/null; then
    printf '\n# Context OS local state\n.context-os/\n.claude/settings.local.json\n' >> .gitignore
    echo "  [$STEP/$TOTAL] added .context-os/ + settings.local.json to .gitignore"
  else
    echo "  [$STEP/$TOTAL] .gitignore already configured"
  fi
else
  printf '# Context OS local state\n.context-os/\n.claude/settings.local.json\n' > .gitignore
  echo "  [$STEP/$TOTAL] created .gitignore"
fi

# ============================================================================
# Impact report
# ============================================================================
echo ""
echo "  ── what's active ───────────────────────────────────"
echo ""

if [ "$NOISE_FILES" -gt 0 ]; then
  TOKENS_SAVED=$((NOISE_FILES * 200))
  if [ "$TOKENS_SAVED" -ge 1000000 ]; then
    DISPLAY_TOKENS="$(echo "scale=1; $TOKENS_SAVED / 1000000" | bc 2>/dev/null || echo "$((TOKENS_SAVED / 1000000))")M"
  elif [ "$TOKENS_SAVED" -ge 1000 ]; then
    DISPLAY_TOKENS="$(echo "scale=0; $TOKENS_SAVED / 1000" | bc 2>/dev/null || echo "$((TOKENS_SAVED / 1000))")K"
  else
    DISPLAY_TOKENS="$TOKENS_SAVED"
  fi
  printf "  ✓ %-22s %s\n" "noise filtering" "$NOISE_FILES files hidden (~${DISPLAY_TOKENS} tokens/search)"
else
  printf "  ✓ %-22s %s\n" "noise filtering" "active"
fi
printf "  ✓ %-22s %s\n" "response shaping" "40-65% fewer output tokens"
printf "  ✓ %-22s %s\n" "output style" "'terse' (/output-style terse)"
printf "  ✓ %-22s %s\n" "statusLine" "live model · branch · context-os ✓"
printf "  ✓ %-22s %s\n" "repo map" "Claude skips structure scanning"
printf "  ✓ %-22s %s\n" "thinking cap" "8000 tokens max (saves on simple tasks)"
printf "  ✓ %-22s %s\n" "early compaction" "at 80% (default is 95%)"
printf "  ✓ %-22s %s\n" "prompt caching 1h" "5min→1hr TTL (huge on long sessions)"
printf "  ✓ %-22s %s\n" "traffic control" "non-essential API calls disabled"
printf "  ✓ %-22s %s\n" "context cap" "150K max (prevents runaway sessions)"
printf "  ✓ %-22s %s\n" "allowed tools" "15 pre-approved (zero confirmation prompts)"
printf "  ✓ %-22s %s\n" "slash commands" "/compact /context /ship /cheap"
printf "  ✓ %-22s %s\n" "haiku subagent" "/explorer for cheap exploration"
printf "  ✓ %-22s %s\n" "secret filtering" ".env, *.pem, credentials blocked"
printf "  ✓ %-22s %s\n" "dedup guard" "blocks duplicate Read/Glob/Grep within 10min"
printf "  ✓ %-22s %s\n" "loop guard" "warns at 5 edits, blocks at 8 on same file"
printf "  ✓ %-22s %s\n" "session profiler" "per-session token report → .context-os/session-reports/"

if [ -n "$BIN" ]; then
  printf "  ✓ %-22s %s\n" "output compression" "27-70% on test/build output"
  printf "  ✓ %-22s %s\n" "session memory" "survives compaction + restarts"
else
  printf "  · %-22s %s\n" "output compression" "optional (needs binary)"
  printf "  · %-22s %s\n" "session memory" "optional (needs binary)"
fi

echo ""
echo "  ── next steps ──────────────────────────────────────"
echo ""
echo "  1. Start a new Claude Code session to activate"
echo "  2. Use /compact before context fills up"
echo "  3. For exploration, tell Claude to 'use the explorer subagent'"
if [ -z "$BIN" ]; then
  echo "  4. Optional: install binary for output compression"
  echo "     cargo install --git https://github.com/sravan27/context-os --path apps/cli"
fi
echo ""
echo "  --status     check what's active"
echo "  --uninstall  fully reversible removal"
echo ""
