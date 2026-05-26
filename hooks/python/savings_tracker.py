#!/usr/bin/env python3
"""
savings_tracker.py — Stop hook. Turns auto_context's invisible token savings
into a visible, personal, accumulating number — measured causally from the
session transcript, not estimated from a constant.

Why causal measurement matters
-------------------------------
A reviewer's first objection to any "we saved you X tokens" claim is: "that's
a made-up number." So we don't make one up. We read the transcript and
classify every prompt's first-turn behaviour:

  * ASSISTED — auto_context surfaced a file and Claude's FIRST tool action was
    a Read of that file, with no Glob/Grep before it. Exploration replaced.
  * EXPLORED — Claude ran Glob/Grep (and read wrong files) before finding the
    target. We MEASURE the token cost of that exploration from the actual
    tool_result sizes in the transcript.

The realized saving per assisted prompt is the *measured* average cost of an
exploration in THAT SAME SESSION — "a search cost you ~14,200 tokens here, and
context-os turned 8 searches into direct opens." When a session has no
exploration to calibrate against, we fall back to a conservative constant
(8k, ~⅖ of the 21k aggregate delta measured in the live A/B) and label the
number an estimate, never passing it off as measured.

Everything is local JSONL + one cached JSON. Fail-open on every error.
Disable with CONTEXT_OS_SAVINGS=0. Override per-hit credit with
CONTEXT_OS_SAVINGS_PER_HIT.
"""
import json
import os
import sys
import time
from pathlib import Path

SAVINGS_DIR_NAME = ".context-os/savings"
DEFAULT_TOKENS_PER_HIT = 8000          # conservative fallback (no baseline)
MEASURED_MIN, MEASURED_MAX = 1500, 15000  # clamp measured per-hit to credible band
MILESTONES = [100_000, 250_000, 500_000, 1_000_000, 2_500_000, 5_000_000,
              10_000_000, 25_000_000, 50_000_000, 100_000_000]
TOKENS_PER_PROMPT = 50_000             # control-arm avg from the live A/B
CHARS_PER_TOKEN = 4
SEARCH_TOOLS = {"Glob", "Grep"}


