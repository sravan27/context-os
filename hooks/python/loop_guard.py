#!/usr/bin/env python3
"""
loop_guard.py — PreToolUse hook that detects Read/Edit loops on the same file
and nudges Claude to step back instead of grinding.

Problem: A common failure mode is Claude editing the same file 5-10 times in
a row — test fails, read it again, edit, test fails, read, edit, ... The
symptom is a stuck loop burning tokens with no forward progress. Anthropic
has seen this in their telemetry (mentioned in the Claude Code best-practices
post). Users waste minutes + thousands of tokens before they notice.

Solution: Count Edit/Write calls per file per session. At THRESHOLD (default 5),
emit a non-blocking warning via stderr. At HARD_LIMIT (default 8), block with
exit 2 and tell Claude to stop and ask the user.

Output: stderr messages are visible to Claude; Claude can course-correct.

Zero dependencies (stdlib only). Runs in <10ms.
"""
import json
import os
import sys
import time
from pathlib import Path

WARN_THRESHOLD = int(os.environ.get("CONTEXT_OS_LOOP_WARN", "5"))
HARD_LIMIT = int(os.environ.get("CONTEXT_OS_LOOP_HARD", "8"))
WINDOW_SECONDS = 1800  # 30-min window — loops beyond this are probably new work
STATE_DIR = Path.home() / ".context-os" / "state"


def main() -> int:
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
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or ""
    )
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
    # Reset counter if previous edit was outside the window.
    if now - entry.get("last", now) > WINDOW_SECONDS:
        entry = {"count": 0, "first": now, "last": now}

    entry["count"] += 1
    entry["last"] = now
    state[file_path] = entry

    try:
        state_file.write_text(json.dumps(state))
    except OSError:
        pass

    count = entry["count"]
    short_path = os.path.relpath(file_path) if os.path.isabs(file_path) else file_path

    if count >= HARD_LIMIT:
        msg = (
            f"[context-os] STOP — edited {short_path} {count} times in this session. "
            f"This is almost certainly a loop. Ask the user before another edit. "
            f"Consider: reading the surrounding code, running tests to see real errors, "
            f"or trying a different approach entirely."
        )
        print(msg, file=sys.stderr)
        return 2  # Block — force a pause.

    if count == WARN_THRESHOLD:
        msg = (
            f"[context-os] Heads up: this is edit #{count} on {short_path}. "
            f"If the tests/builds still fail, step back and re-read the full file "
            f"before editing again — don't grind."
        )
        print(msg, file=sys.stderr)
        # Non-blocking warning.
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
