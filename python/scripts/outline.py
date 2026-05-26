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
