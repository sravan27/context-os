#!/usr/bin/env python3
"""
dedup_guard.py — PreToolUse hook that blocks duplicate Read/Glob/Grep calls
within a session.

Problem: Claude Code frequently re-reads the same file or re-runs the same
Glob/Grep within a single session. Each duplicate call re-pays the cost of
the tool response as input tokens on the next turn. On a 2K-line file,
a duplicate Read burns ~5K input tokens for no new information.

Solution: Track (tool_name, args_hash) per session. If we've seen it within
TTL seconds, block with exit 2 and tell Claude to use the previous result
from conversation history.

Inputs (stdin JSON from Claude Code):
  {
    "session_id": "...",
    "tool_name": "Read"|"Glob"|"Grep",
    "tool_input": {...}
  }

Output:
  exit 0 — allow the tool call
  exit 2 + stderr — block the tool call, stderr shown to Claude

Storage: ~/.context-os/state/dedup-<session_id>.json
  Self-cleans entries older than TTL on every call.
  Self-deletes file after SESSION_MAX_AGE_SECONDS.

Zero dependencies (stdlib only). Runs in <10ms.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

TTL_SECONDS = 600              # 10 minutes — duplicate-read window
SESSION_MAX_AGE_SECONDS = 86400  # 24 hours — purge stale session files
STATE_DIR = Path.home() / ".context-os" / "state"


def args_hash(tool_name: str, tool_input: dict) -> str:
    """Stable hash of a tool call's distinguishing inputs."""
    if tool_name == "Read":
        key = tool_input.get("file_path", "")
        offset = tool_input.get("offset")
        limit = tool_input.get("limit")
        if offset is not None or limit is not None:
            key += f"#{offset or 0}:{limit or 0}"
    elif tool_name == "Glob":
        key = tool_input.get("pattern", "") + "|" + tool_input.get("path", "")
    elif tool_name == "Grep":
        parts = [
            tool_input.get("pattern", ""),
            tool_input.get("path", ""),
            tool_input.get("glob", ""),
            tool_input.get("type", ""),
            str(tool_input.get("output_mode", "")),
            str(tool_input.get("-i", False)),
            str(tool_input.get("multiline", False)),
        ]
        key = "|".join(parts)
    else:
        key = json.dumps(tool_input, sort_keys=True)
    return hashlib.sha1(f"{tool_name}:{key}".encode()).hexdigest()[:16]


def prune_old_sessions(state_dir: Path, now: float) -> None:
    """Delete session state files older than SESSION_MAX_AGE_SECONDS."""
    try:
        for f in state_dir.glob("dedup-*.json"):
            try:
                if now - f.stat().st_mtime > SESSION_MAX_AGE_SECONDS:
                    f.unlink()
            except OSError:
                pass
    except OSError:
        pass


def main() -> int:
    # Disabled? Bail fast.
    if os.environ.get("CONTEXT_OS_DEDUP") == "0":
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0  # Fail open — never break the user's session.

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Read", "Glob", "Grep"):
        return 0

    tool_input = payload.get("tool_input") or {}
    session_id = payload.get("session_id", "default")

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"dedup-{session_id}.json"
    now = time.time()

    # Prune stale sessions occasionally (cheap — cap directory growth).
    if now % 10 < 1:
        prune_old_sessions(STATE_DIR, now)

    try:
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except (OSError, json.JSONDecodeError):
        state = {}

    # Evict expired entries.
    state = {k: v for k, v in state.items() if now - v.get("t", 0) < TTL_SECONDS}

    h = args_hash(tool_name, tool_input)
    if h in state:
        prev = state[h]
        age = int(now - prev["t"])
        # Block the duplicate.
        msg = (
            f"[context-os] Skipping duplicate {tool_name}: "
            f"already called with same args {age}s ago. "
            f"Use the previous result from conversation history instead of re-running."
        )
        # Persist the new access time too, so repeated retries are still blocked.
        state[h]["t"] = now
        try:
            state_file.write_text(json.dumps(state))
        except OSError:
            pass
        print(msg, file=sys.stderr)
        return 2  # Claude Code: exit 2 blocks the tool call.

    # First time in window — allow, record it.
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
        # Fail open on any unexpected error.
        sys.exit(0)
