#!/usr/bin/env bash
# context-os: Every proven Claude Code token optimization in one command.
# Usage:     curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
# Status:    curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --status
# Uninstall: curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --uninstall
set -euo pipefail

VERSION="2.10.0"

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
  if [ -f .claude/hooks/dedup_guard.py ] && [ -f .claude/hooks/loop_guard.py ] && [ -f .claude/hooks/file_size_guard.py ] && [ -f .claude/hooks/session_profile.py ] && [ -f .claude/hooks/auto_context.py ] && [ -f .claude/hooks/prewarm.py ]; then
    check ok "python hooks" "8 installed (dedup, loop, size, smartread, profiler, autocontext, prewarm, savings)"
  else
    check fail "python hooks" "not fully installed"
  fi
  if [ -f .context-os/repo-graph.json ] && [ -f .context-os/build_repo_graph.py ]; then
    GSTAT=$(python3 -c "import json; g=json.load(open('.context-os/repo-graph.json')); print(f\"{g['file_count']}f / {g['symbol_count']}sym\")" 2>/dev/null || echo "present")
    check ok "repo graph" "$GSTAT (.context-os/repo-graph.json)"
  else
    check fail "repo graph" "not built"
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
  for cmd in compact context ship cheap find deps hot warm-clear relevant insights rebuild-graph savings outline; do
    [ -f ".claude/commands/${cmd}.md" ] && rm ".claude/commands/${cmd}.md" && echo "  removed /.claude/commands/${cmd}.md"
  done
  for agent in explorer; do
    [ -f ".claude/agents/${agent}.md" ] && rm ".claude/agents/${agent}.md" && echo "  removed /.claude/agents/${agent}.md"
  done
  [ -f .claude/output-styles/terse.md ] && rm .claude/output-styles/terse.md && echo "  removed /.claude/output-styles/terse.md"
  [ -f .claude/statusline.sh ] && rm .claude/statusline.sh && echo "  removed /.claude/statusline.sh"
  for h in dedup_guard.py loop_guard.py file_size_guard.py smart_read.py session_profile.py auto_context.py prewarm.py savings_tracker.py; do
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
# STEP 1: Repo graph — symbol index + imports + hot files (no grep)
# ============================================================================
# Generates .context-os/repo-graph.json: per-file top-level symbols, import
# edges, and hot files from `git log`. Queried by the /find, /deps, /hot
# slash commands (no grep of user files). Pure stdlib regex — no LSP, no
# tree-sitter, no external deps. Rebuild any time:
#     python3 .context-os/build_repo_graph.py .
STEP=1
TOTAL=12
mkdir -p .context-os

cat > .context-os/build_repo_graph.py <<'CONTEXT_OS_GRAPH_EOF'
#!/usr/bin/env python3
"""
build_repo_graph.py — Context OS repo graph generator.

Zero-dependency (stdlib only) walker that extracts:
- Top-level symbols per source file (Rust, Python, JS, TS, Go)
- Import edges (who imports whom)
- Hot files from git log (change frequency, last 90 days)

Writes `.context-os/repo-graph.json` and prints a short markdown summary to
stdout for setup.sh to embed into CLAUDE.md. Runs in a few hundred ms on
most repos; skips node_modules/target/dist/etc. automatically.

Invoked:
    python3 build_repo_graph.py [repo_root]

Exit 0 always. Failure to parse any file is silent (partial graphs are fine).
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Language patterns. Each matches top-level declarations on their own line.
# Keep patterns conservative — false negatives > false positives.
# ---------------------------------------------------------------------------
LANG_PATTERNS = {
    "rust": {
        "exts": [".rs"],
        "symbol": re.compile(
            r"^\s*(?:pub(?:\s*\([^)]*\))?\s+)?(?:async\s+)?"
            r"(fn|struct|enum|trait|type|mod|const|static)\s+([A-Za-z_][A-Za-z0-9_]*)"
        ),
        "import": re.compile(r"^\s*use\s+([A-Za-z_][\w:]*)"),
    },
    "python": {
        "exts": [".py"],
        "symbol": re.compile(r"^(?:async\s+)?(def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"),
        "import": re.compile(
            r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))"
        ),
    },
    "javascript": {
        "exts": [".js", ".mjs", ".cjs", ".jsx"],
        "symbol": re.compile(
            r"^export\s+(?:default\s+)?(?:async\s+)?"
            r"(function|class|const|let|var)\s+([A-Za-z_$][\w$]*)"
        ),
        "import": re.compile(
            r"""^\s*(?:import\b[^"']*from\s+["']([^"']+)["']"""
            r"""|const\s+[\w{},\s*]+\s*=\s*require\(\s*["']([^"']+)["']\s*\))"""
        ),
    },
    "typescript": {
        "exts": [".ts", ".tsx"],
        "symbol": re.compile(
            r"^export\s+(?:default\s+)?(?:async\s+)?"
            r"(function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)"
        ),
        "import": re.compile(r"""^\s*import\b[^"']*from\s+["']([^"']+)["']"""),
    },
    "go": {
        "exts": [".go"],
        # match `func Name(` or `func (r *Recv) Name(` or `type Name`
        "symbol": re.compile(
            r"^func\s+(?:\([^)]*\)\s+)?([A-Z][\w]*)\s*\(|^type\s+([A-Z][\w]*)"
        ),
        "import": re.compile(r'^\s*"([^"]+)"'),
    },
}

EXCLUDE_DIRS = {
    "node_modules", "target", "dist", "build", ".next", ".git", ".venv", "venv",
    "__pycache__", ".pytest_cache", "coverage", ".turbo", ".cache",
    ".mypy_cache", ".ruff_cache", ".tox", "bower_components", "vendor",
    ".idea", ".vscode", ".context-os",
}
# Prefix-based excludes: dir name starts with any of these. Catches eval
# fixtures, sibling mock repos, etc. without enumerating every variant.
EXCLUDE_DIR_PREFIXES = (
    "autocontext_fixture",   # our own eval fixtures — don't pollute graph
)

# Absolute cap per file to keep pathological files from stalling the walker
MAX_LINES_SCAN = 20000


def walk_sources(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS and not d.startswith(".")
            and not any(d.startswith(p) for p in EXCLUDE_DIR_PREFIXES)
        ]
        for fn in filenames:
            if fn.startswith("."):
                continue
            ext = os.path.splitext(fn)[1]
            for lang, cfg in LANG_PATTERNS.items():
                if ext in cfg["exts"]:
                    path = os.path.join(dirpath, fn)
                    rel = os.path.relpath(path, root)
                    yield rel, lang, path, cfg
                    break


def _clean_sig(line):
    """Trim a declaration line into a compact signature for the outline."""
    s = line.strip()
    # drop trailing block-openers / terminators that add no signal
    s = re.sub(r"\s*[{:]\s*$", "", s)
    s = s.rstrip("\\").rstrip()
    return s[:120]


def extract(path, cfg):
    symbols = []
    imports = []
    line_count = 0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, 1):
                if i > MAX_LINES_SCAN:
                    break
                line_count = i
                s = cfg["symbol"].search(line)
                if s:
                    groups = [g for g in s.groups() if g]
                    sig = _clean_sig(line)
                    if len(groups) >= 2:
                        symbols.append(
                            {"name": groups[1], "kind": groups[0],
                             "line": i, "sig": sig}
                        )
                    elif len(groups) == 1:
                        symbols.append(
                            {"name": groups[0], "kind": "symbol",
                             "line": i, "sig": sig}
                        )
                im = cfg["import"].search(line)
                if im:
                    modules = [g for g in im.groups() if g]
                    if modules:
                        imports.append(modules[0])
    except Exception:
        pass
    # Approximate each symbol's end line as (next top-level symbol start − 1),
    # last one runs to EOF. Good enough to slice a function/class out of a big
    # file without reading the whole thing.
    for idx, sym in enumerate(symbols):
        if idx + 1 < len(symbols):
            sym["end"] = max(sym["line"], symbols[idx + 1]["line"] - 1)
        else:
            sym["end"] = max(sym["line"], line_count)
    # dedupe imports preserving order
    seen = set()
    unique_imports = []
    for m in imports:
        if m not in seen:
            seen.add(m)
            unique_imports.append(m)
    return symbols, unique_imports, line_count


def hot_files(root, max_items=20):
    try:
        out = subprocess.check_output(
            [
                "git", "-C", root, "log", "--name-only",
                "--since=90.days", "--pretty=format:", "-n", "500",
            ],
            stderr=subprocess.DEVNULL, text=True, timeout=15,
        )
    except Exception:
        return []
    counts = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        top = line.split("/", 1)[0]
        if top in EXCLUDE_DIRS:
            continue
        # Also honor prefix excludes at any path depth (fixture dirs etc.).
        if any(seg.startswith(p) for seg in line.split("/")
               for p in EXCLUDE_DIR_PREFIXES):
            continue
        # skip obvious lockfiles and binaries
        base = os.path.basename(line).lower()
        if base in {"package-lock.json", "yarn.lock", "cargo.lock",
                   "poetry.lock", "pnpm-lock.yaml", "composer.lock"}:
            continue
        counts[line] = counts.get(line, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:max_items]
    return [{"path": p, "touches": c} for p, c in ranked]


_PATH_TOK_RE_CAMEL = re.compile(r"[a-z]+|[0-9]+")
_PATH_TOK_RE_SPLIT = re.compile(r"[_\-.]+")


def _path_tokens(fpath):
    """Tokens used by the hook's IDF weighting. Mirror of the hook's
    `_file_path_tokens` — precomputing here avoids an O(N) scan on
    every UserPromptSubmit. At 50k files this drops p99 by ~70%."""
    toks = set()
    low = fpath.lower()
    for seg in re.split(r"[/\\]+", low):
        base = os.path.splitext(seg)[0]
        for part in _PATH_TOK_RE_SPLIT.split(base):
            if len(part) >= 2:
                toks.add(part)
            for sub in _PATH_TOK_RE_CAMEL.findall(part):
                if len(sub) >= 2:
                    toks.add(sub)
    return toks


def build(root):
    files = {}
    symbol_index = {}
    imported_by = {}
    path_df = {}   # token -> document frequency across file paths

    for rel, lang, path, cfg in walk_sources(root):
        symbols, imports, lines = extract(path, cfg)
        files[rel] = {
            "lang": lang,
            "lines": lines,
            "symbols": symbols,
            "imports": imports,
        }
        for sym in symbols:
            symbol_index.setdefault(sym["name"], []).append(
                {"file": rel, "line": sym["line"], "kind": sym["kind"]}
            )
        for im in imports:
            imported_by.setdefault(im, []).append(rel)
        for t in _path_tokens(rel):
            path_df[t] = path_df.get(t, 0) + 1

    return {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": os.path.abspath(root),
        "file_count": len(files),
        "symbol_count": sum(len(f["symbols"]) for f in files.values()),
        "hot_files": hot_files(root),
        "files": files,
        "symbol_index": symbol_index,
        "imported_by": imported_by,
        "path_df": path_df,
    }


