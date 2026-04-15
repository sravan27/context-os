#!/usr/bin/env bash
# Real before/after benchmark for Context OS.
#
# Runs a canonical Claude Code task against a target repo TWICE:
#   1. Without Context OS (baseline)
#   2. With Context OS installed
#
# Then reads Claude Code's JSON result to report ACTUAL input/output/cache
# tokens and cost delta. Not speculative — measured.
#
# Usage:
#   scripts/benchmark.sh                              # against current dir
#   scripts/benchmark.sh /path/to/repo                # against arbitrary repo
#   scripts/benchmark.sh /path/to/repo --model sonnet # override model
#   TASK_PROMPT="..." scripts/benchmark.sh            # override task
#
# Requires:
#   - claude CLI on PATH (Claude Code binary)
#   - git
#   - jq OR python3

set -euo pipefail

TARGET_REPO=""
MODEL=""
TASK_PROMPT_OVERRIDE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --model)
      MODEL="$2"; shift 2 ;;
    --model=*)
      MODEL="${1#*=}"; shift ;;
    --task)
      TASK_PROMPT_OVERRIDE="$2"; shift 2 ;;
    --task=*)
      TASK_PROMPT_OVERRIDE="${1#*=}"; shift ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)
      if [ -z "$TARGET_REPO" ]; then
        TARGET_REPO="$1"
      else
        echo "error: unexpected arg: $1" >&2; exit 1
      fi
      shift ;;
  esac
done

TARGET_REPO="${TARGET_REPO:-$(pwd)}"
# Resolve to absolute path so `file://` URI is valid
TARGET_REPO="$(cd "$TARGET_REPO" 2>/dev/null && pwd)" || {
  echo "error: target repo directory not found" >&2; exit 1;
}
TASK_PROMPT="${TASK_PROMPT_OVERRIDE:-${TASK_PROMPT:-List the top-level directory structure of this repo, then count source files by language. One line per language.}}"

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
if [ -n "$MODEL" ]; then
  echo "  Model:   $MODEL"
fi
echo "  Workdir: $WORKDIR"
echo ""

# Clone (shallow)
git clone --quiet --depth 1 "file://$TARGET_REPO" "$WORKDIR/repo" 2>&1 || {
  cp -R "$TARGET_REPO" "$WORKDIR/repo"
}

