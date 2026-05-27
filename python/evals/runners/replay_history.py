#!/usr/bin/env python3
"""
replay_history.py — validate the context-os stack on YOUR real Claude Code
history, for $0. No API key, no new calls.

Every past Claude Code session is logged at ~/.claude/projects/<slug>/*.jsonl:
real prompts, real tool calls, real token usage. This runner replays those
transcripts against the current graph + ranker and asks, counterfactually:

  smart_read (v2.10): of the whole-file Reads you actually did, how many were
    big indexed files smart_read would have intercepted — and how many tokens
    did those reads load into context? (Measured EXACTLY from the transcript's
    tool_result sizes — no estimation for the load.) Then: how many more turns
    did each of those files persist in context (re-sent every turn until
    compaction)?

  auto_context: of the times Claude actually ran Glob/Grep to find a file,
    how many would the ranker's top-5 have surfaced up front? (Segmented by
    navigation intent — build-session string-greps are excluded, not inflated.)

This is a BACKTEST (counterfactual), not a live A/B. It estimates what the
hooks WOULD have changed; Claude's real behaviour with the hints present can
differ. Whole-file load sizes are measured; outline sizes and the auto_context
collapse are estimated. Labelled honestly throughout.

Usage:
    python3 python/evals/runners/replay_history.py [--root R] [--all] [--min-lines N]

Defaults to transcripts for the current repo (the graph is repo-specific).
Exits 0 always (skips cleanly if no transcripts / no graph) — CI-safe.
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "hooks", "python"))

CHARS_PER_TOKEN = 4
USD_PER_MTOK = 6.0
OUTLINE_TOK_PER_SYM = 14          # ~ "L47-89  def charge(self, amount)"
NAV_HINTS = ("where", "find", "locate", "which file", "look for", "show me",
             "what file", "how does", "how is", "the function that",
             "the class that", "responsible for", "implement")


def approx_tokens(s):
    return max(1, len(s) // CHARS_PER_TOKEN)


def find_transcripts(root, scan_all):
    home = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(home):
        return []
    allj = sorted(glob.glob(os.path.join(home, "*", "*.jsonl")),
                  key=lambda p: -os.path.getsize(p))
    if scan_all:
        return allj
    slug = root.strip("/").replace("/", "-")
    same = [p for p in allj if slug in p]
    return same or allj[:1]   # fall back to the largest if no slug match


def parse(path):
    """Return (episodes, n_turns, billed_tokens).
    episode = {prompt, actions:[{name,file,cost,sliced}], has_search}."""
    try:
        lines = open(path, encoding="utf-8", errors="replace").readlines()
    except OSError:
        return [], 0, 0
    results = {}
    raw = []
    turns = billed = 0
    for line in lines:
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = evt.get("message") or {}
        role = msg.get("role") or evt.get("type")
        usage = msg.get("usage") or evt.get("usage") or {}
        if usage:
            turns += 1
            billed += (usage.get("input_tokens", 0) or 0)
            billed += (usage.get("output_tokens", 0) or 0)
            billed += (usage.get("cache_creation_input_tokens", 0) or 0)
        tools, text, has_result, has_text = [], [], False, False
        content = msg.get("content")
        if isinstance(content, str):
            text.append(content)
            has_text = bool(content.strip())
        elif isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                t = b.get("type")
                if t == "text" and (b.get("text") or "").strip():
                    has_text = True
                    text.append(b["text"])
                elif t == "tool_use":
                    tools.append((b.get("id"), b.get("name", "?"),
                                  b.get("input") or {}))
                elif t == "tool_result":
                    has_result = True
                    rid = b.get("tool_use_id")
                    rc = b.get("content")
                    txt = rc if isinstance(rc, str) else json.dumps(rc)[:200000]
                    if rid:
                        results[rid] = approx_tokens(txt or "")
        raw.append({"role": role, "tools": tools, "text": " ".join(text),
                    "is_prompt": role == "user" and has_text and not has_result})
    episodes, cur = [], None
    for e in raw:
        if e["is_prompt"]:
            cur = {"prompt": e["text"], "actions": [], "has_search": False}
            episodes.append(cur)
            continue
        if cur is None:
            cur = {"prompt": "", "actions": [], "has_search": False}
            episodes.append(cur)
        for (tid, name, inp) in e["tools"]:
            sliced = inp.get("offset") is not None or inp.get("limit") is not None
            f = inp.get("file_path", "") if name == "Read" else ""
            cur["actions"].append({"name": name, "file": f,
                                   "cost": results.get(tid, 0), "sliced": sliced})
            if name in ("Glob", "Grep"):
                cur["has_search"] = True
    return episodes, turns, billed


def graph_entry(graph, path, root):
    files = (graph or {}).get("files") or {}
    rel = os.path.relpath(path, root) if os.path.isabs(path) else path
    rel = rel.replace(os.sep, "/")
    if rel in files:
        return rel, files[rel]
    for k, v in files.items():
        kk = k.replace(os.sep, "/")
        if kk.endswith("/" + rel) or rel.endswith("/" + kk):
            return k, v
    base = os.path.basename(rel)
    cand = [(k, v) for k, v in files.items() if os.path.basename(k) == base]
    return cand[0] if len(cand) == 1 else (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--all", action="store_true", help="scan all projects, not just this repo")
    ap.add_argument("--min-lines", type=int, default=400)
    ap.add_argument("--compact-window", type=int, default=50,
                    help="assumed turns a file persists before AutoCompact "
                         "evicts it (caps the occupancy estimate honestly)")
    args = ap.parse_args()

    try:
        import auto_context as ac
    except Exception as e:
        print(f"[replay] cannot import auto_context: {e}; skipping.")
        return 0
    graph = ac.load_graph(args.root)
    if not graph:
        print("[replay] no repo graph; run build_repo_graph.py first. Skipping.")
        return 0
    transcripts = find_transcripts(args.root, args.all)
    if not transcripts:
        print("[replay] no Claude Code transcripts found; skipping (not a failure).")
        return 0

    min_tok = args.min_lines * 8   # ~tokens for a min-lines file
    # smart_read backtest
    sr_n = sr_loaded = sr_outline = sr_occupancy = 0
    sr_examples = []
    # auto_context backtest
    nav_n = nav_hit = other_n = other_hit = expl_tax = 0
    sessions = tot_turns = tot_billed = 0

    for tp in transcripts:
        episodes, turns, billed = parse(tp)
        if turns == 0:
            continue
        sessions += 1
        tot_turns += turns
        tot_billed += billed
        # linear turn index across the session for persistence
        turn_seen = 0
        for ep in episodes:
            for a in ep["actions"]:
                if a["name"] in ("Read", "Glob", "Grep", "Edit", "Write"):
                    turn_seen += 1
                if a["name"] == "Read" and a["file"] and not a["sliced"]:
                    rel, entry = graph_entry(graph, a["file"], args.root)
                    if not entry:
                        continue
                    syms = entry.get("symbols") or []
                    F = a["cost"]
                    if len(syms) >= 2 and F >= min_tok:
                        O = min(F, max(60, len(syms) * OUTLINE_TOK_PER_SYM))
                        sr_n += 1
                        sr_loaded += F
                        sr_outline += O
                        # Honest occupancy: a file persists only until the next
                        # AutoCompact, not for the whole (possibly 1000s-long)
                        # session. Cap remaining turns at the compaction window.
                        remaining = min(max(0, turns - turn_seen),
                                        args.compact_window)
                        sr_occupancy += (F - O) * remaining
                        if len(sr_examples) < 6:
                            sr_examples.append((rel, F, O, remaining))
            # auto_context backtest on explored episodes
            if ep["has_search"]:
                expl_tax += sum(
                    x["cost"] for x in ep["actions"]
                    if x["name"] in ("Glob", "Grep"))
                targets = [os.path.normpath(x["file"]) for x in ep["actions"]
                           if x["name"] == "Read" and x["file"]]
                is_nav = any(h in ep["prompt"].lower() for h in NAV_HINTS)
                if is_nav:
                    nav_n += 1
                else:
                    other_n += 1
                if targets and ep["prompt"]:
                    try:
                        hits = ac.rank(ep["prompt"], graph, 5, 4)
                    except Exception:
                        hits = []
                    sugg = {os.path.normpath(h["file"]) for h in hits}
                    matched = any(
                        t in sugg or any(t.endswith("/" + s) or s.endswith("/" + t)
                                         for s in sugg) for t in targets)
                    if matched:
                        if is_nav:
                            nav_hit += 1
                        else:
                            other_hit += 1

    sr_first = sr_loaded - sr_outline
    print()
    print("  context-os — replay on YOUR real Claude Code history ($0, no API)")
    print("  " + "═" * 62)
    print(f"  Scanned        {sessions} session(s) · {tot_turns:,} tool-turns · "
          f"{tot_billed:,} tokens billed")
    print(f"  Transcripts    {'all projects' if args.all else 'this repo'} "
          f"(~/.claude/projects)")
    print()
    print("  ── smart_read (structural slicing) ──────────────────────────")
    print(f"  Whole-file reads of big indexed files   {sr_n:>10,}")
    print(f"  Tokens those reads loaded into context  {sr_loaded:>10,}  (measured)")
    print(f"  If served as outlines instead (est.)    {sr_outline:>10,}")
    print(f"  First-load reduction (before slices)    {sr_first:>10,}  "
          f"(~${sr_first/1e6*USD_PER_MTOK:,.2f}, defensible floor)")
    print(f"  + re-sent each turn until compaction (≤{args.compact_window}): "
          f"{sr_occupancy:,} tok of context budget freed")
    if sr_examples:
        print("  e.g.:")
        for rel, F, O, rem in sr_examples:
            print(f"     {rel}: loaded {F:,} tok → outline ~{O:,}, "
                  f"carried ~{rem} more turns before compaction")
    print()
    print("  ── auto_context (retrieval) ─────────────────────────────────")
    print(f"  Real explorations (Glob/Grep episodes)  {nav_n + other_n:>10,}")
    print(f"  Measured exploration tax                {expl_tax:>10,}  tokens")
    nav_rate = (nav_hit / nav_n * 100) if nav_n else 0
    print(f"  Navigation-intent explorations          {nav_n:>10,}")
    print(f"  …ranker top-5 would have surfaced target {nav_hit:>9,}  "
          f"({nav_rate:.0f}%)")
    print(f"  Other (string-hunts a graph shouldn't collapse): {other_n}")
    print()
    print("  Caveat: BACKTEST on real data, not a live A/B. Load sizes are")
    print("  measured from your transcripts; outline sizes + the auto_context")
    print("  collapse are estimates. Claude's behaviour with hints present may")
    print("  differ. Occupancy token-turns are cache-discounted in $ but full")
    print("  in context budget (they push you to compaction / limits sooner).")
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[replay] error (non-fatal): {e}")
        sys.exit(0)
