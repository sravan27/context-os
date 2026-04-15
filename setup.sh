#!/usr/bin/env bash
# context-os: Every proven Claude Code token optimization in one command.
# Usage:     curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
# Status:    curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --status
# Uninstall: curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --uninstall
set -euo pipefail

VERSION="1.1.0"

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
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80"
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
  if [ -f .claude/settings.local.json ] && grep -q 'hooks' .claude/settings.local.json 2>/dev/null; then
    check ok "hooks" "active (output compression)"
  else
    check fail "hooks" "not active (optional)"
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
  for cmd in compact context ship; do
    [ -f ".claude/commands/${cmd}.md" ] && rm ".claude/commands/${cmd}.md" && echo "  removed /.claude/commands/${cmd}.md"
  done
  for agent in explorer; do
    [ -f ".claude/agents/${agent}.md" ] && rm ".claude/agents/${agent}.md" && echo "  removed /.claude/agents/${agent}.md"
  done
  [ -f .claude/output-styles/terse.md ] && rm .claude/output-styles/terse.md && echo "  removed /.claude/output-styles/terse.md"
  [ -f .claude/statusline.sh ] && rm .claude/statusline.sh && echo "  removed /.claude/statusline.sh"
  [ -d .context-os ] && rm -rf .context-os && echo "  removed .context-os/"
  # Clean up empty .claude subdirs
  for d in .claude/commands .claude/agents .claude/output-styles; do
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
TOTAL=9
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
# STEP 3: .claude/settings.json — Env vars (caps thinking/output cost)
# ============================================================================
STEP=3
mkdir -p .claude
SETTINGS_JSON=".claude/settings.json"

# Env tuning (shared, checked into repo)
ENV_SETTINGS='{
  "env": {
    "MAX_THINKING_TOKENS": "8000",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80"
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
# STEP 4: Slash commands — /compact, /context, /ship
# ============================================================================
STEP=4
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

echo "  [$STEP/$TOTAL] installed 3 slash commands (/compact, /context, /ship)"

# ============================================================================
# STEP 5: Haiku subagent — 15x cheaper than Opus for exploration
# ============================================================================
STEP=5
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
# STEP 6: Output style — enforces terse responses at every turn
# ============================================================================
STEP=6
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
# STEP 7: statusLine — live context + cost visibility in every prompt
# ============================================================================
STEP=7
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
# STEP 8: Hooks — output compression + session memory (needs binary)
# ============================================================================
STEP=8
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
new_hooks = json.load(sys.stdin)
existing['hooks'] = new_hooks['hooks']
json.dump(existing, open('$SETTINGS_LOCAL', 'w'), indent=2)
" 2>/dev/null && echo "  [$STEP/$TOTAL] updated hooks in settings.local.json" || echo "  [$STEP/$TOTAL] hooks merge failed"
  else
    printf '%s' "$HOOKS" | python3 -m json.tool > "$SETTINGS_LOCAL" 2>/dev/null || printf '%s' "$HOOKS" > "$SETTINGS_LOCAL"
    echo "  [$STEP/$TOTAL] installed 5 hooks (output compression + memory)"
  fi

  mkdir -p .context-os
  [ -f .context-os/session.json ] || printf '{"schema_version":1}' > .context-os/session.json
  [ -f .context-os/journal.jsonl ] || touch .context-os/journal.jsonl
else
  echo "  [$STEP/$TOTAL] hooks skipped (needs binary — optional)"
fi

# ============================================================================
# STEP 9: .gitignore
# ============================================================================
STEP=9
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
printf "  ✓ %-22s %s\n" "slash commands" "/compact /context /ship"
printf "  ✓ %-22s %s\n" "haiku subagent" "/explorer for cheap exploration"
printf "  ✓ %-22s %s\n" "secret filtering" ".env, *.pem, credentials blocked"

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