# Parse a claude --output-format json result file.
# Emits: "input_tokens cache_read cache_creation output_tokens cost_usd is_error"
parse_result() {
  local f=$1
  if command -v jq &>/dev/null; then
    jq -r '[
      (.usage.input_tokens // 0),
      (.usage.cache_read_input_tokens // 0),
      (.usage.cache_creation_input_tokens // 0),
      (.usage.output_tokens // 0),
      (.total_cost_usd // 0),
      (if .is_error == true then 1 else 0 end)
    ] | join(" ")' "$f"
  else
    python3 - "$f" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
u = d.get("usage", {}) or {}
ie = 1 if d.get("is_error") is True else 0
print(f'{u.get("input_tokens",0)} {u.get("cache_read_input_tokens",0)} {u.get("cache_creation_input_tokens",0)} {u.get("output_tokens",0)} {d.get("total_cost_usd",0)} {ie}')
PY
  fi
}

# Run the task once, return parsed result line on stdout. All progress to stderr.
run_task() {
  local label=$1
  local dir=$2
  local transcript="$WORKDIR/result-${label}.json"

  echo "  running '$label' task..." >&2

  local cmd=(claude --print --output-format json)
  if [ -n "$MODEL" ]; then
    cmd+=(--model "$MODEL")
  fi
  cmd+=("$TASK_PROMPT")

  if ! (cd "$dir" && "${cmd[@]}" > "$transcript" 2>"$WORKDIR/err-${label}.log"); then
    echo "  ! claude CLI exited non-zero for '$label'" >&2
    if [ -s "$WORKDIR/err-${label}.log" ]; then
      echo "    stderr:" >&2
      sed 's/^/      /' < "$WORKDIR/err-${label}.log" >&2
    fi
    return 1
  fi

  if [ ! -s "$transcript" ]; then
    echo "  ! claude CLI produced empty output for '$label'" >&2
    return 1
  fi

  local parsed
  parsed=$(parse_result "$transcript")
  local is_err
  is_err=$(echo "$parsed" | awk '{print $6}')
  if [ "$is_err" = "1" ]; then
    local err_msg
    if command -v jq &>/dev/null; then
      err_msg=$(jq -r '.result // .error // "unknown error"' "$transcript")
    else
      err_msg=$(python3 -c "import json;d=json.load(open('$transcript'));print(d.get('result') or d.get('error') or 'unknown error')")
    fi
    echo "  ! claude returned is_error=true for '$label': $err_msg" >&2
    echo "    (try: scripts/benchmark.sh $TARGET_REPO --model sonnet)" >&2
    return 1
  fi

  echo "$parsed"
}

# BEFORE: no Context OS
echo "  [baseline: no Context OS]"
BEFORE=$(run_task "before" "$WORKDIR/repo")
BEFORE_IN=$(echo "$BEFORE" | awk '{print $1}')
BEFORE_CACHE_R=$(echo "$BEFORE" | awk '{print $2}')
BEFORE_CACHE_W=$(echo "$BEFORE" | awk '{print $3}')
BEFORE_OUT=$(echo "$BEFORE" | awk '{print $4}')
BEFORE_COST=$(echo "$BEFORE" | awk '{print $5}')
echo ""

# Install Context OS in a fresh copy
cp -R "$WORKDIR/repo" "$WORKDIR/repo-cos"
(cd "$WORKDIR/repo-cos" && bash "$SETUP_SH" >/dev/null 2>&1)

# AFTER: with Context OS
echo "  [with Context OS]"
AFTER=$(run_task "after" "$WORKDIR/repo-cos")
AFTER_IN=$(echo "$AFTER" | awk '{print $1}')
AFTER_CACHE_R=$(echo "$AFTER" | awk '{print $2}')
AFTER_CACHE_W=$(echo "$AFTER" | awk '{print $3}')
AFTER_OUT=$(echo "$AFTER" | awk '{print $4}')
AFTER_COST=$(echo "$AFTER" | awk '{print $5}')
echo ""

# Deltas (cache-aware totals: input + cache_read + cache_write + output)
BEFORE_TOTAL=$((BEFORE_IN + BEFORE_CACHE_R + BEFORE_CACHE_W + BEFORE_OUT))
AFTER_TOTAL=$((AFTER_IN + AFTER_CACHE_R + AFTER_CACHE_W + AFTER_OUT))
DELTA_IN=$((BEFORE_IN - AFTER_IN))
DELTA_OUT=$((BEFORE_OUT - AFTER_OUT))
DELTA_TOTAL=$((BEFORE_TOTAL - AFTER_TOTAL))

PCT=0
if [ "$BEFORE_TOTAL" -gt 0 ]; then
  PCT=$((DELTA_TOTAL * 100 / BEFORE_TOTAL))
fi

# Cost delta (float math via awk)
COST_DELTA=$(awk "BEGIN { printf \"%.4f\", $BEFORE_COST - $AFTER_COST }")
COST_PCT=0
if awk "BEGIN { exit !($BEFORE_COST > 0) }"; then
  COST_PCT=$(awk "BEGIN { printf \"%.1f\", ($BEFORE_COST - $AFTER_COST) * 100 / $BEFORE_COST }")
fi

BEFORE_COST_FMT=$(awk "BEGIN { printf \"%.4f\", $BEFORE_COST }")
AFTER_COST_FMT=$(awk "BEGIN { printf \"%.4f\", $AFTER_COST }")

echo "  ── results ─────────────────────────────────────────"
echo ""
printf "  %-10s  %10s  %10s  %10s  %10s  %12s\n" "" "input" "cache_r" "cache_w" "output" "cost_usd"
printf "  %-10s  %10d  %10d  %10d  %10d  %12s\n" "before" "$BEFORE_IN" "$BEFORE_CACHE_R" "$BEFORE_CACHE_W" "$BEFORE_OUT" "$BEFORE_COST_FMT"
printf "  %-10s  %10d  %10d  %10d  %10d  %12s\n" "after"  "$AFTER_IN"  "$AFTER_CACHE_R"  "$AFTER_CACHE_W"  "$AFTER_OUT"  "$AFTER_COST_FMT"
printf "  %-10s  %10d  %10s  %10s  %10d  %12s\n" "delta"  "$DELTA_IN"  "-"               "-"               "$DELTA_OUT"  "$COST_DELTA"
echo ""
printf "  token reduction: %d%%    cost reduction: %s%%\n" "$PCT" "$COST_PCT"
echo ""

# JSON output for CI or further processing
cat > "$WORKDIR/report.json" <<JSON
{
  "target": "$TARGET_REPO",
  "task": "$TASK_PROMPT",
  "model": "${MODEL:-default}",
  "before": {
    "input_tokens": $BEFORE_IN,
    "cache_read_input_tokens": $BEFORE_CACHE_R,
    "cache_creation_input_tokens": $BEFORE_CACHE_W,
    "output_tokens": $BEFORE_OUT,
    "total_tokens": $BEFORE_TOTAL,
    "total_cost_usd": $BEFORE_COST
  },
  "after": {
    "input_tokens": $AFTER_IN,
    "cache_read_input_tokens": $AFTER_CACHE_R,
    "cache_creation_input_tokens": $AFTER_CACHE_W,
    "output_tokens": $AFTER_OUT,
    "total_tokens": $AFTER_TOTAL,
    "total_cost_usd": $AFTER_COST
  },
  "delta": {
    "input_tokens": $DELTA_IN,
    "output_tokens": $DELTA_OUT,
    "total_tokens": $DELTA_TOTAL,
    "total_cost_usd": $COST_DELTA
  },
  "token_reduction_pct": $PCT,
  "cost_reduction_pct": $COST_PCT
}
JSON

echo "  JSON report: $WORKDIR/report.json"
cp "$WORKDIR/report.json" /tmp/cos-last-benchmark.json 2>/dev/null || true
echo "  Saved copy:  /tmp/cos-last-benchmark.json"
echo ""
