#!/usr/bin/env python3
"""
savings_tracker.py — Stop hook that turns context-os's invisible token savings
into a visible, personal, accumulating number.

The problem with auto_context (context-os's flagship feature): it works
silently. It saves ~40% of first-turn tokens, but the user never SEES it.
Invisible wins don't build habits, don't earn trust, and don't get shared.
Every other dev tool that became sticky — GitHub's contribution graph, Spotify
Wrapped, language-learning streaks — made an invisible quantity visible and
let it accumulate.

This hook closes that loop. After each session it:

  1. Reads the transcript to find every file Claude actually opened (Read).
  2. Reads `.context-os/savings/suggestions.jsonl` (written by auto_context)
     to find every file context-os surfaced this session.
  3. Counts HITS — files context-os pointed at that Claude went on to open
     WITHOUT a Glob/Grep to find them. Each hit is one exploration sequence
     the agent skipped.
  4. Estimates tokens saved (conservative, calibrated well below the measured
     live-A/B delta) and appends a per-session record to the ledger.
  5. Updates a tiny cached aggregate (`total.json`) the statusline reads.
  6. Prints a one-line receipt to the terminal — the dopamine hit — plus a
     milestone celebration when the running total crosses a round number.

No phone-home. Local JSONL + one cached JSON. Fail-open on every error.

Honesty notes:
  - A "hit" is conservative: a suggested file that was also Read, counted
    once per session regardless of how many times it was opened.
  - tokens-saved is an ESTIMATE. Default 8,000 tok/hit, env-overridable via
    CONTEXT_OS_SAVINGS_PER_HIT. The live A/B (python/evals/reports/
    live-session-bench-stats.md) measured ~21k tok/prompt aggregate delta;
    we deliberately credit less than half of that per hit so the running
    total under-claims rather than over-claims.
"""
import json
import os
import sys
import time
from pathlib import Path

SAVINGS_DIR_NAME = ".context-os/savings"
SUGGESTIONS_FILE = "suggestions.jsonl"
LEDGER_FILE = "ledger.jsonl"
TOTAL_FILE = "total.json"

DEFAULT_TOKENS_PER_HIT = 8000
# Round-number milestones (tokens). Crossing one this session = celebration.
MILESTONES = [
    100_000, 250_000, 500_000, 1_000_000, 2_500_000, 5_000_000,
    10_000_000, 25_000_000, 50_000_000, 100_000_000,
]
# Control-arm average tokens/prompt from the live A/B — used to translate
# saved tokens into "prompts of runway" in the terminal receipt.
TOKENS_PER_PROMPT = 50_000


def _abspath(p, cwd):
    if not p:
        return ""
    try:
        if os.path.isabs(p):
            return os.path.normpath(p)
        return os.path.normpath(os.path.join(cwd, p))
    except Exception:
        return p


def _matches(suggested_abs, read_abs_set, read_suffixes):
    """A suggested file is a hit if Claude opened the same path, or a path
    that ends with the suggested one (handles abs/rel + subdir mismatch)."""
    if suggested_abs in read_abs_set:
        return True
    tail = suggested_abs.lstrip("/")
    for r in read_abs_set:
        if r.endswith("/" + tail) or tail.endswith("/" + r.lstrip("/")):
            return True
    # basename fallback only when the basename is distinctive (has a dir part)
    base = os.path.basename(suggested_abs)
    if base and "/" in suggested_abs and base in read_suffixes:
        return True
    return False


def parse_transcript_reads(path):
    """Return (read_abspaths:set, turns:int, total_tokens:int)."""
    reads = set()
    turns = 0
    total = 0
    try:
        lines = Path(path).open("r", encoding="utf-8", errors="replace").readlines()
    except OSError:
        return reads, turns, total
    for line in lines:
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = evt.get("message") or {}
        usage = msg.get("usage") or evt.get("usage") or {}
        if usage:
            turns += 1
            total += (usage.get("input_tokens", 0) or 0)
            total += (usage.get("output_tokens", 0) or 0)
            total += (usage.get("cache_creation_input_tokens", 0) or 0)
        content = msg.get("content") or []
        if isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and b.get("name") == "Read":
                    fp = (b.get("input") or {}).get("file_path", "")
                    if fp:
                        reads.add(os.path.normpath(fp))
    return reads, turns, total


