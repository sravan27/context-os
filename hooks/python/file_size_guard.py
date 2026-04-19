#!/usr/bin/env python3
"""
file_size_guard.py — Context OS PreToolUse hook.

Blocks `Read` calls on files larger than a threshold when no offset/limit is
set. Nudges Claude to use offset+limit or delegate to the `explorer` Haiku
subagent, rather than blow 10k-20k tokens on a generated or lockfile read.

Thresholds (env-overridable):
- CONTEXT_OS_FILE_SIZE_THRESHOLD (default: 1500 lines) — warn/block boundary
- CONTEXT_OS_FILE_SIZE_HARD (default: 5000 lines) — above this, always block

Disable entirely: CONTEXT_OS_FILE_SIZE_GUARD=0

Fail-open: any error exits 0 and allows the read. Never breaks a user session.

Protocol:
- Reads JSON from stdin (hook input)
- Exit 0: allow tool call
- Exit 2: block with stderr message (Claude sees it, retries with offset)
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

    # User explicitly requested a slice — never block.
    if inp.get("offset") is not None or inp.get("limit") is not None:
        return 0

    # Non-existent paths are handled by the tool itself.
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

    # Count lines cheaply. Stop at hard_cap + 1 so we know if we're over it.
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

    # Over threshold — compute human-readable size label.
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
