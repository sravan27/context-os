#!/usr/bin/env python3
"""
prewarm.py — Context OS SessionStart hook.

Emits a compact "session intelligence brief" on session start, prepended as
additional context by Claude Code. Four parts, in order:

  1. Git state: branch, uncommitted file count, divergence from main.
  2. Graph freshness: auto-rebuilds in background if stale.
  3. Hot files (top 3) from the repo graph.
  4. Last session's notable issues (from the most recent .context-os/
     session-reports/*.md, if any): duplicate tool calls caught, edit loops,
     files that ate the most tokens.

Zero-dep stdlib. Fail-open. Silent if no signals.

Env:
- CONTEXT_OS_PREWARM=0                 disable entirely
- CONTEXT_OS_GRAPH_AUTOBUILD=0         disable background graph rebuild
- CONTEXT_OS_GRAPH_MAX_AGE_DAYS=7      rebuild if graph older than N days
- CONTEXT_OS_GRAPH_MAX_CHANGED=20      rebuild if > N source files newer

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
import time

SRC_EXTS = (".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".rs", ".go")
EXCLUDE_DIRS = {
    "node_modules", "target", "dist", "build", ".next", ".git", ".venv",
    "venv", "__pycache__", ".pytest_cache", "coverage", ".turbo", ".cache",
    ".mypy_cache", ".ruff_cache", ".tox", "bower_components", "vendor",
    ".idea", ".vscode", ".context-os",
}


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


def graph_freshness(cwd, scan_cap=800):
    """Return dict(age_days, changed, seen) or None if no graph exists."""
    path = os.path.join(cwd, ".context-os", "repo-graph.json")
    if not os.path.isfile(path):
        return None
    try:
        graph_mt = os.path.getmtime(path)
    except OSError:
        return None
    now = time.time()
    age_days = (now - graph_mt) / 86400
    newer = 0
    seen = 0
    for dirpath, dirnames, filenames in os.walk(cwd):
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fn in filenames:
            if not fn.endswith(SRC_EXTS):
                continue
            seen += 1
            if seen > scan_cap:
                break
            try:
                if os.path.getmtime(os.path.join(dirpath, fn)) > graph_mt:
                    newer += 1
            except OSError:
                pass
        if seen > scan_cap:
            break
    return {"age_days": age_days, "changed": newer, "seen": seen}


def is_stale(fresh, max_age_days, max_changed):
    if fresh is None:
        return False, None
    if fresh["age_days"] > max_age_days:
        return True, f"graph {fresh['age_days']:.0f}d old"
    if fresh["changed"] > max_changed:
        return True, f"{fresh['changed']} source files newer than graph"
    return False, None


def find_builder(cwd):
    """Locate build_repo_graph.py. Checks installed location first, then the
    hook's sibling dir (dev mode)."""
    candidates = [
        os.path.join(cwd, ".context-os", "build_repo_graph.py"),
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "build_repo_graph.py"
        ),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def spawn_rebuild(cwd):
    """Fire-and-forget background rebuild. Returns True on successful spawn."""
    builder = find_builder(cwd)
    if not builder:
        return False
    try:
        subprocess.Popen(
            [sys.executable, builder, cwd],
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception:
        return False


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

    # 3. Graph freshness check + background rebuild if stale.
    try:
        max_age = int(os.environ.get("CONTEXT_OS_GRAPH_MAX_AGE_DAYS", "7"))
        max_changed = int(os.environ.get("CONTEXT_OS_GRAPH_MAX_CHANGED", "20"))
    except ValueError:
        max_age, max_changed = 7, 20
    fresh = graph_freshness(cwd)
    stale, reason = is_stale(fresh, max_age, max_changed)
    if stale:
        autobuild = os.environ.get("CONTEXT_OS_GRAPH_AUTOBUILD") != "0"
        if autobuild and spawn_rebuild(cwd):
            sections.append(
                f"Graph: {reason} — rebuilding in background. "
                f"Auto-context will use the fresh graph next session."
            )
        else:
            sections.append(
                f"Graph: {reason} — run `/rebuild-graph` to refresh."
            )

    # 4. Hot files from graph
    hot = graph_hot(cwd)
    if hot:
        bits = [f"`{h['path']}` ({h['touches']})" for h in hot]
        sections.append("Hot (90d): " + ", ".join(bits) + ".")

    # 5. Last session's notable issues
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
