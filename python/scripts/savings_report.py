#!/usr/bin/env python3
"""
savings_report.py — backend for the `/savings` slash command.

Reads the savings ledger written by savings_tracker.py (Stop hook) and prints
a terminal dashboard plus a copy-paste shareable card. This is the surface
that makes context-os's value felt: a personal, accumulating number with a
day-streak, a dollar figure, and rate-limit runway framing.

Usage:
    python3 savings_report.py [--root DIR] [--json] [--card-only]

Honesty: every number is derived from the local ledger. tokens-saved is the
conservative per-hit estimate recorded at session time (see savings_tracker.py
docstring). Nothing phones home.
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

SAVINGS_DIR_NAME = ".context-os/savings"
TOKENS_PER_PROMPT = 50_000  # control-arm avg from the live A/B
USD_PER_MTOK = 6.0          # conservative blended Sonnet pricing


def load_ledger(root):
    path = os.path.join(root, SAVINGS_DIR_NAME, "ledger.jsonl")
    rows = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return rows


def _bar(frac, width=24):
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    return "█" * filled + "░" * (width - filled)


def aggregate(rows):
    tot_saved = sum(r.get("tokens_saved", 0) or 0 for r in rows)
    tot_hits = sum(r.get("hits", 0) or 0 for r in rows)
    tot_sugg = sum(r.get("suggestions", 0) or 0 for r in rows)
    tot_sugg_files = sum(r.get("suggested_files", 0) or 0 for r in rows)
    tot_explored = sum(r.get("explored_episodes", 0) or 0 for r in rows)
    tot_expl_tok = sum(r.get("exploration_tokens", 0) or 0 for r in rows)
    tot_slices = sum(r.get("slices", 0) or 0 for r in rows)
    tot_slice_saved = sum(r.get("slice_saved", 0) or 0 for r in rows)
    tot_search_saved = sum(r.get("search_saved",
                                 r.get("tokens_saved", 0)) or 0 for r in rows)
    measured_rows = sum(1 for r in rows if r.get("method") == "measured")
    measured_saved = sum(r.get("tokens_saved", 0) or 0
                         for r in rows if r.get("method") == "measured")
    by_day = defaultdict(int)
    for r in rows:
        by_day[r.get("date", "?")] += r.get("tokens_saved", 0) or 0
    days = sorted(d for d in by_day if d and d != "?")
    # streak: consecutive days up to the most recent ledger day
    streak = 0
    if days:
        from datetime import date, timedelta
        try:
            cur = date.fromisoformat(days[-1])
            present = {date.fromisoformat(d) for d in days}
            while cur in present:
                streak += 1
                cur = cur - timedelta(days=1)
        except ValueError:
            streak = len(days)
    # this week
    week_saved = 0
    if days:
        from datetime import date, timedelta
        try:
            today = date.fromisoformat(days[-1])
            wk_start = today - timedelta(days=6)
            for d, v in by_day.items():
                try:
                    if date.fromisoformat(d) >= wk_start:
                        week_saved += v
                except ValueError:
                    pass
        except ValueError:
            pass
    return {
        "tokens_saved": tot_saved,
        "hits": tot_hits,
        "suggestions": tot_sugg,
        "suggested_files": tot_sugg_files,
        "sessions": len(rows),
        "days_active": len(days),
        "streak": streak,
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
        "week_saved": week_saved,
        "by_day": dict(by_day),
        "hit_rate": (tot_hits / tot_sugg_files) if tot_sugg_files else 0.0,
        "explored_episodes": tot_explored,
        "exploration_tokens": tot_expl_tok,
        "avg_search_cost": (tot_expl_tok / tot_explored) if tot_explored else 0,
        "measured_rows": measured_rows,
        "measured_saved": measured_saved,
        "measured_share": (measured_saved / tot_saved) if tot_saved else 0.0,
        "slices": tot_slices,
        "slice_saved": tot_slice_saved,
        "search_saved": tot_search_saved,
    }


def make_card(a):
    saved = a["tokens_saved"]
    usd = saved / 1_000_000 * USD_PER_MTOK
    runway = saved / TOKENS_PER_PROMPT
    W = 45  # inner width

    def row(s):
        return "│ " + s.ljust(W - 2) + " │"

    def center(s):
        return "│" + s.center(W) + "│"

    searches = f"{a['hits']:,} search{'es' if a['hits'] != 1 else ''}"
    third = (f"avg search cost {int(a['avg_search_cost']):,} tok — measured"
             if a["avg_search_cost"] > 0
             else f"{a['hits']:,} would-be searches, skipped")
    lines = [
        "╭" + "─" * W + "╮",
        center("context-os · receipts"),
        "├" + "─" * W + "┤",
        row(f"{saved:,} tokens saved   (~${usd:,.2f})"),
        row(f"{searches} replaced by a direct open"),
        row(third),
        row(f"~{runway:.0f} prompts of runway  ·  {a['streak']}-day streak"),
        "├" + "─" * W + "┤",
        row("github.com/sravan27/context-os · MIT"),
        "╰" + "─" * W + "╯",
    ]
    return "\n".join(lines)


def make_report(a):
    saved = a["tokens_saved"]
    usd = saved / 1_000_000 * USD_PER_MTOK
    runway = saved / TOKENS_PER_PROMPT
    week_usd = a["week_saved"] / 1_000_000 * USD_PER_MTOK
    out = []
    out.append("")
    out.append("  context-os — your savings")
    out.append("  " + "─" * 44)
    out.append("")
    runway_str = f"{runway:,.1f}" if runway < 10 else f"{runway:,.0f}"
    out.append(f"  All-time saved   {saved:>13,} tokens  (~${usd:,.2f})")
    out.append(f"  This week        {a['week_saved']:>13,} tokens  "
               f"(~${week_usd:,.2f})")
    out.append(f"  Runway bought    {('~' + runway_str):>13} prompts before "
               f"the rate window")
    out.append("")
    out.append(f"  Searches avoided {a['hits']:>13,}  "
               f"(prompts that opened the right file with no Glob/Grep)")
    if a.get("slices", 0):
        out.append(f"  Big reads sliced {a['slices']:>13,}  "
                   f"(whole-file reads turned into a structural outline)")
    out.append(f"  Sessions         {a['sessions']:>13,}  "
               f"over {a['days_active']} active days")
    out.append(f"  Streak           {a['streak']:>13}  "
               f"consecutive days {'🔥' if a['streak'] >= 3 else ''}")
    if a["first_day"]:
        out.append(f"  Since            {a['first_day']:>13}")
    out.append("")

    # Two measured sources, broken out.
    if a.get("slice_saved", 0) and a.get("search_saved", 0):
        out.append("  Where it came from")
        out.append("  " + "─" * 44)
        out.append(f"  Avoided searches  {a['search_saved']:>13,} tok  "
                   f"(auto_context → straight to file)")
        out.append(f"  Sliced big reads  {a['slice_saved']:>13,} tok  "
                   f"(smart_read → outline, not whole file)")
        out.append("")

    # The Boris line: measured, not estimated.
    if a["avg_search_cost"] > 0:
        share = a["measured_share"] * 100
        out.append("  How it's measured")
        out.append("  " + "─" * 44)
        out.append(f"  A search cost   {int(a['avg_search_cost']):>13,} tokens "
                   f"on average — measured")
        out.append(f"                  from {a['explored_episodes']:,} of your own "
                   f"prompts that still explored")
        out.append(f"  {share:.0f}% of the savings above is measured this way "
                   f"(rest: conservative")
        out.append("  8k/hit fallback for sessions with nothing to measure).")
        out.append("")

    # sparkline of last 14 active days
    days = sorted(d for d in a["by_day"] if d and d != "?")
    if days:
        tail = days[-14:]
        vals = [a["by_day"][d] for d in tail]
        mx = max(vals) or 1
        spark = "".join(
            " ▁▂▃▄▅▆▇█"[min(8, int(v / mx * 8))] for v in vals
        )
        out.append(f"  Last {len(tail):>2} days     {spark}")
        out.append(f"                   {tail[0]} → {tail[-1]}")
        out.append("")

    out.append("  Shareable card (copy/paste anywhere):")
    out.append("")
    for ln in make_card(a).splitlines():
        out.append("  " + ln)
    out.append("")
    if a["measured_share"] >= 0.999:
        out.append("  Note: every token above is measured from your own "
                   "exploration cost —")
        out.append("  no estimated constants. It still under-claims (clamped "
                   "≤15k/search).")
    elif a["measured_share"] > 0:
        out.append(f"  Note: {a['measured_share']*100:.0f}% measured from your "
                   "own exploration cost; the rest")
        out.append("  uses a conservative 8k/hit fallback. Under-claims on "
                   "purpose.")
    else:
        out.append("  Note: tokens-saved uses a conservative 8k/hit estimate "
                   "(vs ~21k")
        out.append("  measured in the live A/B) until a session has searches "
                   "to measure.")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--card-only", action="store_true")
    args = ap.parse_args()

    rows = load_ledger(args.root)
    if not rows:
        print(
            "\n  context-os — your savings\n  " + "─" * 44 + "\n\n"
            "  No receipts yet. context-os logs a receipt every time Claude\n"
            "  opens a file it surfaced for you. Run a few prompts that ask\n"
            "  'where is X' and check back — the savings start accumulating\n"
            "  on the next Stop event.\n"
        )
        return 0

    a = aggregate(rows)
    if args.json:
        print(json.dumps(a, indent=2))
    elif args.card_only:
        print(make_card(a))
    else:
        print(make_report(a))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open: a broken report must never break the user's session.
        sys.exit(0)