def approx_tokens(s):
    return max(1, len(s) // CHARS_PER_TOKEN)


def parse_iso(ts):
    if not ts or not isinstance(ts, str):
        return None
    try:
        return _dt_from_iso(ts)
    except Exception:
        return None


def _dt_from_iso(ts):
    from datetime import datetime
    t = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(t).timestamp()


def _abspath(p, cwd):
    if not p:
        return ""
    try:
        return os.path.normpath(p if os.path.isabs(p) else os.path.join(cwd, p))
    except Exception:
        return p


def _file_match(target_abs, candidate_set, candidate_suffixes):
    """target opened by Claude; candidate_set = suggested files (abspaths)."""
    if target_abs in candidate_set:
        return True
    tail = target_abs.lstrip("/")
    for c in candidate_set:
        if c.endswith("/" + tail) or tail.endswith("/" + c.lstrip("/")):
            return True
    base = os.path.basename(target_abs)
    return bool(base and "/" in target_abs and base in candidate_suffixes)


def parse_transcript(path):
    """Return ordered episodes + totals.

    episode = {
        "prompt_ts": float|None,
        "actions": [ {"name","file","cost"} ],   # in call order
        "has_search": bool,
    }
    Also returns (total_tokens, turns).
    """
    try:
        lines = Path(path).open("r", encoding="utf-8", errors="replace").readlines()
    except OSError:
        return [], 0, 0

    raw = []
    result_tokens = {}   # tool_use_id -> approx tokens of its result
    total_tokens = turns = 0

    for line in lines:
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = evt.get("message") or {}
        role = msg.get("role") or evt.get("type")
        ts = parse_iso(evt.get("timestamp"))
        usage = msg.get("usage") or evt.get("usage") or {}
        if usage:
            turns += 1
            total_tokens += (usage.get("input_tokens", 0) or 0)
            total_tokens += (usage.get("output_tokens", 0) or 0)
            total_tokens += (usage.get("cache_creation_input_tokens", 0) or 0)

        text_parts, tools, has_result, has_text = [], [], False, False
        content = msg.get("content")
        if isinstance(content, str):
            text_parts.append(content)
            has_text = bool(content.strip())
        elif isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text":
                    txt = b.get("text") or ""
                    if txt.strip():
                        has_text = True
                        text_parts.append(txt)
                elif bt == "tool_use":
                    tools.append((b.get("id"), b.get("name", "?"),
                                  b.get("input") or {}))
                elif bt == "tool_result":
                    has_result = True
                    rid = b.get("tool_use_id")
                    rc = b.get("content")
                    txt = rc if isinstance(rc, str) else json.dumps(rc)[:40000]
                    if rid:
                        result_tokens[rid] = approx_tokens(txt or "")
        raw.append({"role": role, "ts": ts, "tools": tools,
                    "is_prompt": role == "user" and has_text and not has_result})

    # Attribute result tokens to tool calls; build episodes.
    episodes = []
    cur = None
    for entry in raw:
        if entry["is_prompt"]:
            cur = {"prompt_ts": entry["ts"], "actions": [], "has_search": False}
            episodes.append(cur)
            continue
        if cur is None:
            cur = {"prompt_ts": None, "actions": [], "has_search": False}
            episodes.append(cur)
        for (tid, name, inp) in entry["tools"]:
            cost = result_tokens.get(tid, 0)
            f = ""
            if name == "Read":
                f = inp.get("file_path", "") or ""
            cur["actions"].append({"name": name, "file": f, "cost": cost})
            if name in SEARCH_TOOLS:
                cur["has_search"] = True
    return episodes, total_tokens, turns


def load_suggestions(savings_dir, session_id, cwd):
    """Return (sorted [(ts, abspath)], union_set, n_records)."""
    items, union, n = [], set(), 0
    f = savings_dir / "suggestions.jsonl"
    if not f.exists():
        return items, union, n
    try:
        for line in f.open("r", encoding="utf-8", errors="replace"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if session_id and rec.get("session") != session_id:
                continue
            n += 1
            ts = rec.get("ts")
            for p in rec.get("files", []):
                ap = _abspath(p, cwd)
                if ap:
                    items.append((ts if isinstance(ts, (int, float)) else None, ap))
                    union.add(ap)
    except OSError:
        pass
    items.sort(key=lambda x: (x[0] is None, x[0] or 0))
    return items, union, n


def analyze(episodes, sugg_items, sugg_union):
    """Causal classification + measured exploration cost.

    Returns dict with assisted_hits, explored_episodes, exploration_tokens,
    avg_search_cost, soft_hits.
    """
    have_ts = any(s[0] is not None for s in sugg_items) and \
        any(e["prompt_ts"] is not None for e in episodes)
    sugg_suffixes = {os.path.basename(a) for (_, a) in sugg_items}

    # episode end bounds (next prompt ts) for cumulative suggestion windows
    prompt_idx = [i for i, e in enumerate(episodes) if e["prompt_ts"] is not None]
    next_ts = {}
    for k, i in enumerate(prompt_idx):
        nxt = episodes[prompt_idx[k + 1]]["prompt_ts"] if k + 1 < len(prompt_idx) else float("inf")
        next_ts[i] = nxt

    assisted = explored = exploration_tokens = 0
    all_read_files = set()

    for i, ep in enumerate(episodes):
        actions = ep["actions"]
        for a in actions:
            if a["name"] == "Read" and a["file"]:
                all_read_files.add(os.path.normpath(a["file"]))
        if ep["has_search"]:
            explored += 1
            # exploration tokens: all Glob/Grep results + Reads that follow a
            # search within this episode (the "found it" reads after a hunt).
            seen_search = False
            for a in actions:
                if a["name"] in SEARCH_TOOLS:
                    seen_search = True
                    exploration_tokens += a["cost"]
                elif a["name"] == "Read" and seen_search:
                    exploration_tokens += a["cost"]

        # ASSISTED: first action is a Read of a suggested file, no search first.
        if not actions or actions[0]["name"] != "Read" or not actions[0]["file"]:
            continue
        first_file = os.path.normpath(actions[0]["file"])
        # build the suggestion set visible to this episode
        if have_ts and ep["prompt_ts"] is not None:
            bound = next_ts.get(i, float("inf"))
            cand = {a for (ts, a) in sugg_items
                    if ts is None or ts < bound}
        else:
            cand = set(sugg_union)
        if _file_match(first_file, cand, sugg_suffixes):
            assisted += 1

    soft_hits = len(sugg_union & all_read_files) if sugg_union else 0
    avg_search_cost = (exploration_tokens / explored) if explored else 0
    return {
        "assisted_hits": assisted,
        "explored_episodes": explored,
        "exploration_tokens": exploration_tokens,
        "avg_search_cost": avg_search_cost,
        "soft_hits": soft_hits,
    }


def load_total(savings_dir):
    try:
        return json.loads((savings_dir / "total.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {"tokens_saved": 0, "hits": 0, "sessions": 0,
                "first_date": None, "last_date": None, "streak": 0,
                "milestone": 0, "measured_sessions": 0}


def compute_streak(prev, today):
    last = prev.get("last_date")
    streak = prev.get("streak", 0) or 0
    if last == today:
        return max(1, streak)
    if last is None:
        return 1
    try:
        from datetime import date
        ly, lm, ld = (int(x) for x in last.split("-"))
        ty, tm, td = (int(x) for x in today.split("-"))
        gap = (date(ty, tm, td) - date(ly, lm, ld)).days
    except Exception:
        return 1
    if gap == 1:
        return streak + 1
    if gap <= 0:
        return max(1, streak)
    return 1


def main():
    if os.environ.get("CONTEXT_OS_SAVINGS") == "0":
        return 0
    env_per_hit = os.environ.get("CONTEXT_OS_SAVINGS_PER_HIT")
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    transcript = payload.get("transcript_path")
    session_id = payload.get("session_id", "") or ""
    cwd = payload.get("cwd") or os.getcwd()
    if not transcript or not os.path.exists(transcript):
        return 0

    savings_dir = Path(cwd) / SAVINGS_DIR_NAME
    sugg_items, sugg_union, n_sugg = load_suggestions(savings_dir, session_id, cwd)
    if n_sugg == 0:
        return 0  # auto_context never fired this session

    episodes, total_tokens, turns = parse_transcript(transcript)
    a = analyze(episodes, sugg_items, sugg_union)

    # Per-hit credit: measured if we have an exploration baseline, else estimate.
    if env_per_hit:
        try:
            per_hit = max(0, int(env_per_hit))
        except ValueError:
            per_hit = DEFAULT_TOKENS_PER_HIT
        method = "override"
    elif a["explored_episodes"] > 0 and a["avg_search_cost"] > 0:
        per_hit = int(max(MEASURED_MIN, min(a["avg_search_cost"], MEASURED_MAX)))
        method = "measured"
    else:
        per_hit = DEFAULT_TOKENS_PER_HIT
        method = "estimate"

    n_hits = a["assisted_hits"]
    tokens_saved = n_hits * per_hit

    today = time.strftime("%Y-%m-%d")
    prev = load_total(savings_dir)
    prev_saved = prev.get("tokens_saved", 0) or 0
    new_total = prev_saved + tokens_saved
    streak = compute_streak(prev, today)

    savings_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.time(), "date": today, "session": session_id[:12],
        "suggestions": n_sugg, "suggested_files": len(sugg_union),
        "hits": n_hits,                       # causal assisted hits (headline)
        "assisted_hits": n_hits,
        "soft_hits": a["soft_hits"],          # broad suggested∩read (context)
        "explored_episodes": a["explored_episodes"],
        "exploration_tokens": a["exploration_tokens"],
        "avg_search_cost": round(a["avg_search_cost"]),
        "per_hit": per_hit, "method": method,
        "turns": turns, "session_tokens": total_tokens,
        "tokens_saved": tokens_saved,
    }
    try:
        with (savings_dir / "ledger.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        return 0

    crossed = None
    for m in MILESTONES:
        if prev_saved < m <= new_total:
            crossed = m
    total = {
        "tokens_saved": new_total,
        "hits": (prev.get("hits", 0) or 0) + n_hits,
        "sessions": (prev.get("sessions", 0) or 0) + 1,
        "measured_sessions": (prev.get("measured_sessions", 0) or 0)
        + (1 if method == "measured" else 0),
        "first_date": prev.get("first_date") or today,
        "last_date": today, "streak": streak,
        "milestone": crossed or prev.get("milestone", 0),
        "usd_per_mtok": 6.0,
    }
    try:
        (savings_dir / "total.json").write_text(json.dumps(total))
    except OSError:
        pass

    if n_hits > 0:
        usd = new_total / 1_000_000 * 6.0
        if method == "measured":
            how = (f"a search cost ~{int(a['avg_search_cost']):,} tok here, "
                   f"measured across {a['explored_episodes']} that still explored")
        elif method == "estimate":
            how = "conservative estimate (no search to measure this session)"
        else:
            how = "per CONTEXT_OS_SAVINGS_PER_HIT"
        print(
            f"[context-os] receipt: {n_hits} prompt"
            f"{'s' if n_hits != 1 else ''} went straight to the right file "
            f"→ ~{tokens_saved:,} tokens saved ({how}). "
            f"All-time: {new_total:,} tok (~${usd:,.2f}) · {streak}-day streak. "
            f"/savings for the breakdown.",
            file=sys.stderr,
        )
    if crossed:
        print(
            f"[context-os] *** MILESTONE: {crossed:,} tokens saved with "
            f"context-os. Share your card: /savings ***",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
