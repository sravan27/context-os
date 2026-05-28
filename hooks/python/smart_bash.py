#!/usr/bin/env python3
"""
smart_bash.py — Context OS PreToolUse hook (Bash). Closes the Bash blind spot.

`smart_read` only sees the `Read` tool. When Claude views a file via Bash —
`cat`, `head`, `tail` — the whole file content dumps into context unintercepted
and `Receipts` doesn't count it. In autonomous/agentic sessions Claude reaches
for Bash heavily (proven from real transcripts), so the slicing product was
deliberately missing where work actually happens.

This hook intercepts **only** the narrow, unambiguous case of a pure file
dump via Bash: a single safe view command, a single file argument, **zero**
shell metacharacters in the command string. Anything more complex (pipes,
redirects, command chains, multiple files, unrecognised flags) is allowed
through untouched. The rule is: if there is any doubt, allow.

When intercepted, the user-visible behaviour mirrors `smart_read`: stderr
shows the file's outline (signatures + line ranges from the graph) and
Claude reads only the slice it needs via the `Read` tool. Each interception
logs a `slices.jsonl` entry credited by `Receipts` at session end.

Disable: `CONTEXT_OS_SMART_BASH=0`. Threshold reuses
`CONTEXT_OS_SMART_READ_MIN` (default 400 lines). Once-per-file-per-session
state shared with `smart_read` under `~/.context-os/state/`.

Fail-open on every error.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".context-os" / "state"
CHARS_PER_TOKEN = 4
MAX_OUTLINE_ROWS = 80

# Whitelisted commands that dump the WHOLE file by default. Anything else
# (including `head`/`tail` — they default to 10 lines, intercepting their
# tiny output to show a larger outline would be net negative) is allowed.
SAFE_VIEW_CMDS = {"cat", "less", "more", "bat"}

# If ANY of these appear ANYWHERE in the command string, allow through —
# the command is doing more than a single-file dump (pipes, redirects,
# chains, substitutions, globs, quoting, env-var expansion).
SHELL_META = set("|&;<>()$`\\\"'*?[]{}~!#=")


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
    norm = rel.replace(os.sep, "/")
    for k, v in files.items():
        kk = k.replace(os.sep, "/")
        if kk.endswith("/" + norm) or norm.endswith("/" + kk):
            return v
    base = os.path.basename(rel)
    cand = [v for k, v in files.items() if os.path.basename(k) == base]
    return cand[0] if len(cand) == 1 else None


def parse_pure_dump(command):
    """Return the single file path if `command` is an unambiguous pure file
    dump, else None. Strict — any doubt returns None and the hook allows.

    Accepted shapes (no shell metacharacters anywhere):
        cat <file>     less <file>     more <file>     bat <file>

    Deliberately NOT included: `head`/`tail` (default 10 lines, too small a
    dump to be worth intercepting vs the outline cost).
    """
    if not command or not isinstance(command, str):
        return None
    # Reject anything that hints at shell composition. Even a single such
    # character means we cannot safely reason about file flow.
    if any(c in SHELL_META for c in command):
        return None
    tokens = command.split()
    if not tokens:
        return None
    cmd = tokens[0]
    if cmd not in SAFE_VIEW_CMDS:
        return None
    args = tokens[1:]
    # cat / less / more / bat: exactly one positional, no flags
    if cmd in SAFE_VIEW_CMDS:
        if len(args) == 1 and not args[0].startswith("-"):
            return args[0]
        return None
    return None


def _render_outline(rel, entry, total_lines, src_cmd):
    syms = entry.get("symbols") or []
    rows = []
    for s in syms:
        line = s.get("line", 1)
        end = s.get("end", line)
        sig = s.get("sig") or f"{s.get('kind','')} {s.get('name','')}".strip()
        rows.append((line, end, f"  L{line}-{end:<6} {sig}"))
    if not rows:
        return None, 0
    shown = rows[:MAX_OUTLINE_ROWS]
    body = "\n".join(r[2] for r in shown)
    more = len(rows) - len(shown)
    biggest = max(rows, key=lambda r: r[1] - r[0])
    ex_off, ex_end = biggest[0], biggest[1]
    ex_lim = max(1, ex_end - ex_off + 1)
    out = [
        f"[context-os] `{src_cmd}` would dump all {total_lines} lines of "
        f"`{rel}` into context for every turn until compaction. "
        f"Its structure ({len(rows)} symbols) — read the slice you need:",
        "",
        body,
    ]
    if more > 0:
        out.append(f"  … +{more} more symbols")
    out += [
        "",
        f"Use the Read tool, not a Bash dump — e.g. "
        f"Read(\"{rel}\", offset={ex_off}, limit={ex_lim}). Sliced reads are "
        f"never intercepted. To override (this session), re-run the same "
        f"command (won't be intercepted again) or set CONTEXT_OS_SMART_BASH=0.",
    ]
    return "\n".join(out), len(rows)


def _already_offered(session, rel):
    """Share state with smart_read so the same file isn't double-nagged."""
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
               "saved": max(0, full_tokens - outline_tokens),
               "via": "bash"}
        with open(os.path.join(d, "slices.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def main():
    if os.environ.get("CONTEXT_OS_SMART_BASH") == "0":
        return 0
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    if event.get("tool_name") != "Bash":
        return 0
    inp = event.get("tool_input") or {}
    command = inp.get("command")
    fp_arg = parse_pure_dump(command)
    if not fp_arg:
        return 0  # not a pure file dump — allow

    cwd = event.get("cwd") or os.getcwd()
    # Resolve to an absolute path; if it doesn't exist as a file, allow.
    path = fp_arg if os.path.isabs(fp_arg) else os.path.join(cwd, fp_arg)
    try:
        if not os.path.isfile(path):
            return 0
    except Exception:
        return 0
    try:
        threshold = int(os.environ.get("CONTEXT_OS_SMART_READ_MIN", "400"))
    except ValueError:
        threshold = 400

    graph = _load_graph(cwd)
    if not graph:
        return 0
    rel = _rel(path, cwd)
    entry = _file_entry(graph, rel, path)
    if not entry:
        return 0
    syms = entry.get("symbols") or []
    if len(syms) < 2:
        return 0  # too little structure to be worth slicing

    capped = _count_lines(path, threshold + 1)
    if capped <= threshold:
        return 0
    real_lines = max(entry.get("lines") or 0, capped)

    session = event.get("session_id", "") or ""
    if _already_offered(session, rel):
        return 0

    outline, n = _render_outline(rel, entry, real_lines, command)
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
