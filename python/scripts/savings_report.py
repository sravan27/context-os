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

    lines = [
        "╭" + "─" * W + "╮",
        center("context-os · receipts"),
        "├" + "─" * W + "┤",
        row(f"{saved:,} tokens saved"),
        row(f"~${usd:,.2f}  ·  ~{runway:.0f} prompts of runway"),
        row(f"{a['hits']:,} hits over {a['sessions']:,} sessions"),
        row(f"{a['streak']}-day streak  ·  "
            f"{a['hit_rate']*100:.0f}% hit-rate"),
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
    out.append(f"  Hits             {a['hits']:>13,}  "
               f"(files context-os surfaced that you opened)")
    out.append(f"  Hit-rate         {a['hit_rate']*100:>12.0f}%  "
               f"of suggested files were used  {_bar(a['hit_rate'])}")
    out.append(f"  Sessions         {a['sessions']:>13,}  "
               f"over {a['days_active']} active days")
    out.append(f"  Streak           {a['streak']:>13}  "
               f"consecutive days {'🔥' if a['streak'] >= 3 else ''}")
    if a["first_day"]:
        out.append(f"  Since            {a['first_day']:>13}")
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
    out.append("  Note: tokens-saved is a conservative estimate "
               "(8k/hit vs ~21k")
    out.append("  measured in the live A/B). It under-claims on purpose.")
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
