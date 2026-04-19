#!/usr/bin/env python3
"""
prewarm.py — Context OS SessionStart hook.

Emits a compact "session intelligence brief" on session start, prepended as
additional context by Claude Code. Three parts, in order:

  1. Git state: branch, uncommitted file count, divergence from main.
  2. Hot files (top 3) from the repo graph.
  3. Last session's notable issues (from the most recent .context-os/
     session-reports/*.md, if any): duplicate tool calls caught, edit loops,
     files that ate the most tokens.

Zero-dep stdlib. Fail-open. Silent if no signals.

Env:
- CONTEXT_OS_PREWARM=0    disable entirely

Protocol:
- stdin: {"session_id": "...", "cwd": "..."}  (from SessionStart)
- stdout: text block prepended as context
- exit 0 always
"""
import glob
import json
import os
import subprocess
import sys


def git(cmd, cwd):
    try:
        return subprocess.check_output(
            ["git", "-C", cwd] + cmd,
            stderr=subprocess.DEVNULL, text=True, timeout=3,
        ).strip()
    except Exception:
        return ""


def git_state(cwd):
    if not os.path.isdir(os.path.join(cwd, ".git")):
        return None
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) or "detached"
    porcelain = git(["status", "--porcelain"], cwd)
    dirty = len([l for l in porcelain.splitlines() if l.strip()])
    # divergence from main/master
    ahead = behind = 0
    base = None
    for b in ("main", "master"):
        if git(["rev-parse", "--verify", "--quiet", b], cwd):
            base = b
            break
    if base and branch != base:
        rev_list = git(["rev-list", "--left-right", "--count",
                        f"{base}...HEAD"], cwd)
        parts = rev_list.split()
        if len(parts) == 2:
            try:
                behind, ahead = int(parts[0]), int(parts[1])
            except ValueError:
                pass
    return {"branch": branch, "dirty": dirty,
            "base": base, "ahead": ahead, "behind": behind}


def graph_hot(cwd, top_n=3):
    path = os.path.join(cwd, ".context-os", "repo-graph.json")
    try:
        with open(path, "r") as f:
            g = json.load(f)
    except Exception:
        return []
    hot = g.get("hot_files") or []
    return hot[:top_n]


def last_session_report(cwd):
    """Return (path, notable_lines[]) or (None, [])."""
    pattern = os.path.join(cwd, ".context-os", "session-reports", "*.md")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        return None, []
    try:
        with open(files[0], "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return None, []
    notable = []
    # Grep a few headline metrics if present
    for kw, label in [
        ("duplicate", "duplicates caught"),
        ("loop", "edit loops flagged"),
        ("top file", "top file"),
    ]:
        for line in content.splitlines():
            if kw in line.lower():
                t = line.strip("-* ").strip()
                if t and t not in notable:
                    notable.append(t)
                    break
    return os.path.basename(files[0]), notable[:3]


def handoff_exists(cwd):
    for candidate in (
        ".context-os/handoff.md",
        ".context-os/restart-packet.md",
    ):
        p = os.path.join(cwd, candidate)
        if os.path.isfile(p):
            return candidate
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

    # 1. Handoff reminder (highest priority)
    ho = handoff_exists(cwd)
    if ho:
        sections.append(f"Handoff packet found at `{ho}` — resume from there "
                        f"instead of re-planning.")

    # 2. Git state
    g = git_state(cwd)
    if g:
        parts = [f"branch `{g['branch']}`"]
        if g["dirty"]:
            parts.append(f"{g['dirty']} uncommitted")
        if g["base"] and g["ahead"]:
            parts.append(f"{g['ahead']} commits ahead of `{g['base']}`")
        if g["base"] and g["behind"]:
            parts.append(f"{g['behind']} behind `{g['base']}`")
        sections.append("Git: " + ", ".join(parts) + ".")

    # 3. Hot files from graph
    hot = graph_hot(cwd)
    if hot:
        bits = [f"`{h['path']}` ({h['touches']})" for h in hot]
        sections.append("Hot (90d): " + ", ".join(bits) + ".")

    # 4. Last session's notable issues
    _, notable = last_session_report(cwd)
    if notable:
        sections.append("Last session flagged: " + "; ".join(notable) + ".")

    if not sections:
        return 0

    out = ["<context-os:prewarm>"]
    out.extend(sections)
    out.append("Disable: CONTEXT_OS_PREWARM=0.")
    out.append("</context-os:prewarm>")
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