def summary_md(graph):
    lines = []
    lines.append(
        f"- Graph: {graph['file_count']} files, "
        f"{graph['symbol_count']} top-level symbols indexed."
    )
    hf = graph.get("hot_files", [])
    if hf:
        top = ", ".join(f"`{h['path']}` ({h['touches']})" for h in hf[:5])
        lines.append(f"- Hot files (90d): {top}")
    lines.append(
        "- Query via `/find <symbol>`, `/deps <file>`, `/hot` — "
        "reads `.context-os/repo-graph.json` (no grep)."
    )
    return "\n".join(lines)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    try:
        graph = build(root)
    except Exception as e:
        sys.stderr.write(f"[context-os] repo-graph build failed: {e}\n")
        return 0
    out_dir = os.path.join(root, ".context-os")
    try:
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "repo-graph.json")
        with open(out_path, "w") as f:
            json.dump(graph, f, separators=(",", ":"))
        sys.stderr.write(
            f"[context-os] repo-graph: {out_path} "
            f"({graph['file_count']} files, {graph['symbol_count']} symbols)\n"
        )
    except Exception as e:
        sys.stderr.write(f"[context-os] repo-graph write failed: {e}\n")
        return 0
    print(summary_md(graph))
    return 0


if __name__ == "__main__":
    sys.exit(main())
CONTEXT_OS_GRAPH_EOF
chmod +x .context-os/build_repo_graph.py

GRAPH_SUMMARY=""
if GRAPH_SUMMARY=$(python3 .context-os/build_repo_graph.py . 2>/dev/null) && [ -f .context-os/repo-graph.json ]; then
  GRAPH_STATS=$(python3 -c "import json; g=json.load(open('.context-os/repo-graph.json')); print(f\"{g['file_count']} files, {g['symbol_count']} symbols\")" 2>/dev/null || echo "built")
  echo "  [$STEP/$TOTAL] built repo graph ($GRAPH_STATS)"
else
  GRAPH_SUMMARY="- Graph: not built (no source files detected, or Python unavailable)."
  echo "  [$STEP/$TOTAL] repo graph skipped"
fi

