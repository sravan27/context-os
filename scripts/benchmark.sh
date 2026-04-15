#!/usr/bin/env bash
# Real before/after benchmark for Context OS.
#
# This runs a canonical Claude Code task against a target repo TWICE:
#   1. Without Context OS (baseline)
#   2. With Context OS installed
#
# Then it reads Claude Code's session transcripts to count actual input
# and output tokens, and reports the delta.
#
# This is NOT the --measure speculative estimate. These are measured numbers.
#
# Usage:
#   scripts/benchmark.sh                      # against current dir
#   scripts/benchmark.sh /path/to/repo        # against arbitrary repo
#   scripts/benchmark.sh --task "add hello"   # override task prompt
#
# Requires:
#   - claude CLI on PATH (Claude Code binary)
#   - git (to snapshot/restore repo state)
#   - jq OR python3 (for JSON parsing)

set -euo pipefail

TARGET_REPO="${1:-$(pwd)}"
TASK_PROMPT="${TASK_PROMPT:-List the top-level directory structure of this repo, then count source files by language. One line per language.}"

if [ ! -d "$TARGET_REPO/.git" ]; then
  echo "error: $TARGET_REPO is not a git repo" >&2
  exit 1
fi

if ! command -v claude &>/dev/null; then
  echo "error: 'claude' CLI not found on PATH. Install Claude Code first." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SETUP_SH="${SCRIPT_DIR}/../setup.sh"
if [ ! -f "$SETUP_SH" ]; then
  echo "error: setup.sh not found at $SETUP_SH" >&2
  exit 1
fi

# Work in a temp clone so we never touch the user's real repo
WORKDIR=$(mktemp -d -t cos-bench.XXXXXX)
trap 'rm -rf "$WORKDIR"' EXIT

echo ""
echo "  context-os benchmark"
echo "  ═══════════════════════════════════════════════════"
echo "  Target:  $TARGET_REPO"
echo "  Task:    $TASK_PROMPT"
echo "  Workdir: $WORKDIR"
echo ""

# Clone (shallow)
git clone --quiet --depth 1 "file://$TARGET_REPO" "$WORKDIR/repo" 2>&1 || {
  # Fallback for non-git-local paths
  cp -R "$TARGET_REPO" "$WORKDIR/repo"
}

run_task() {
  local label=$1
  local dir=$2
  local transcript="$WORKDIR/transcript-${label}.json"

  echo "  → running '$label' task..."

  # claude --print runs headlessly, exits with usage report in JSON
  (cd "$dir" && claude --print --output-format json "$TASK_PROMPT" 2>/dev/null > "$transcript") || {
    echo "  ! claude CLI failed for '$label'" >&2
    return 1
  }

  # Parse token counts from the JSON transcript
  local input_tokens output_tokens
  if command -v jq &>/dev/null; then
    input_tokens=$(jq -r '.usage.input_tokens // .total_tokens // 0' "$transcript" 2>/dev/null || echo 0)
    output_tokens=$(jq -r '.usage.output_tokens // 0' "$transcript" 2>/dev/null || echo 0)
  else
    input_tokens=$(python3 -c "import json;d=json.load(open('$transcript'));print(d.get('usage',{}).get('input_tokens', d.get('total_tokens', 0)))" 2>/dev/null || echo 0)
    output_tokens=$(python3 -c "import json;d=json.load(open('$transcript'));print(d.get('usage',{}).get('output_tokens', 0))" 2>/dev/null || echo 0)
  fi

  echo "$input_tokens $output_tokens"
}

# BEFORE: no Context OS
echo "  [baseline: no Context OS]"
BEFORE=$(run_task "before" "$WORKDIR/repo")
BEFORE_IN=$(echo "$BEFORE" | awk '{print $1}')
BEFORE_OUT=$(echo "$BEFORE" | awk '{print $2}')
echo ""

# Install Context OS in a fresh copy
cp -R "$WORKDIR/repo" "$WORKDIR/repo-cos"
(cd "$WORKDIR/repo-cos" && bash "$SETUP_SH" >/dev/null 2>&1)

# AFTER: with Context OS
echo "  [with Context OS]"
AFTER=$(run_task "after" "$WORKDIR/repo-cos")
AFTER_IN=$(echo "$AFTER" | awk '{print $1}')
AFTER_OUT=$(echo "$AFTER" | awk '{print $2}')
echo ""

# Deltas
DELTA_IN=$((BEFORE_IN - AFTER_IN))
DELTA_OUT=$((BEFORE_OUT - AFTER_OUT))
TOTAL_BEFORE=$((BEFORE_IN + BEFORE_OUT))
TOTAL_AFTER=$((AFTER_IN + AFTER_OUT))
TOTAL_DELTA=$((TOTAL_BEFORE - TOTAL_AFTER))

# Percent (safe against div-by-zero)
PCT=0
if [ "$TOTAL_BEFORE" -gt 0 ]; then
  PCT=$((TOTAL_DELTA * 100 / TOTAL_BEFORE))
fi

echo "  ── results ─────────────────────────────────────────"
echo ""
printf "  %-20s  %10s  %10s  %10s\n" "" "input" "output" "total"
printf "  %-20s  %10s  %10s  %10s\n" "before" "$BEFORE_IN" "$BEFORE_OUT" "$TOTAL_BEFORE"
printf "  %-20s  %10s  %10s  %10s\n" "after" "$AFTER_IN" "$AFTER_OUT" "$TOTAL_AFTER"
printf "  %-20s  %10s  %10s  %10s\n" "delta" "$DELTA_IN" "$DELTA_OUT" "$TOTAL_DELTA"
echo ""
printf "  reduction: %d%%\n" "$PCT"
echo ""

# JSON output for CI or further processing
cat > "$WORKDIR/report.json" <<JSON
{
  "target": "$TARGET_REPO",
  "task": "$TASK_PROMPT",
  "before": {"input": $BEFORE_IN, "output": $BEFORE_OUT, "total": $TOTAL_BEFORE},
  "after": {"input": $AFTER_IN, "output": $AFTER_OUT, "total": $TOTAL_AFTER},
  "delta": {"input": $DELTA_IN, "output": $DELTA_OUT, "total": $TOTAL_DELTA},
  "reduction_pct": $PCT
}
JSON

echo "  JSON report: $WORKDIR/report.json"
cp "$WORKDIR/report.json" /tmp/cos-last-benchmark.json 2>/dev/null || true
echo "  Saved copy:  /tmp/cos-last-benchmark.json"
echo ""