def read_suggestions(savings_dir, session_id, cwd):
    """Union of files context-os suggested this session + suggestion count."""
    suggested = set()
    n_suggestions = 0
    f = savings_dir / SUGGESTIONS_FILE
    if not f.exists():
        return suggested, n_suggestions
    try:
        for line in f.open("r", encoding="utf-8", errors="replace"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if session_id and rec.get("session") != session_id:
                continue
            n_suggestions += 1
            for p in rec.get("files", []):
                ap = _abspath(p, cwd)
                if ap:
                    suggested.add(ap)
    except OSError:
        pass
    return suggested, n_suggestions


def load_total(savings_dir):
    f = savings_dir / TOTAL_FILE
    try:
        return json.loads(f.read_text())
    except (OSError, json.JSONDecodeError):
        return {
            "tokens_saved": 0, "hits": 0, "sessions": 0,
            "first_date": None, "last_date": None, "streak": 0,
            "milestone": 0,
        }


def compute_streak(prev_total, today):
    """Consecutive-day streak. Increments on a new day, resets if a day
    was skipped, holds if same day."""
    last = prev_total.get("last_date")
    streak = prev_total.get("streak", 0) or 0
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
    return 1  # gap > 1: streak broken


def main():
    if os.environ.get("CONTEXT_OS_SAVINGS") == "0":
        return 0
    try:
        per_hit = int(os.environ.get("CONTEXT_OS_SAVINGS_PER_HIT",
                                     str(DEFAULT_TOKENS_PER_HIT)))
    except ValueError:
        per_hit = DEFAULT_TOKENS_PER_HIT

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
    suggested, n_suggestions = read_suggestions(savings_dir, session_id, cwd)
    if n_suggestions == 0:
        return 0  # auto_context never fired this session — nothing to credit

    reads, turns, total_tokens = parse_transcript_reads(transcript)
    read_suffixes = {os.path.basename(r) for r in reads}

    hits = sorted(
        s for s in suggested if _matches(s, reads, read_suffixes)
    )
    n_hits = len(hits)
    tokens_saved = n_hits * per_hit

    today = time.strftime("%Y-%m-%d")
    prev = load_total(savings_dir)
    prev_saved = prev.get("tokens_saved", 0) or 0
    new_total_saved = prev_saved + tokens_saved
    streak = compute_streak(prev, today)

    savings_dir.mkdir(parents=True, exist_ok=True)

    # Per-session ledger record.
    record = {
        "ts": time.time(),
        "date": today,
        "session": session_id[:12],
        "suggestions": n_suggestions,
        "suggested_files": len(suggested),
        "hits": n_hits,
        "reads": len(reads),
        "turns": turns,
        "session_tokens": total_tokens,
        "tokens_saved": tokens_saved,
        "per_hit": per_hit,
    }
    try:
        with (savings_dir / LEDGER_FILE).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        return 0

    # Cached aggregate (statusline reads this — keep it tiny).
    crossed = None
    for m in MILESTONES:
        if prev_saved < m <= new_total_saved:
            crossed = m
    total = {
        "tokens_saved": new_total_saved,
        "hits": (prev.get("hits", 0) or 0) + n_hits,
        "sessions": (prev.get("sessions", 0) or 0) + 1,
        "first_date": prev.get("first_date") or today,
        "last_date": today,
        "streak": streak,
        "milestone": crossed or prev.get("milestone", 0),
        "usd_per_mtok": 6.0,
    }
    try:
        (savings_dir / TOTAL_FILE).write_text(json.dumps(total))
    except OSError:
        pass

    # Terminal receipt — the visible payoff.
    if n_hits > 0:
        runway = tokens_saved / TOKENS_PER_PROMPT
        usd = new_total_saved / 1_000_000 * 6.0
        print(
            f"[context-os] receipt: {n_hits} hit"
            f"{'s' if n_hits != 1 else ''} → ~{tokens_saved:,} tokens saved "
            f"(~{runway:.1f} prompts of runway). "
            f"All-time: {new_total_saved:,} tok (~${usd:,.2f}) · "
            f"{streak}-day streak. /savings for the full picture.",
            file=sys.stderr,
        )
    if crossed:
        print(
            f"[context-os] *** MILESTONE: you've saved {crossed:,} tokens "
            f"with context-os. Share your card: /savings ***",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