# ============================================================================
# STEP 2: CLAUDE.md — Response shaping (saves 40-65% output tokens)
# ============================================================================
STEP=2
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
- \`file_size_guard.py\`: blocks Read on files > 1500 lines without offset/limit. Retry with \`offset=N, limit=M\` or delegate to the \`explorer\` subagent.
- \`session_profile.py\`: Stop-time report at \`.context-os/session-reports/\`. Check it after long sessions to see where tokens went.

# Repo graph (.context-os/repo-graph.json)

$GRAPH_SUMMARY

Use \`/find <symbol>\`, \`/deps <file>\`, \`/hot\` before grep. Rebuild via \`python3 .context-os/build_repo_graph.py .\`.
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
# STEP 3: .claudeignore — Noise + secrets (30-40% context reduction)
# ============================================================================
STEP=3
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
# STEP 4: .claude/settings.json — Env vars (thinking cap, prompt caching, traffic control)
# ============================================================================
STEP=4
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
# STEP 5: Permission auto-granting — pre-approve safe tools
# ============================================================================
STEP=5
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
# STEP 6: Slash commands — /compact, /context, /ship, /cheap
# ============================================================================
STEP=6
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

cat > .claude/commands/find.md << 'CMDEOF'
---
description: Find a symbol by name via the repo graph (no grep)
argument-hint: <symbol-name>
---
1. Read `.context-os/repo-graph.json`.
2. In the `symbol_index` object, look up the exact key `$ARGUMENTS`.
3. If found, print each occurrence as: `path:line (kind)` — one per line, up to 10.
4. If more than 10 matches, print "+N more".
5. If the key is missing, also try case-insensitive / substring match against keys and print the top 5 candidates.
6. If `.context-os/repo-graph.json` doesn't exist, tell the user: `python3 .context-os/build_repo_graph.py .` to build it.

Do NOT grep. Do NOT read source files. Just the JSON lookup.
CMDEOF

cat > .claude/commands/deps.md << 'CMDEOF'
---
description: Show imports + importers for a file via the repo graph
argument-hint: <file-path>
---
Read `.context-os/repo-graph.json`. For the file `$ARGUMENTS`:

1. Print `**Imports** (from files["$ARGUMENTS"].imports):` then each import on its own line, up to 15.
2. Print `**Importers** (likely):` — scan `imported_by` keys; for any key whose tail matches the basename of `$ARGUMENTS` without extension, print the value list. Up to 15.
3. Print `**Same-module neighbors:**` — other files in the same directory as `$ARGUMENTS` (from `files` keys).

No grep. No source reads. If the graph is missing, tell the user to rebuild.
CMDEOF

cat > .claude/commands/hot.md << 'CMDEOF'
---
description: List files with highest git change frequency (last 90 days)
---
Read `.context-os/repo-graph.json` → `hot_files`. Print as a numbered list: `N. <path> — <touches> commits`. Show all available (up to 20). If the list is empty, tell the user this repo has no git history or the graph wasn't built.
CMDEOF

cat > .claude/commands/warm-clear.md << 'CMDEOF'
---
description: Write a handoff packet, then prompt for /clear
---
Before the user runs `/clear`, write a succinct handoff to `.context-os/handoff.md` with these sections:

- **OBJECTIVE**: current goal in one line
- **DECISIONS**: last 3-5 decisions made (bullet)
- **FILES**: files modified or key files referenced (bullet)
- **FAILED**: what didn't work (bullet, so we don't retry)
- **NEXT**: one-line "what to do next"

Keep the whole file under 40 lines. Then output exactly:

> Handoff written. Run `/clear` to reset — then paste `.context-os/handoff.md` into the new session.
CMDEOF

cat > .claude/commands/relevant.md << 'CMDEOF'
---
description: Find files most relevant to a query via the repo graph (semantic-lite)
argument-hint: <query>
---
Read `.context-os/repo-graph.json`. For the query `$ARGUMENTS`:

1. Tokenize the query (lowercase, split on non-alphanumeric, drop words < 3 chars).
2. For each file in `files`, score:
   - +5 per matching symbol name (in `files[file].symbols[].name`)
   - +3 per matching import (in `files[file].imports`)
   - +2 if any query token is a substring of the file path
   - +1 if the file is in `hot_files`
3. Print the top 10 as: `score  path  (N symbols, lang)` — one per line.
4. Skip files with score 0.

Do NOT read source files. Do NOT grep. Score purely from the graph JSON.
CMDEOF

cat > .claude/commands/insights.md << 'CMDEOF'
---
description: Aggregate recent session reports — top token sinks and redundant tool calls
---
1. Glob `.context-os/session-reports/*.md` — newest 10.
2. For each, extract: `duplicates caught`, `edit loops`, `top-3 largest tool outputs`.
3. Print:
   - **Patterns (across last N sessions)**: each recurring issue with count
   - **Top token-sink files (aggregated)**: file path + total size seen
   - **Actionable suggestion** (1 line): e.g., "`src/x.ts` seen 4× as top sink — add to .claudeignore or always Read with offset"
4. If no reports exist, say: "No session reports yet — session_profile writes one per Stop event."

Under 20 lines total. Concrete suggestions only — no narrative.
CMDEOF

cat > .claude/commands/rebuild-graph.md << 'CMDEOF'
---
description: Rebuild the repo graph used by auto_context / /find / /deps / /hot
---
Run `python3 .context-os/build_repo_graph.py .` from the repo root via Bash. Then:

1. Print the one-line summary the builder emits (file count, symbol count, hot files).
2. Confirm the graph path: `.context-os/repo-graph.json`.
3. Mention: auto_context and `/find` / `/deps` / `/hot` now use the fresh index.

If the builder fails, show its stderr and tell the user to check Python 3 is on PATH.
CMDEOF

cat > .claude/commands/savings.md << 'CMDEOF'
---
description: Show your context-os token savings — all-time, this week, streak, and a shareable card
---

Run the savings report and show the user the output verbatim:

```bash
python3 .context-os/scripts/savings_report.py --root "$(pwd)" 2>/dev/null \
  || echo "No receipts yet — context-os logs savings as you work. Check back after a few prompts."
```

Print the result exactly as-is (it's a pre-formatted dashboard). Do not summarize
or re-format. The shareable card alone is available with `--card-only`; raw
numbers with `--json`.
CMDEOF

cat > .claude/commands/outline.md << 'CMDEOF'
---
description: Show a file's structural map (symbols + line ranges) so you can read only the slice you need
---

Run, substituting the file the user named (or the one in context):

```bash
python3 .context-os/scripts/outline.py "<file>" --root "$(pwd)" 2>/dev/null \
  || echo "No graph yet — run /rebuild-graph first."
```

Print the output verbatim. It lists every top-level symbol with its exact line
range. Use it to `Read(file, offset=N, limit=M)` the precise block you need
instead of loading the whole file into context.
CMDEOF

echo "  [$STEP/$TOTAL] installed 13 slash commands (/compact /context /ship /cheap /find /deps /hot /warm-clear /relevant /insights /rebuild-graph /savings /outline)"

# ============================================================================
# STEP 7: Haiku subagent — 15x cheaper than Opus for exploration
# ============================================================================
STEP=7
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
# STEP 8: Output style — enforces terse responses at every turn
# ============================================================================
STEP=8
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
# STEP 9: statusLine — live context + cost visibility in every prompt
# ============================================================================
STEP=9
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

# Live savings meter — reads the cached aggregate the Stop hook maintains.
# One tiny file read; compact k/M formatting; silent until there are receipts.
SAVINGS=""
TOTAL_FILE="$CWD/.context-os/savings/total.json"
if [ -f "$TOTAL_FILE" ]; then
  SAVINGS=$(python3 -c "
import json,sys
try:
    d=json.load(open('$TOTAL_FILE')); t=d.get('tokens_saved',0) or 0
    if t<=0: sys.exit(0)
    s=d.get('streak',0) or 0
    v=(f'{t/1_000_000:.1f}M' if t>=1_000_000 else f'{t//1000}k' if t>=1000 else str(t))
    out='💰 '+v+' saved'
    if s>=3: out+=f' · {s}d🔥'
    print(out)
except Exception:
    pass
" 2>/dev/null || echo "")
fi

# Format: model · branch · context-os status · savings
OUT="$MODEL"
[ -n "$BRANCH" ] && OUT="$OUT · $BRANCH"
[ -n "$COS" ] && OUT="$OUT · $COS"
[ -n "$SAVINGS" ] && OUT="$OUT · $SAVINGS"
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
# STEP 10: Python hooks — dedup-guard, loop-guard, session-profile (zero-dep)
# ============================================================================
# These hooks are pure Python stdlib, no binary required. They catch the
# three most common waste patterns in Claude Code sessions:
#   - dedup_guard: blocks duplicate Read/Glob/Grep (same args within 10min)
#   - loop_guard: warns at 5 edits / blocks at 8 edits on same file
#   - session_profile: writes a per-session token breakdown on Stop
# All three fail-open — any error or unexpected input exits 0 silently.
STEP=10
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

# --- file_size_guard.py ---------------------------------------------
cat > "$HOOK_DIR/file_size_guard.py" <<'CONTEXT_OS_SIZE_EOF'
#!/usr/bin/env python3
"""
file_size_guard.py - Context OS PreToolUse hook.

Blocks Read on files larger than a threshold when no offset/limit is set.
Nudges Claude to use offset+limit or delegate to the explorer subagent,
rather than blow 10k-20k tokens on a generated or lockfile read.

Env overrides:
- CONTEXT_OS_FILE_SIZE_THRESHOLD (default: 1500 lines)
- CONTEXT_OS_FILE_SIZE_HARD      (default: 5000 lines)
- CONTEXT_OS_FILE_SIZE_GUARD=0   (disables entirely)

Fail-open on any error.
"""
import json
import os
import sys


def main():
    if os.environ.get("CONTEXT_OS_FILE_SIZE_GUARD") == "0":
        return 0
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    if event.get("tool_name") != "Read":
        return 0
    inp = event.get("tool_input") or {}
    path = inp.get("file_path")
    if not path:
        return 0
    if inp.get("offset") is not None or inp.get("limit") is not None:
        return 0
    try:
        if not os.path.isfile(path):
            return 0
    except Exception:
        return 0
    try:
        threshold = int(os.environ.get("CONTEXT_OS_FILE_SIZE_THRESHOLD", "1500"))
        hard_cap = int(os.environ.get("CONTEXT_OS_FILE_SIZE_HARD", "5000"))
    except ValueError:
        return 0
    count_cap = hard_cap + 1
    line_count = 0
    try:
        with open(path, "rb") as f:
            for line_count, _ in enumerate(f, 1):
                if line_count >= count_cap:
                    break
    except Exception:
        return 0
    if line_count <= threshold:
        return 0
    over_hard = line_count >= count_cap
    label = f">{hard_cap}" if over_hard else str(line_count)
    msg = (
        f"[context-os] {path} has {label} lines "
        f"(threshold {threshold}). Options:\n"
        f"  - Read(file_path, offset=N, limit=M) to read a slice\n"
        f"  - Grep(pattern, path=\"{path}\") to search within it\n"
        f"  - Delegate to the `explorer` Haiku subagent for broad exploration\n"
        f"Set CONTEXT_OS_FILE_SIZE_GUARD=0 to disable."
    )
    sys.stderr.write(msg + "\n")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
CONTEXT_OS_SIZE_EOF
chmod +x "$HOOK_DIR/file_size_guard.py"

# --- auto_context.py (UserPromptSubmit: static-analysis RAG) ---------
cat > "$HOOK_DIR/auto_context.py" <<'CONTEXT_OS_AUTOCTX_EOF'
#!/usr/bin/env python3
"""
auto_context.py - Context OS UserPromptSubmit hook.

Static-analysis RAG without embeddings. Parses the user prompt for
keywords/paths/symbols, looks them up in .context-os/repo-graph.json,
and emits a compact "candidate files" block on stdout. Claude Code
prepends it to the prompt as additional context, so the first turn
starts with structure already in hand.

Env:
- CONTEXT_OS_AUTOCONTEXT=0            disable
- CONTEXT_OS_AUTOCONTEXT_MAX=5        max hits (default 5)
- CONTEXT_OS_AUTOCONTEXT_MIN_WORD=4   min keyword length (default 4)
- CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT=15  min prompt length to trigger
- CONTEXT_OS_AUTOCONTEXT_ABLATE=a,b   comma signals to disable (research)

Fail-open on any error. Silent on no-match.
"""
import json
import math
import os
import re
import sys

# Small natural-language -> code-term expansion. Tuned from dogfood
# failures where prompt describes behavior ("enormous") and code uses
# a different convention ("size"). Kept deliberately small.
EXPANSIONS = {
    "duplicate": ("dedup",), "duplicates": ("dedup",),
    "dedupe": ("dedup",), "deduplicate": ("dedup",),
    "block": ("guard",), "blocks": ("guard",), "blocking": ("guard",),
    "enormous": ("size", "large"), "huge": ("size", "large"),
    "big": ("size",), "gigantic": ("size", "large"),
    "benchmark": ("bench",), "benchmarks": ("bench",),
    "benchmarking": ("bench",), "bench": ("bench",),
    "simulator": ("replay", "simulate"), "simulation": ("replay", "simulate"),
    "simulate": ("replay", "simulate"),
    "adversarial": ("robust", "robustness"),
    "robustness": ("robust",), "robust": ("robust",),
    "warmup": ("prewarm", "warm"), "warm-up": ("prewarm", "warm"),
    "evaluation": ("eval",), "evaluate": ("eval",),
    "statistics": ("stats",), "statistical": ("stats",),
    "ablation": ("ablate", "ablat"),
    "ranking": ("rank",), "scoring": ("rank", "score"),
    "penalty": ("penalt",), "penalize": ("penalt",), "penalise": ("penalt",),
    "savings": ("saving", "save"), "saved": ("save",),
}

STOPWORDS = frozenset([
    "the","and","for","are","but","not","you","all","can","was","one","our",
    "out","had","has","him","his","how","its","let","use","from","with","that",
    "this","have","will","your","what","when","make","like","time","just",
    "know","take","into","them","some","could","other","than","then","look",
    "only","come","over","also","back","after","first","well","even","want",
    "any","been","which","their","work","fix","add","remove","update","create",
    "delete","change","file","files","code","function","class","method",
    "please","thanks","help","need","should","would","show","tell","find",
    "check","test","run","see","does","doing","done","try","using","used",
    "still","where","there","because","about","very","really","much","more",
    "less","most","least","without","within","across","between","through",
    "during","before","above","below","under","same","different","new","old",
    "good","bad","best","worst","better","worse","maybe","probably",
    "definitely","exactly","actually","somehow","instead","rather",
    "something","someone","somewhere","anything","anyone","anywhere",
    "nothing","nobody","nowhere","everything","everyone","everywhere",
    "lets","it's","isn't","wasn't","don't","doesn't","didn't","won't",
    "can't","couldn't","shouldn't","aren't",
])

CAMEL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|[_\-\s]+")
WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PATH_RE = re.compile(r"[\w./\-]+(?:/[\w./\-]+|\.[A-Za-z]{1,5})")


def load_graph(root):
    try:
        with open(os.path.join(root, ".context-os", "repo-graph.json")) as f:
            return json.load(f)
    except Exception:
        return None


def _graph_aware_stopwords(graph):
    """Return stopword set with code-y tokens that appear as filename
    parts promoted back to tokens. Keeps "test"/"file"/"find" etc.
    usable as search terms on repos that have `test_foo.py`."""
    files = graph.get("files") or {}
    filename_toks = set()
    for fpath in files.keys():
        base = os.path.splitext(os.path.basename(fpath))[0].lower()
        for part in re.split(r"[_\-.]+", base):
            if len(part) >= 3:
                filename_toks.add(part)
    promotable = {"test","tests","file","files","find","check","run",
                  "code","fix","add","make","use","show","create",
                  "update","delete","change","remove"}
    promoted = promotable & filename_toks
    return STOPWORDS - promoted


def extract_tokens(prompt, min_word, stopwords=STOPWORDS):
    tokens = set()
    for w in WORD_RE.findall(prompt):
        if len(w) < min_word:
            continue
        low = w.lower()
        if low in stopwords:
            continue
        tokens.add(w)
        for part in CAMEL_SPLIT.split(w):
            if len(part) >= min_word and part.lower() not in stopwords:
                tokens.add(part)
    # NL -> code expansion: only on explicit whole-word hits.
    expanded = set()
    lowered = {t.lower(): t for t in tokens}
    for word in re.findall(r"[A-Za-z]+", prompt.lower()):
        if word in EXPANSIONS:
            for syn in EXPANSIONS[word]:
                if syn not in lowered:
                    expanded.add(syn)
    return tokens | expanded


def extract_paths(prompt):
    paths = set()
    for m in PATH_RE.findall(prompt):
        if "://" in m or m.count(".") > 4:
            continue
        if len(m) >= 3:
            paths.add(m)
    return paths


def _ablate_set():
    v = os.environ.get("CONTEXT_OS_AUTOCONTEXT_ABLATE", "")
    return {s.strip() for s in v.split(",") if s.strip()}


def _file_path_tokens(fpath):
    toks = set()
    low = fpath.lower()
    for seg in re.split(r"[/\\]+", low):
        base = os.path.splitext(seg)[0]
        for part in re.split(r"[_\-.]+", base):
            if len(part) >= 2:
                toks.add(part)
            for sub in re.findall(r"[a-z]+|[0-9]+", part):
                if len(sub) >= 2:
                    toks.add(sub)
    return toks


def _path_token_df(files):
    df = {}
    for fpath in files.keys():
        for t in _file_path_tokens(fpath):
            df[t] = df.get(t, 0) + 1
    return df


def _idf(df, token, N):
    """Dampened IDF capped at 1.6 so rare tokens lift but don't
    dominate exact symbol/path matches."""
    n = df.get(token, 0)
    if n == 0:
        return 1.0
    raw = math.log((N + 1) / (n + 0.5))
    return max(1.0, min(1.6, raw / 2.0))


def _normalize_prompt_forms(prompt):
    low = prompt.lower()
    under = re.sub(r"[^a-z0-9]+", "_", low).strip("_")
    space = re.sub(r"[^a-z0-9]+", " ", low).strip()
    none = re.sub(r"[^a-z0-9]+", "", low)
    return under, space, none


def rank(prompt, graph, max_hits, min_word):
    files = graph.get("files") or {}
    symbol_index = graph.get("symbol_index") or {}
    imported_by = graph.get("imported_by") or {}
    hot = {h.get("path"): h.get("touches", 0)
           for h in (graph.get("hot_files") or [])}

    off = _ablate_set()
    stopwords = _graph_aware_stopwords(graph)
    tokens = extract_tokens(prompt, min_word, stopwords)
    paths = extract_paths(prompt)

    N = max(1, len(files))
    path_df = _path_token_df(files)

    def path_idf(tok):
        return _idf(path_df, tok.lower(), N)

    under, space, _none = _normalize_prompt_forms(prompt)

    candidates = {}

    def bump(f, ln, kind, sym, score, reason):
        key = (f, ln)
        cur = candidates.get(key)
        if cur is None:
            candidates[key] = {"file": f, "line": ln, "kind": kind,
                                "symbol": sym, "score": score,
                                "reasons": [reason]}
        else:
            cur["score"] += score
            if reason not in cur["reasons"]:
                cur["reasons"].append(reason)

    # 1. Symbol match — IDF-weighted.
    sym_lc = {k.lower(): k for k in symbol_index.keys()}
    for tok in tokens:
        if "symbol_exact" not in off and tok in symbol_index:
            idf = max(1.0, path_idf(tok))
            for loc in symbol_index[tok]:
                bump(loc["file"], loc["line"], loc.get("kind",""),
                     tok, int(10 * idf), "symbol `" + tok + "`")
        elif "symbol_ci" not in off and tok.lower() in sym_lc:
            real = sym_lc[tok.lower()]
            idf = max(1.0, path_idf(tok))
            for loc in symbol_index[real]:
                bump(loc["file"], loc["line"], loc.get("kind",""),
                     real, int(8 * idf),
                     "symbol `" + real + "` (ci)")

    # 2a. Basename-in-prompt — catches "robustness_test suite" etc.
    if "path_exact" not in off:
        for fpath in files.keys():
            base_root = os.path.splitext(os.path.basename(fpath))[0].lower()
            if len(base_root) < 5:
                continue
            base_under = re.sub(r"[^a-z0-9]+", "_", base_root).strip("_")
            base_space = re.sub(r"[^a-z0-9]+", " ", base_root).strip()
            if (base_under and base_under in under) or \
               (base_space and " "+base_space+" " in " "+space+" "):
                bump(fpath, 1, "file", os.path.basename(fpath),
                     15, "basename `"+base_root+"` in prompt")

    # 2b. Path / substring — IDF-weighted.
    for tok in list(tokens) + list(paths):
        tl = tok.lower()
        for fpath in files.keys():
            fl = fpath.lower()
            if (("path_exact" not in off) and
                    (fl == tl or fl.endswith("/"+tl)
                     or ("/" in tl and tl in fl))):
                bump(fpath, 1, "file", os.path.basename(fpath),
                     int(8 * max(1.0, path_idf(tok))),
                     "path `"+tok+"`")
            elif ("path_substr" not in off) and len(tl) >= 4 and tl in fl:
                bump(fpath, 1, "file", os.path.basename(fpath),
                     int(3 * max(1.0, path_idf(tok))),
                     "path contains `"+tok+"`")

    # 3. Import match — tight rule.
    if "import" not in off:
        for tok in tokens:
            tl = tok.lower()
            for mod, importers in imported_by.items():
                ml = mod.lower()
                last = ml.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
                if tl == ml or tl == last:
                    for imp in importers[:3]:
                        bump(imp, 1, "importer", mod, 3,
                             "imports `"+mod+"`")

    # 3b. Multi-token coverage bonus.
    if "path_substr" not in off and tokens:
        lowered_tokens = {t.lower() for t in tokens}
        for key, c in list(candidates.items()):
            fl = c["file"].lower()
            base_toks = _file_path_tokens(c["file"])
            hits = sum(1 for t in lowered_tokens
                       if t in base_toks or (len(t) >= 4 and t in fl))
            if hits >= 2:
                bonus = min(8, 2 * (hits - 1))
                c["score"] += bonus
                c["reasons"].append(str(hits)+"-token path coverage")

    # 4. Hot-file boost.
    if "hot" not in off:
        for c in candidates.values():
            if c["file"] in hot:
                c["score"] += 2
                c["reasons"].append("hot")

    # 5. Test-file penalty.
    prompt_low = prompt.lower()
    mentions_tests = any(w in prompt_low for w in ("test","tests","pytest","fixture"))
    if "test_penalty" not in off and not mentions_tests:
        for c in candidates.values():
            f = c["file"]
            base = os.path.basename(f).lower()
            if (f.startswith("tests/") or f.startswith("test/")
                    or "/tests/" in f or "/test/" in f
                    or base.startswith("test_") or base.endswith("_test.py")
                    or base.endswith(".test.ts") or base.endswith(".test.js")
                    or base.endswith(".spec.ts") or base.endswith(".spec.js")):
                c["score"] -= 3
                c["reasons"].append("test-file penalty")

    # 6. Hub-file penalty.
    if "hub_penalty" not in off:
        hub_files = {"mod.rs","models.py","index.ts","index.js",
                     "index.tsx","index.jsx","__init__.py","lib.rs"}
        for c in candidates.values():
            base = os.path.basename(c["file"]).lower()
            if base in hub_files and base.split(".")[0] not in prompt_low and base not in prompt_low:
                c["score"] -= 2
                c["reasons"].append("hub-file penalty")

    ranked = sorted(candidates.values(),
                    key=lambda c: (-c["score"], c["file"], c["line"]))
    per_file = {}
    out = []
    for c in ranked:
        if per_file.get(c["file"], 0) >= 2:
            continue
        per_file[c["file"]] = per_file.get(c["file"], 0) + 1
        out.append(c)
        if len(out) >= max_hits:
            break
    return out


def format_block(hits, graph):
    if not hits:
        return ""
    files = graph.get("files") or {}
    lines = ["<context-os:autocontext>",
             "Graph-matched candidates (structure only, no files read yet):"]
    for c in hits:
        f = c["file"]; sym = c["symbol"]; kind = c["kind"]; ln = c["line"]
        finfo = files.get(f, {})
        imports = finfo.get("imports", [])
        marker = f + ":" + str(ln) if ln > 1 else f
        parts = ["`" + marker + "`"]
        if kind and kind not in ("file", "importer"):
            parts.append(sym + " (" + kind + ")")
        elif kind == "importer":
            parts.append("uses `" + sym + "`")
        if imports and len(imports) <= 3 and kind != "importer":
            parts.append("imports: " + ", ".join(imports))
        elif imports and kind != "importer":
            parts.append(str(len(imports)) + " imports")
        lines.append("- " + " \u00b7 ".join(parts))
    lines.append("Verify before reading. `/find <symbol>` \u00b7 `/deps <file>` for more. Disable: CONTEXT_OS_AUTOCONTEXT=0.")
    lines.append("</context-os:autocontext>")
    return "\n".join(lines)


def main():
    if os.environ.get("CONTEXT_OS_AUTOCONTEXT") == "0":
        return 0
    try:
        min_word = int(os.environ.get("CONTEXT_OS_AUTOCONTEXT_MIN_WORD","4"))
        max_hits = int(os.environ.get("CONTEXT_OS_AUTOCONTEXT_MAX","5"))
        min_prompt = int(os.environ.get("CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT","15"))
    except ValueError:
        return 0
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    prompt = (event.get("prompt") or "").strip()
    if len(prompt) < min_prompt:
        return 0
    low = prompt.lower()
    if low in {"continue","ok","yes","no","go","fix it","do it","run it",
               "try again","retry","next","what","why"}:
        return 0
    cwd = event.get("cwd") or os.getcwd()
    graph = load_graph(cwd)
    if not graph:
        return 0
    hits = rank(prompt, graph, max_hits, min_word)
    block = format_block(hits, graph)
    if block:
        sys.stdout.write(block + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
CONTEXT_OS_AUTOCTX_EOF
chmod +x "$HOOK_DIR/auto_context.py"

# --- prewarm.py (SessionStart: session intelligence brief) -----------
cat > "$HOOK_DIR/prewarm.py" <<'CONTEXT_OS_PREWARM_EOF'
#!/usr/bin/env python3
"""
prewarm.py - Context OS SessionStart hook.

Emits a compact "session intelligence brief" on session start:
  1. Handoff packet reminder (if .context-os/handoff.md exists)
  2. Git state: branch, uncommitted, ahead/behind main
  3. Graph freshness: auto-rebuild in background if stale
  4. Top-3 hot files (90d) from the repo graph
  5. Last session's notable issues (from .context-os/session-reports/)

Prepended to session context by Claude Code so Turn 1 starts informed.

Env:
  CONTEXT_OS_PREWARM=0             disable entirely
  CONTEXT_OS_GRAPH_AUTOBUILD=0     disable background graph rebuild
  CONTEXT_OS_GRAPH_MAX_AGE_DAYS=7  rebuild if graph older than N days
  CONTEXT_OS_GRAPH_MAX_CHANGED=20  rebuild if > N source files newer
"""
import glob
import json
import os
import subprocess
import sys
import time

SRC_EXTS = (".py",".js",".mjs",".cjs",".jsx",".ts",".tsx",".rs",".go")
EXCLUDE_DIRS = {"node_modules","target","dist","build",".next",".git",
                ".venv","venv","__pycache__",".pytest_cache","coverage",
                ".turbo",".cache",".mypy_cache",".ruff_cache",".tox",
                "bower_components","vendor",".idea",".vscode",".context-os"}


def git(cmd, cwd):
    try:
        return subprocess.check_output(
            ["git","-C",cwd]+cmd, stderr=subprocess.DEVNULL,
            text=True, timeout=3).strip()
    except Exception:
        return ""


def git_state(cwd):
    if not os.path.isdir(os.path.join(cwd, ".git")):
        return None
    branch = git(["rev-parse","--abbrev-ref","HEAD"], cwd) or "detached"
    porcelain = git(["status","--porcelain"], cwd)
    dirty = len([l for l in porcelain.splitlines() if l.strip()])
    ahead = behind = 0
    base = None
    for b in ("main","master"):
        if git(["rev-parse","--verify","--quiet",b], cwd):
            base = b
            break
    if base and branch != base:
        rv = git(["rev-list","--left-right","--count",base+"...HEAD"], cwd)
        parts = rv.split()
        if len(parts) == 2:
            try:
                behind, ahead = int(parts[0]), int(parts[1])
            except ValueError:
                pass
    return {"branch":branch,"dirty":dirty,"base":base,
            "ahead":ahead,"behind":behind}


def graph_hot(cwd, n=3):
    try:
        g = json.load(open(os.path.join(cwd,".context-os","repo-graph.json")))
    except Exception:
        return []
    return (g.get("hot_files") or [])[:n]


def graph_freshness(cwd, cap=800):
    p = os.path.join(cwd, ".context-os", "repo-graph.json")
    if not os.path.isfile(p):
        return None
    try:
        gmt = os.path.getmtime(p)
    except OSError:
        return None
    age = (time.time() - gmt) / 86400
    newer = 0
    seen = 0
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for fn in files:
            if not fn.endswith(SRC_EXTS):
                continue
            seen += 1
            if seen > cap:
                break
            try:
                if os.path.getmtime(os.path.join(root, fn)) > gmt:
                    newer += 1
            except OSError:
                pass
        if seen > cap:
            break
    return {"age_days": age, "changed": newer, "seen": seen}


def is_stale(fresh, max_age, max_changed):
    if fresh is None:
        return False, None
    if fresh["age_days"] > max_age:
        return True, "graph %.0fd old" % fresh["age_days"]
    if fresh["changed"] > max_changed:
        return True, "%d source files newer than graph" % fresh["changed"]
    return False, None


def find_builder(cwd):
    candidates = [
        os.path.join(cwd, ".context-os", "build_repo_graph.py"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "build_repo_graph.py"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def spawn_rebuild(cwd):
    builder = find_builder(cwd)
    if not builder:
        return False
    try:
        subprocess.Popen([sys.executable, builder, cwd], cwd=cwd,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except Exception:
        return False


def last_session_notes(cwd):
    pattern = os.path.join(cwd,".context-os","session-reports","*.md")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        return []
    try:
        content = open(files[0], "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return []
    notable = []
    for kw in ("duplicate","loop","top file"):
        for line in content.splitlines():
            if kw in line.lower():
                t = line.strip("-* ").strip()
                if t and t not in notable:
                    notable.append(t)
                    break
    return notable[:3]


def handoff(cwd):
    for c in (".context-os/handoff.md",".context-os/restart-packet.md"):
        if os.path.isfile(os.path.join(cwd, c)):
            return c
    return None


def main():
    if os.environ.get("CONTEXT_OS_PREWARM") == "0":
        return 0
    try:
        event = json.load(sys.stdin)
    except Exception:
        event = {}
    cwd = event.get("cwd") or os.getcwd()
    sections = []

    ho = handoff(cwd)
    if ho:
        sections.append("Handoff packet at `" + ho + "` \u2014 resume from there instead of re-planning.")

    g = git_state(cwd)
    if g:
        parts = ["branch `"+g["branch"]+"`"]
        if g["dirty"]:
            parts.append(str(g["dirty"])+" uncommitted")
        if g["base"] and g["ahead"]:
            parts.append(str(g["ahead"])+" ahead of `"+g["base"]+"`")
        if g["base"] and g["behind"]:
            parts.append(str(g["behind"])+" behind `"+g["base"]+"`")
        sections.append("Git: " + ", ".join(parts) + ".")

    try:
        max_age = int(os.environ.get("CONTEXT_OS_GRAPH_MAX_AGE_DAYS","7"))
        max_changed = int(os.environ.get("CONTEXT_OS_GRAPH_MAX_CHANGED","20"))
    except ValueError:
        max_age, max_changed = 7, 20
    fresh = graph_freshness(cwd)
    stale, reason = is_stale(fresh, max_age, max_changed)
    if stale:
        auto = os.environ.get("CONTEXT_OS_GRAPH_AUTOBUILD") != "0"
        if auto and spawn_rebuild(cwd):
            sections.append("Graph: " + reason + " \u2014 rebuilding in background. Auto-context will use the fresh graph next session.")
        else:
            sections.append("Graph: " + reason + " \u2014 run `/rebuild-graph` to refresh.")

    hot = graph_hot(cwd)
    if hot:
        bits = ["`"+h["path"]+"` ("+str(h["touches"])+")" for h in hot]
        sections.append("Hot (90d): " + ", ".join(bits) + ".")

    notes = last_session_notes(cwd)
    if notes:
        sections.append("Last session: " + "; ".join(notes) + ".")

    if not sections:
        return 0
    out = ["<context-os:prewarm>"] + sections + ["Disable: CONTEXT_OS_PREWARM=0.","</context-os:prewarm>"]
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
CONTEXT_OS_PREWARM_EOF
chmod +x "$HOOK_DIR/prewarm.py"

# --- savings_tracker.py (Stop: turn invisible savings into a visible number) -
cat > "$HOOK_DIR/savings_tracker.py" <<'CONTEXT_OS_SAVINGS_EOF'
#!/usr/bin/env python3
"""
savings_tracker.py — Stop hook. Turns auto_context's invisible token savings
into a visible, personal, accumulating number — measured causally from the
session transcript, not estimated from a constant.

Why causal measurement matters
-------------------------------
A reviewer's first objection to any "we saved you X tokens" claim is: "that's
a made-up number." So we don't make one up. We read the transcript and
classify every prompt's first-turn behaviour:

  * ASSISTED — auto_context surfaced a file and Claude's FIRST tool action was
    a Read of that file, with no Glob/Grep before it. Exploration replaced.
  * EXPLORED — Claude ran Glob/Grep (and read wrong files) before finding the
    target. We MEASURE the token cost of that exploration from the actual
    tool_result sizes in the transcript.

The realized saving per assisted prompt is the *measured* average cost of an
exploration in THAT SAME SESSION — "a search cost you ~14,200 tokens here, and
context-os turned 8 searches into direct opens." When a session has no
exploration to calibrate against, we fall back to a conservative constant
(8k, ~⅖ of the 21k aggregate delta measured in the live A/B) and label the
number an estimate, never passing it off as measured.

Everything is local JSONL + one cached JSON. Fail-open on every error.
Disable with CONTEXT_OS_SAVINGS=0. Override per-hit credit with
CONTEXT_OS_SAVINGS_PER_HIT.
"""
import json
import os
import sys
import time
from pathlib import Path

SAVINGS_DIR_NAME = ".context-os/savings"
DEFAULT_TOKENS_PER_HIT = 8000          # conservative fallback (no baseline)
MEASURED_MIN, MEASURED_MAX = 1500, 15000  # clamp measured per-hit to credible band
MILESTONES = [100_000, 250_000, 500_000, 1_000_000, 2_500_000, 5_000_000,
              10_000_000, 25_000_000, 50_000_000, 100_000_000]
TOKENS_PER_PROMPT = 50_000             # control-arm avg from the live A/B
CHARS_PER_TOKEN = 4
SEARCH_TOOLS = {"Glob", "Grep"}


def approx_tokens(s):
    return max(1, len(s) // CHARS_PER_TOKEN)


def parse_iso(ts):
    if not ts or not isinstance(ts, str):
        return None
    try:
        return _dt_from_iso(ts)
    except Exception:
        return None


def _dt_from_iso(ts):
    from datetime import datetime
    t = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(t).timestamp()


def _abspath(p, cwd):
    if not p:
        return ""
    try:
        return os.path.normpath(p if os.path.isabs(p) else os.path.join(cwd, p))
    except Exception:
        return p


def _file_match(target_abs, candidate_set, candidate_suffixes):
    """target opened by Claude; candidate_set = suggested files (abspaths)."""
    if target_abs in candidate_set:
        return True
    tail = target_abs.lstrip("/")
    for c in candidate_set:
        if c.endswith("/" + tail) or tail.endswith("/" + c.lstrip("/")):
            return True
    base = os.path.basename(target_abs)
    return bool(base and "/" in target_abs and base in candidate_suffixes)


def parse_transcript(path):
    """Return ordered episodes + totals.

    episode = {
        "prompt_ts": float|None,
        "actions": [ {"name","file","cost"} ],   # in call order
        "has_search": bool,
    }
    Also returns (total_tokens, turns).
    """
    try:
        lines = Path(path).open("r", encoding="utf-8", errors="replace").readlines()
    except OSError:
        return [], 0, 0

    raw = []
    result_tokens = {}   # tool_use_id -> approx tokens of its result
    total_tokens = turns = 0

    for line in lines:
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = evt.get("message") or {}
        role = msg.get("role") or evt.get("type")
        ts = parse_iso(evt.get("timestamp"))
        usage = msg.get("usage") or evt.get("usage") or {}
        if usage:
            turns += 1
            total_tokens += (usage.get("input_tokens", 0) or 0)
            total_tokens += (usage.get("output_tokens", 0) or 0)
            total_tokens += (usage.get("cache_creation_input_tokens", 0) or 0)

        text_parts, tools, has_result, has_text = [], [], False, False
        content = msg.get("content")
        if isinstance(content, str):
            text_parts.append(content)
            has_text = bool(content.strip())
        elif isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text":
                    txt = b.get("text") or ""
                    if txt.strip():
                        has_text = True
                        text_parts.append(txt)
                elif bt == "tool_use":
                    tools.append((b.get("id"), b.get("name", "?"),
                                  b.get("input") or {}))
                elif bt == "tool_result":
                    has_result = True
                    rid = b.get("tool_use_id")
                    rc = b.get("content")
                    txt = rc if isinstance(rc, str) else json.dumps(rc)[:40000]
                    if rid:
                        result_tokens[rid] = approx_tokens(txt or "")
        raw.append({"role": role, "ts": ts, "tools": tools,
                    "is_prompt": role == "user" and has_text and not has_result})

    # Attribute result tokens to tool calls; build episodes.
    episodes = []
    cur = None
    for entry in raw:
        if entry["is_prompt"]:
            cur = {"prompt_ts": entry["ts"], "actions": [], "has_search": False}
            episodes.append(cur)
            continue
        if cur is None:
            cur = {"prompt_ts": None, "actions": [], "has_search": False}
            episodes.append(cur)
        for (tid, name, inp) in entry["tools"]:
            cost = result_tokens.get(tid, 0)
            f = ""
            if name == "Read":
                f = inp.get("file_path", "") or ""
            cur["actions"].append({"name": name, "file": f, "cost": cost})
            if name in SEARCH_TOOLS:
                cur["has_search"] = True
    return episodes, total_tokens, turns


def load_suggestions(savings_dir, session_id, cwd):
    """Return (sorted [(ts, abspath)], union_set, n_records)."""
    items, union, n = [], set(), 0
    f = savings_dir / "suggestions.jsonl"
    if not f.exists():
        return items, union, n
    try:
        for line in f.open("r", encoding="utf-8", errors="replace"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if session_id and rec.get("session") != session_id:
                continue
            n += 1
            ts = rec.get("ts")
            for p in rec.get("files", []):
                ap = _abspath(p, cwd)
                if ap:
                    items.append((ts if isinstance(ts, (int, float)) else None, ap))
                    union.add(ap)
    except OSError:
        pass
    items.sort(key=lambda x: (x[0] is None, x[0] or 0))
    return items, union, n


def analyze(episodes, sugg_items, sugg_union):
    """Causal classification + measured exploration cost.

    Returns dict with assisted_hits, explored_episodes, exploration_tokens,
    avg_search_cost, soft_hits.
    """
    have_ts = any(s[0] is not None for s in sugg_items) and \
        any(e["prompt_ts"] is not None for e in episodes)
    sugg_suffixes = {os.path.basename(a) for (_, a) in sugg_items}

    # episode end bounds (next prompt ts) for cumulative suggestion windows
    prompt_idx = [i for i, e in enumerate(episodes) if e["prompt_ts"] is not None]
    next_ts = {}
    for k, i in enumerate(prompt_idx):
        nxt = episodes[prompt_idx[k + 1]]["prompt_ts"] if k + 1 < len(prompt_idx) else float("inf")
        next_ts[i] = nxt

    assisted = explored = exploration_tokens = 0
    all_read_files = set()

    for i, ep in enumerate(episodes):
        actions = ep["actions"]
        for a in actions:
            if a["name"] == "Read" and a["file"]:
                all_read_files.add(os.path.normpath(a["file"]))
        if ep["has_search"]:
            explored += 1
            # exploration tokens: all Glob/Grep results + Reads that follow a
            # search within this episode (the "found it" reads after a hunt).
            seen_search = False
            for a in actions:
                if a["name"] in SEARCH_TOOLS:
                    seen_search = True
                    exploration_tokens += a["cost"]
                elif a["name"] == "Read" and seen_search:
                    exploration_tokens += a["cost"]

        # ASSISTED: first action is a Read of a suggested file, no search first.
        if not actions or actions[0]["name"] != "Read" or not actions[0]["file"]:
            continue
        first_file = os.path.normpath(actions[0]["file"])
        # build the suggestion set visible to this episode
        if have_ts and ep["prompt_ts"] is not None:
            bound = next_ts.get(i, float("inf"))
            cand = {a for (ts, a) in sugg_items
                    if ts is None or ts < bound}
        else:
            cand = set(sugg_union)
        if _file_match(first_file, cand, sugg_suffixes):
            assisted += 1

    soft_hits = len(sugg_union & all_read_files) if sugg_union else 0
    avg_search_cost = (exploration_tokens / explored) if explored else 0
    return {
        "assisted_hits": assisted,
        "explored_episodes": explored,
        "exploration_tokens": exploration_tokens,
        "avg_search_cost": avg_search_cost,
        "soft_hits": soft_hits,
    }


def read_slices(savings_dir, session_id):
    """Sum tokens smart_read kept out of context this session (whole-file
    reads it turned into outlines). Returns (saved, count)."""
    f = savings_dir / "slices.jsonl"
    if not f.exists():
        return 0, 0
    saved = n = 0
    try:
        for line in f.open("r", encoding="utf-8", errors="replace"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if session_id and rec.get("session") != session_id[:12]:
                continue
            saved += rec.get("saved", 0) or 0
            n += 1
    except OSError:
        pass
    return saved, n


def load_total(savings_dir):
    try:
        return json.loads((savings_dir / "total.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {"tokens_saved": 0, "hits": 0, "sessions": 0,
                "first_date": None, "last_date": None, "streak": 0,
                "milestone": 0, "measured_sessions": 0}


def compute_streak(prev, today):
    last = prev.get("last_date")
    streak = prev.get("streak", 0) or 0
    if last == today:
        return max(1, streak)
    if last is None:
        return 1
    try:
        from datetime import date
        ly, lm, ld = (int(x) for x in last.split("-"))
        ty, tm, td = (int(x) for x in today.split("-"))
        gap = (date(ty, tm, td) - date(ly, lm, ld)).days
    except Exception:
        return 1
    if gap == 1:
        return streak + 1
    if gap <= 0:
        return max(1, streak)
    return 1


def main():
    if os.environ.get("CONTEXT_OS_SAVINGS") == "0":
        return 0
    env_per_hit = os.environ.get("CONTEXT_OS_SAVINGS_PER_HIT")
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    transcript = payload.get("transcript_path")
    session_id = payload.get("session_id", "") or ""
    cwd = payload.get("cwd") or os.getcwd()
    if not transcript or not os.path.exists(transcript):
        return 0

    savings_dir = Path(cwd) / SAVINGS_DIR_NAME
    sugg_items, sugg_union, n_sugg = load_suggestions(savings_dir, session_id, cwd)
    slice_saved, n_slices = read_slices(savings_dir, session_id)
    if n_sugg == 0 and n_slices == 0:
        return 0  # neither auto_context nor smart_read fired this session

    episodes, total_tokens, turns = parse_transcript(transcript)
    a = analyze(episodes, sugg_items, sugg_union)

    # Per-hit credit: measured if we have an exploration baseline, else estimate.
    if env_per_hit:
        try:
            per_hit = max(0, int(env_per_hit))
        except ValueError:
            per_hit = DEFAULT_TOKENS_PER_HIT
        method = "override"
    elif a["explored_episodes"] > 0 and a["avg_search_cost"] > 0:
        per_hit = int(max(MEASURED_MIN, min(a["avg_search_cost"], MEASURED_MAX)))
        method = "measured"
    else:
        per_hit = DEFAULT_TOKENS_PER_HIT
        method = "estimate"

    n_hits = a["assisted_hits"]
    search_saved = n_hits * per_hit
    # slice_saved / n_slices computed above (smart_read whole-file → outline).
    tokens_saved = search_saved + slice_saved

    today = time.strftime("%Y-%m-%d")
    prev = load_total(savings_dir)
    prev_saved = prev.get("tokens_saved", 0) or 0
    new_total = prev_saved + tokens_saved
    streak = compute_streak(prev, today)

    savings_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.time(), "date": today, "session": session_id[:12],
        "suggestions": n_sugg, "suggested_files": len(sugg_union),
        "hits": n_hits,                       # causal assisted hits (headline)
        "assisted_hits": n_hits,
        "soft_hits": a["soft_hits"],          # broad suggested∩read (context)
        "explored_episodes": a["explored_episodes"],
        "exploration_tokens": a["exploration_tokens"],
        "avg_search_cost": round(a["avg_search_cost"]),
        "per_hit": per_hit, "method": method,
        "slices": n_slices, "slice_saved": slice_saved,
        "search_saved": search_saved,
        "turns": turns, "session_tokens": total_tokens,
        "tokens_saved": tokens_saved,
    }
    try:
        with (savings_dir / "ledger.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        return 0

    crossed = None
    for m in MILESTONES:
        if prev_saved < m <= new_total:
            crossed = m
    total = {
        "tokens_saved": new_total,
        "hits": (prev.get("hits", 0) or 0) + n_hits,
        "sessions": (prev.get("sessions", 0) or 0) + 1,
        "measured_sessions": (prev.get("measured_sessions", 0) or 0)
        + (1 if method == "measured" else 0),
        "slices": (prev.get("slices", 0) or 0) + n_slices,
        "first_date": prev.get("first_date") or today,
        "last_date": today, "streak": streak,
        "milestone": crossed or prev.get("milestone", 0),
        "usd_per_mtok": 6.0,
    }
    try:
        (savings_dir / "total.json").write_text(json.dumps(total))
    except OSError:
        pass

    if tokens_saved > 0:
        usd = new_total / 1_000_000 * 6.0
        parts = []
        if n_hits > 0:
            if method == "measured":
                how = (f"a search cost ~{int(a['avg_search_cost']):,} tok here, "
                       f"measured")
            elif method == "estimate":
                how = "conservative estimate"
            else:
                how = "per CONTEXT_OS_SAVINGS_PER_HIT"
            parts.append(
                f"{n_hits} prompt{'s' if n_hits != 1 else ''} went straight to "
                f"the right file ({how})")
        if n_slices > 0:
            parts.append(
                f"{n_slices} big file{'s' if n_slices != 1 else ''} read as an "
                f"outline, not whole ({slice_saved:,} tok kept out of context)")
        print(
            f"[context-os] receipt: " + "; ".join(parts) +
            f" → ~{tokens_saved:,} tokens saved. "
            f"All-time: {new_total:,} tok (~${usd:,.2f}) · {streak}-day streak. "
            f"/savings for the breakdown.",
            file=sys.stderr,
        )
    if crossed:
        print(
            f"[context-os] *** MILESTONE: {crossed:,} tokens saved with "
            f"context-os. Share your card: /savings ***",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
CONTEXT_OS_SAVINGS_EOF
chmod +x "$HOOK_DIR/savings_tracker.py"

# --- smart_read.py (PreToolUse Read: whole-file → structural outline) ---
cat > "$HOOK_DIR/smart_read.py" <<'CONTEXT_OS_SMARTREAD_EOF'
#!/usr/bin/env python3
"""
smart_read.py — Context OS PreToolUse hook (Read). The structural-slicing layer.

The compounding cost nobody attacks
------------------------------------
auto_context kills *first-turn* exploration. But the bigger, compounding cost
in a long session is this: every file Claude reads enters the context window
and is **re-sent on every subsequent turn** until compaction. Read an 800-line
file at turn 3 and you pay ~6.5k tokens for it again, and again, for the next
40 turns — even though Claude needed one 40-line function.

`file_size_guard` blocks oversized whole-file reads but only says "use
offset/limit" — leaving Claude to Grep or guess, which costs *more*. This hook
closes that gap: it intercepts a whole-file Read and hands back the file's
**outline** — every symbol with its exact line range, rendered straight from
the repo graph with zero file content — so Claude re-reads only the slice it
needs. The 800 lines never enter context.

Mechanism (proven): PreToolUse exit 2 + stderr → Claude sees the outline and
retries with `offset`/`limit` (which this hook never intercepts). Each file is
offered an outline at most once per session, so there is no loop and no nag.

Logs each interception to `.context-os/savings/slices.jsonl`; the Stop-time
Receipts hook credits the whole-file tokens kept out of context (a floor —
the avoided per-turn re-sends dwarf it).

Disable: CONTEXT_OS_SMART_READ=0. Threshold: CONTEXT_OS_SMART_READ_MIN (lines,
default 400). Fail-open on every error.
"""
import json
import os
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".context-os" / "state"
CHARS_PER_TOKEN = 4
MAX_OUTLINE_ROWS = 80


def _load_graph(cwd):
    p = os.path.join(cwd, ".context-os", "repo-graph.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _rel(path, cwd):
    try:
        return os.path.relpath(path, cwd)
    except Exception:
        return path


def _count_lines(path, cap):
    n = 0
    try:
        with open(path, "rb") as f:
            for n, _ in enumerate(f, 1):
                if n >= cap:
                    break
    except Exception:
        return 0
    return n


def _file_entry(graph, rel, path):
    files = (graph or {}).get("files") or {}
    if rel in files:
        return files[rel]
    # tolerate path/sep differences: match by suffix
    norm = rel.replace(os.sep, "/")
    for k, v in files.items():
        if k.replace(os.sep, "/").endswith("/" + norm) or \
                norm.endswith("/" + k.replace(os.sep, "/")):
            return v
    base = os.path.basename(rel)
    cand = [v for k, v in files.items() if os.path.basename(k) == base]
    return cand[0] if len(cand) == 1 else None


def _render_outline(rel, entry, total_lines):
    syms = entry.get("symbols") or []
    rows = []
    for s in syms:
        line = s.get("line", 1)
        end = s.get("end", line)
        sig = s.get("sig") or f"{s.get('kind','')} {s.get('name','')}".strip()
        span = f"L{line}-{end}"
        rows.append((line, end, f"  {span:<12} {sig}"))
    if not rows:
        return None, 0
    shown = rows[:MAX_OUTLINE_ROWS]
    body = "\n".join(r[2] for r in shown)
    more = len(rows) - len(shown)
    # pick the largest symbol as the "for example" slice
    biggest = max(rows, key=lambda r: r[1] - r[0])
    ex_off, ex_end = biggest[0], biggest[1]
    ex_lim = max(1, ex_end - ex_off + 1)
    out = [
        f"[context-os] `{rel}` is {total_lines} lines. Reading it whole loads "
        f"it into context for every turn that follows. Its structure ({len(rows)} "
        f"symbols) — read the slice you need:",
        "",
        body,
    ]
    if more > 0:
        out.append(f"  … +{more} more symbols")
    out += [
        "",
        f"e.g. Read(\"{rel}\", offset={ex_off}, limit={ex_lim}) for the block at "
        f"L{ex_off}. Sliced reads are never intercepted. Need the whole file? "
        f"Re-Read it (won't be intercepted again this session) or set "
        f"CONTEXT_OS_SMART_READ=0.",
    ]
    return "\n".join(out), len(rows)


def _already_offered(session, rel):
    """Offer a given file's outline at most once per session (no loop/nag)."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        f = STATE_DIR / f"smartread-{(session or 'default')[:24]}.json"
        try:
            seen = set(json.loads(f.read_text()))
        except (OSError, json.JSONDecodeError):
            seen = set()
        if rel in seen:
            return True
        seen.add(rel)
        f.write_text(json.dumps(sorted(seen)))
        return False
    except Exception:
        return False


def _log_slice(cwd, session, rel, full_lines, full_tokens, outline_tokens):
    try:
        d = os.path.join(cwd, ".context-os", "savings")
        os.makedirs(d, exist_ok=True)
        rec = {"ts": time.time(), "session": (session or "")[:12], "file": rel,
               "full_lines": full_lines, "full_tokens": full_tokens,
               "outline_tokens": outline_tokens,
               "saved": max(0, full_tokens - outline_tokens)}
        with open(os.path.join(d, "slices.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def main():
    if os.environ.get("CONTEXT_OS_SMART_READ") == "0":
        return 0
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    if event.get("tool_name") != "Read":
        return 0
    inp = event.get("tool_input") or {}
    path = inp.get("file_path")
    if not path:
        return 0
    # Only intercept whole-file reads — slices are exactly what we want.
    if inp.get("offset") is not None or inp.get("limit") is not None:
        return 0
    try:
        threshold = int(os.environ.get("CONTEXT_OS_SMART_READ_MIN", "400"))
    except ValueError:
        threshold = 400
    cwd = event.get("cwd") or os.getcwd()
    try:
        if not os.path.isfile(path):
            return 0
    except Exception:
        return 0

    graph = _load_graph(cwd)
    if not graph:
        return 0  # no map → let file_size_guard handle pure size
    rel = _rel(path, cwd)
    entry = _file_entry(graph, rel, path)
    if not entry:
        return 0
    syms = entry.get("symbols") or []
    if len(syms) < 2:
        return 0  # too little structure to slice usefully

    capped = _count_lines(path, threshold + 1)
    if capped <= threshold:
        return 0
    # Real line count for display/logging (the threshold scan is capped).
    real_lines = max(entry.get("lines") or 0, capped)

    session = event.get("session_id", "") or ""
    if _already_offered(session, rel):
        return 0  # offered once already — let Claude read it whole now

    outline, n = _render_outline(rel, entry, real_lines)
    if not outline:
        return 0
    try:
        full_tokens = max(1, os.path.getsize(path) // CHARS_PER_TOKEN)
    except Exception:
        full_tokens = real_lines * 8
    outline_tokens = max(1, len(outline) // CHARS_PER_TOKEN)
    _log_slice(cwd, session, rel, real_lines, full_tokens, outline_tokens)
    sys.stderr.write(outline + "\n")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
CONTEXT_OS_SMARTREAD_EOF
chmod +x "$HOOK_DIR/smart_read.py"

# --- savings_report.py (/savings backend) → .context-os/scripts/ ------------
mkdir -p .context-os/scripts
cat > .context-os/scripts/savings_report.py <<'CONTEXT_OS_SAVINGS_REPORT_EOF'
#!/usr/bin/env python3
"""
savings_report.py — backend for the `/savings` slash command.

Reads the savings ledger written by savings_tracker.py (Stop hook) and prints
a terminal dashboard plus a copy-paste shareable card. This is the surface
that makes context-os's value felt: a personal, accumulating number with a
day-streak, a dollar figure, and rate-limit runway framing.

Usage:
    python3 savings_report.py [--root DIR] [--json] [--card-only]

Honesty: every number is derived from the local ledger. tokens-saved is the
conservative per-hit estimate recorded at session time (see savings_tracker.py
docstring). Nothing phones home.
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

SAVINGS_DIR_NAME = ".context-os/savings"
TOKENS_PER_PROMPT = 50_000  # control-arm avg from the live A/B
USD_PER_MTOK = 6.0          # conservative blended Sonnet pricing


def load_ledger(root):
    path = os.path.join(root, SAVINGS_DIR_NAME, "ledger.jsonl")
    rows = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return rows


def _bar(frac, width=24):
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    return "█" * filled + "░" * (width - filled)


def aggregate(rows):
    tot_saved = sum(r.get("tokens_saved", 0) or 0 for r in rows)
    tot_hits = sum(r.get("hits", 0) or 0 for r in rows)
    tot_sugg = sum(r.get("suggestions", 0) or 0 for r in rows)
    tot_sugg_files = sum(r.get("suggested_files", 0) or 0 for r in rows)
    tot_explored = sum(r.get("explored_episodes", 0) or 0 for r in rows)
    tot_expl_tok = sum(r.get("exploration_tokens", 0) or 0 for r in rows)
    tot_slices = sum(r.get("slices", 0) or 0 for r in rows)
    tot_slice_saved = sum(r.get("slice_saved", 0) or 0 for r in rows)
    tot_search_saved = sum(r.get("search_saved",
                                 r.get("tokens_saved", 0)) or 0 for r in rows)
    measured_rows = sum(1 for r in rows if r.get("method") == "measured")
    measured_saved = sum(r.get("tokens_saved", 0) or 0
                         for r in rows if r.get("method") == "measured")
    by_day = defaultdict(int)
    for r in rows:
        by_day[r.get("date", "?")] += r.get("tokens_saved", 0) or 0
    days = sorted(d for d in by_day if d and d != "?")
    # streak: consecutive days up to the most recent ledger day
    streak = 0
    if days:
        from datetime import date, timedelta
        try:
            cur = date.fromisoformat(days[-1])
            present = {date.fromisoformat(d) for d in days}
            while cur in present:
                streak += 1
                cur = cur - timedelta(days=1)
        except ValueError:
            streak = len(days)
    # this week
    week_saved = 0
    if days:
        from datetime import date, timedelta
        try:
            today = date.fromisoformat(days[-1])
            wk_start = today - timedelta(days=6)
            for d, v in by_day.items():
                try:
                    if date.fromisoformat(d) >= wk_start:
                        week_saved += v
                except ValueError:
                    pass
        except ValueError:
            pass
    return {
        "tokens_saved": tot_saved,
        "hits": tot_hits,
        "suggestions": tot_sugg,
        "suggested_files": tot_sugg_files,
        "sessions": len(rows),
        "days_active": len(days),
        "streak": streak,
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
        "week_saved": week_saved,
        "by_day": dict(by_day),
        "hit_rate": (tot_hits / tot_sugg_files) if tot_sugg_files else 0.0,
        "explored_episodes": tot_explored,
        "exploration_tokens": tot_expl_tok,
        "avg_search_cost": (tot_expl_tok / tot_explored) if tot_explored else 0,
        "measured_rows": measured_rows,
        "measured_saved": measured_saved,
        "measured_share": (measured_saved / tot_saved) if tot_saved else 0.0,
        "slices": tot_slices,
        "slice_saved": tot_slice_saved,
        "search_saved": tot_search_saved,
    }


def make_card(a):
    saved = a["tokens_saved"]
    usd = saved / 1_000_000 * USD_PER_MTOK
    runway = saved / TOKENS_PER_PROMPT
    W = 45  # inner width

    def row(s):
        return "│ " + s.ljust(W - 2) + " │"

    def center(s):
        return "│" + s.center(W) + "│"

    searches = f"{a['hits']:,} search{'es' if a['hits'] != 1 else ''}"
    third = (f"avg search cost {int(a['avg_search_cost']):,} tok — measured"
             if a["avg_search_cost"] > 0
             else f"{a['hits']:,} would-be searches, skipped")
    lines = [
        "╭" + "─" * W + "╮",
        center("context-os · receipts"),
        "├" + "─" * W + "┤",
        row(f"{saved:,} tokens saved   (~${usd:,.2f})"),
        row(f"{searches} replaced by a direct open"),
        row(third),
        row(f"~{runway:.0f} prompts of runway  ·  {a['streak']}-day streak"),
        "├" + "─" * W + "┤",
        row("github.com/sravan27/context-os · MIT"),
        "╰" + "─" * W + "╯",
    ]
    return "\n".join(lines)


def make_report(a):
    saved = a["tokens_saved"]
    usd = saved / 1_000_000 * USD_PER_MTOK
    runway = saved / TOKENS_PER_PROMPT
    week_usd = a["week_saved"] / 1_000_000 * USD_PER_MTOK
    out = []
    out.append("")
    out.append("  context-os — your savings")
    out.append("  " + "─" * 44)
    out.append("")
    runway_str = f"{runway:,.1f}" if runway < 10 else f"{runway:,.0f}"
    out.append(f"  All-time saved   {saved:>13,} tokens  (~${usd:,.2f})")
    out.append(f"  This week        {a['week_saved']:>13,} tokens  "
               f"(~${week_usd:,.2f})")
    out.append(f"  Runway bought    {('~' + runway_str):>13} prompts before "
               f"the rate window")
    out.append("")
    out.append(f"  Searches avoided {a['hits']:>13,}  "
               f"(prompts that opened the right file with no Glob/Grep)")
    if a.get("slices", 0):
        out.append(f"  Big reads sliced {a['slices']:>13,}  "
                   f"(whole-file reads turned into a structural outline)")
    out.append(f"  Sessions         {a['sessions']:>13,}  "
               f"over {a['days_active']} active days")
    out.append(f"  Streak           {a['streak']:>13}  "
               f"consecutive days {'🔥' if a['streak'] >= 3 else ''}")
    if a["first_day"]:
        out.append(f"  Since            {a['first_day']:>13}")
    out.append("")

    # Two measured sources, broken out.
    if a.get("slice_saved", 0) and a.get("search_saved", 0):
        out.append("  Where it came from")
        out.append("  " + "─" * 44)
        out.append(f"  Avoided searches  {a['search_saved']:>13,} tok  "
                   f"(auto_context → straight to file)")
        out.append(f"  Sliced big reads  {a['slice_saved']:>13,} tok  "
                   f"(smart_read → outline, not whole file)")
        out.append("")

    # The Boris line: measured, not estimated.
    if a["avg_search_cost"] > 0:
        share = a["measured_share"] * 100
        out.append("  How it's measured")
        out.append("  " + "─" * 44)
        out.append(f"  A search cost   {int(a['avg_search_cost']):>13,} tokens "
                   f"on average — measured")
        out.append(f"                  from {a['explored_episodes']:,} of your own "
                   f"prompts that still explored")
        out.append(f"  {share:.0f}% of the savings above is measured this way "
                   f"(rest: conservative")
        out.append("  8k/hit fallback for sessions with nothing to measure).")
        out.append("")

    # sparkline of last 14 active days
    days = sorted(d for d in a["by_day"] if d and d != "?")
    if days:
        tail = days[-14:]
        vals = [a["by_day"][d] for d in tail]
        mx = max(vals) or 1
        spark = "".join(
            " ▁▂▃▄▅▆▇█"[min(8, int(v / mx * 8))] for v in vals
        )
        out.append(f"  Last {len(tail):>2} days     {spark}")
        out.append(f"                   {tail[0]} → {tail[-1]}")
        out.append("")

    out.append("  Shareable card (copy/paste anywhere):")
    out.append("")
    for ln in make_card(a).splitlines():
        out.append("  " + ln)
    out.append("")
    if a["measured_share"] >= 0.999:
        out.append("  Note: every token above is measured from your own "
                   "exploration cost —")
        out.append("  no estimated constants. It still under-claims (clamped "
                   "≤15k/search).")
    elif a["measured_share"] > 0:
        out.append(f"  Note: {a['measured_share']*100:.0f}% measured from your "
                   "own exploration cost; the rest")
        out.append("  uses a conservative 8k/hit fallback. Under-claims on "
                   "purpose.")
    else:
        out.append("  Note: tokens-saved uses a conservative 8k/hit estimate "
                   "(vs ~21k")
        out.append("  measured in the live A/B) until a session has searches "
                   "to measure.")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--card-only", action="store_true")
    args = ap.parse_args()

    rows = load_ledger(args.root)
    if not rows:
        print(
            "\n  context-os — your savings\n  " + "─" * 44 + "\n\n"
            "  No receipts yet. context-os logs a receipt every time Claude\n"
            "  opens a file it surfaced for you. Run a few prompts that ask\n"
            "  'where is X' and check back — the savings start accumulating\n"
            "  on the next Stop event.\n"
        )
        return 0

    a = aggregate(rows)
    if args.json:
        print(json.dumps(a, indent=2))
    elif args.card_only:
        print(make_card(a))
    else:
        print(make_report(a))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open: a broken report must never break the user's session.
        sys.exit(0)
CONTEXT_OS_SAVINGS_REPORT_EOF
chmod +x .context-os/scripts/savings_report.py

# --- outline.py (/outline backend) → .context-os/scripts/ -----------------
cat > .context-os/scripts/outline.py <<'CONTEXT_OS_OUTLINE_EOF'
#!/usr/bin/env python3
"""
outline.py — backend for the `/outline <file>` slash command.

Prints a file's structural map — every top-level symbol with its exact line
range and signature — straight from `.context-os/repo-graph.json`, with zero
file content loaded. Lets Claude (or you) see the shape of a big file and read
only the slice that matters, instead of dumping the whole thing into context.

Usage:
    python3 outline.py <file> [--root DIR]
"""
import argparse
import json
import os
import sys


def load_graph(root):
    p = os.path.join(root, ".context-os", "repo-graph.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def find_entry(graph, target, root):
    files = (graph or {}).get("files") or {}
    if not files:
        return None, None
    # normalize the requested path to repo-relative
    t = target
    if os.path.isabs(t):
        try:
            t = os.path.relpath(t, root)
        except Exception:
            pass
    t = t.replace(os.sep, "/").lstrip("./")
    if t in files:
        return t, files[t]
    for k, v in files.items():
        kk = k.replace(os.sep, "/")
        if kk.endswith("/" + t) or t.endswith("/" + kk):
            return k, v
    base = os.path.basename(t)
    cand = [(k, v) for k, v in files.items() if os.path.basename(k) == base]
    if len(cand) == 1:
        return cand[0]
    return None, None


def render(rel, entry):
    syms = entry.get("symbols") or []
    lines = entry.get("lines", 0)
    out = [f"\n  {rel}  ({lines} lines · {len(syms)} symbols)",
           "  " + "─" * 56]
    if not syms:
        out.append("  (no top-level symbols indexed)")
        return "\n".join(out) + "\n"
    for s in syms:
        ln, end = s.get("line", 1), s.get("end", s.get("line", 1))
        sig = s.get("sig") or f"{s.get('kind','')} {s.get('name','')}".strip()
        out.append(f"  L{ln:<5}-{end:<5} {sig}")
    biggest = max(syms, key=lambda s: (s.get("end", s["line"]) - s["line"]))
    off = biggest["line"]
    lim = max(1, biggest.get("end", off) - off + 1)
    out.append("")
    out.append(f"  Read a slice, not the whole file — e.g. "
               f"Read(\"{rel}\", offset={off}, limit={lim})")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--root", default=os.getcwd())
    args = ap.parse_args()
    if not args.file:
        print("usage: /outline <file>")
        return 0
    graph = load_graph(args.root)
    if not graph:
        print("No repo graph yet — run `python3 .context-os/build_repo_graph.py .` "
              "(or /rebuild-graph) first.")
        return 0
    rel, entry = find_entry(graph, args.file, args.root)
    if not entry:
        print(f"`{args.file}` is not in the graph. Try /rebuild-graph, or "
              f"Grep within it. (Non-code files aren't indexed.)")
        return 0
    print(render(rel, entry))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
CONTEXT_OS_OUTLINE_EOF
chmod +x .context-os/scripts/outline.py

# Merge Python hooks into settings.local.json. Additive merge — preserves any
# existing hooks (e.g. from the optional binary-based step below).
PY_ABS="$(cd "$HOOK_DIR" && pwd)"
SETTINGS_LOCAL=".claude/settings.local.json"

PYTHON_HOOKS=$(cat <<HOOKJSON
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Read|Glob|Grep", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/dedup_guard.py'", "timeout": 3}]},
      {"matcher": "Edit|Write|NotebookEdit", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/loop_guard.py'", "timeout": 3}]},
      {"matcher": "Read", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/smart_read.py'", "timeout": 3}]},
      {"matcher": "Read", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/file_size_guard.py'", "timeout": 3}]}
    ],
    "UserPromptSubmit": [
      {"matcher": "", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/auto_context.py'", "timeout": 3}]}
    ],
    "SessionStart": [
      {"matcher": "", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/prewarm.py'", "timeout": 3}]}
    ],
    "Stop": [
      {"matcher": "", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/session_profile.py'", "timeout": 15}]},
      {"matcher": "", "hooks": [{"type": "command", "command": "python3 '$PY_ABS/savings_tracker.py'", "timeout": 15}]}
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
" 2>/dev/null && echo "  [$STEP/$TOTAL] installed 8 Python hooks (dedup, loop, size, smartread, profiler, autocontext, prewarm, savings)" || echo "  [$STEP/$TOTAL] Python hooks install failed"
else
  printf '%s' "$PYTHON_HOOKS" | python3 -m json.tool > "$SETTINGS_LOCAL" 2>/dev/null || printf '%s' "$PYTHON_HOOKS" > "$SETTINGS_LOCAL"
  echo "  [$STEP/$TOTAL] installed 8 Python hooks (dedup, loop, size, smartread, profiler, autocontext, prewarm, savings)"
fi

# ============================================================================
# STEP 11: Binary hooks — output compression + session memory (needs binary)
# ============================================================================
STEP=11
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
# STEP 12: .gitignore
# ============================================================================
STEP=12
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
printf "  ✓ %-22s %s\n" "slash commands" "11 total (incl. /find /deps /hot /relevant /insights /rebuild-graph)"
printf "  ✓ %-22s %s\n" "haiku subagent" "/explorer for cheap exploration"
printf "  ✓ %-22s %s\n" "secret filtering" ".env, *.pem, credentials blocked"
printf "  ✓ %-22s %s\n" "repo graph" "symbols + imports + hot files (.context-os/repo-graph.json)"
printf "  ✓ %-22s %s\n" "auto-context" "graph-RAG injected on every UserPromptSubmit"
printf "  ✓ %-22s %s\n" "prewarm" "session brief: git + hot files + last-session flags"
printf "  ✓ %-22s %s\n" "dedup guard" "blocks duplicate Read/Glob/Grep within 10min"
printf "  ✓ %-22s %s\n" "loop guard" "warns at 5 edits, blocks at 8 on same file"
printf "  ✓ %-22s %s\n" "size guard" "blocks Read on files >1500 lines without offset"
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
