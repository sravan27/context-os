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
