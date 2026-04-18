#!/usr/bin/env python3
"""
session_profile.py — Stop hook that analyzes the session transcript and writes
a per-session token-usage profile. Output goes to .context-os/session-reports/.

Problem: Users don't know where their tokens went. Claude Code shows a running
count but no attribution. A 200K-token session could be 80% productive or 20%
productive and it's invisible. Boris's team has internal telemetry; external
users don't.

Solution: After each session, parse the transcript JSONL, attribute tokens to
tool calls, detect waste patterns (duplicate reads, edit loops, oversized
context), and write a markdown report. No phone-home — local only.

The report surfaces:
  - Total tokens by type (input, output, cache_read, cache_creation)
  - Top 10 token-burning turns
  - Duplicate tool calls (that dedup_guard would have caught)
  - Files edited >3 times (loop_guard territory)
  - Oversized tool results (>5K tokens — candidates for ignore/compression)

Zero dependencies. Runs in <1s even on 500-turn sessions.
"""
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


REPORTS_DIR_NAME = ".context-os/session-reports"
LARGE_RESULT_TOKEN_THRESHOLD = 5000
# Conservative 4-chars-per-token approximation for tool outputs when usage missing.
CHARS_PER_TOKEN = 4


def approx_tokens(s: str) -> int:
    return max(1, len(s) // CHARS_PER_TOKEN)


def parse_transcript(path: Path) -> dict:
    """Parse a Claude Code transcript.jsonl. Returns aggregated stats."""
    stats = {
        "turns": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "tool_calls": Counter(),
        "tool_arg_hashes": defaultdict(list),  # (tool, hash) -> [turn_idx]
        "file_edits": Counter(),
        "big_results": [],  # [(turn, tool, tokens, preview)]
        "top_turns": [],    # [(turn, total_tokens, summary)]
    }

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return stats

    for i, line in enumerate(lines):
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg = evt.get("message") or {}
        usage = msg.get("usage") or evt.get("usage") or {}
        if usage:
            stats["turns"] += 1
            stats["input_tokens"] += usage.get("input_tokens", 0) or 0
            stats["output_tokens"] += usage.get("output_tokens", 0) or 0
            stats["cache_read_tokens"] += usage.get("cache_read_input_tokens", 0) or 0
            stats["cache_creation_tokens"] += usage.get("cache_creation_input_tokens", 0) or 0
            turn_total = (
                (usage.get("input_tokens", 0) or 0)
                + (usage.get("output_tokens", 0) or 0)
            )
            if turn_total > 0:
                stats["top_turns"].append((i, turn_total, _summarize_turn(msg)))

        # Detect tool calls — shape: content array with type=tool_use
        content = msg.get("content") or []
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    tool = block.get("name", "?")
                    stats["tool_calls"][tool] += 1
                    inp = block.get("input") or {}
                    # Track duplicate-args for Read/Grep/Glob
                    if tool in ("Read", "Glob", "Grep"):
                        h = _arg_signature(tool, inp)
                        stats["tool_arg_hashes"][(tool, h)].append(i)
                    # Track file-edit counts
                    if tool in ("Edit", "Write", "NotebookEdit"):
                        fp = inp.get("file_path") or inp.get("notebook_path") or ""
                        if fp:
                            stats["file_edits"][fp] += 1
                elif block.get("type") == "tool_result":
                    result_content = block.get("content")
                    text = (
                        result_content
                        if isinstance(result_content, str)
                        else json.dumps(result_content)[:20000]
                    )
                    toks = approx_tokens(text)
                    if toks >= LARGE_RESULT_TOKEN_THRESHOLD:
                        stats["big_results"].append(
                            (i, toks, (text or "")[:120].replace("\n", " "))
                        )

    return stats


def _arg_signature(tool: str, inp: dict) -> str:
    if tool == "Read":
        return inp.get("file_path", "")
    if tool == "Glob":
        return f"{inp.get('pattern', '')}|{inp.get('path', '')}"
    if tool == "Grep":
        return "|".join(
            str(inp.get(k, ""))
            for k in ("pattern", "path", "glob", "type", "output_mode")
        )
    return json.dumps(inp, sort_keys=True)[:200]


def _summarize_turn(msg: dict) -> str:
    content = msg.get("content") or []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    return (b.get("text") or "")[:80].replace("\n", " ")
                if b.get("type") == "tool_use":
                    return f"tool:{b.get('name', '?')}"
    if isinstance(content, str):
        return content[:80].replace("\n", " ")
    return ""


def format_report(stats: dict, session_id: str) -> str:
    total = (
        stats["input_tokens"]
        + stats["output_tokens"]
        + stats["cache_creation_tokens"]
    )
    cache_ratio = (
        stats["cache_read_tokens"]
        / max(1, stats["input_tokens"] + stats["cache_read_tokens"])
    )

    lines = [
        f"# Session profile — {session_id}",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Totals",
        "",
        f"- Turns: {stats['turns']}",
        f"- Input tokens (uncached): {stats['input_tokens']:,}",
        f"- Output tokens: {stats['output_tokens']:,}",
        f"- Cache read tokens: {stats['cache_read_tokens']:,}",
        f"- Cache write tokens: {stats['cache_creation_tokens']:,}",
        f"- **Total billable: {total:,}**",
        f"- Cache hit ratio: {cache_ratio:.1%}",
        "",
        "## Tool call breakdown",
        "",
    ]
    if stats["tool_calls"]:
        for tool, n in stats["tool_calls"].most_common():
            lines.append(f"- {tool}: {n}")
    else:
        lines.append("- (no tool calls)")
    lines.append("")

    # Duplicate tool calls — dedup_guard would've caught these.
    dupes = [
        (tool, sig, turns)
        for (tool, sig), turns in stats["tool_arg_hashes"].items()
        if len(turns) > 1
    ]
    lines += ["## Duplicate Read/Glob/Grep (dedup_guard saves these)", ""]
    if dupes:
        dupes.sort(key=lambda x: -len(x[2]))
        for tool, sig, turns in dupes[:10]:
            lines.append(f"- `{tool}` × {len(turns)}: `{sig[:80]}`")
    else:
        lines.append("- (none detected)")
    lines.append("")

    # Files edited many times — loop_guard territory.
    loops = [(fp, n) for fp, n in stats["file_edits"].most_common() if n >= 3]
    lines += ["## Files edited 3+ times (loop_guard territory)", ""]
    if loops:
        for fp, n in loops[:10]:
            lines.append(f"- {fp}: {n} edits")
    else:
        lines.append("- (none)")
    lines.append("")

    # Oversized tool results — ignore-pattern candidates.
    lines += ["## Oversized tool results (>5K tokens each)", ""]
    if stats["big_results"]:
        for turn, toks, preview in sorted(
            stats["big_results"], key=lambda x: -x[1]
        )[:10]:
            lines.append(f"- turn {turn}: ~{toks:,} tok — `{preview}`")
    else:
        lines.append("- (none)")
    lines.append("")

    # Top turns by total tokens.
    lines += ["## Top 10 turns by token cost", ""]
    for turn, toks, summary in sorted(
        stats["top_turns"], key=lambda x: -x[1]
    )[:10]:
        lines.append(f"- turn {turn}: {toks:,} tok — {summary or '(empty)'}")
    lines.append("")

    # Recommendations.
    lines += ["## Recommendations", ""]
    recs = []
    if dupes:
        saved = sum(len(turns) - 1 for _, _, turns in dupes)
        recs.append(
            f"- Enable `dedup_guard` hook: would have skipped ~{saved} duplicate tool calls."
        )
    if loops:
        recs.append(
            "- Enable `loop_guard` hook: catches edit loops before they burn tokens."
        )
    if stats["big_results"]:
        recs.append(
            "- Add the file patterns above to `.claudeignore` if they're "
            "noise (build logs, node_modules, generated code)."
        )
    if cache_ratio < 0.3 and total > 50_000:
        recs.append(
            "- Low cache hit ratio. Enable `ENABLE_PROMPT_CACHING_1H=1` and "
            "keep CLAUDE.md/system prompt stable across sessions."
        )
    if not recs:
        recs.append("- Session looks clean. No obvious waste detected.")
    lines += recs
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    if os.environ.get("CONTEXT_OS_PROFILE") == "0":
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    transcript = payload.get("transcript_path")
    session_id = payload.get("session_id", "unknown")
    cwd = payload.get("cwd") or os.getcwd()

    if not transcript or not os.path.exists(transcript):
        return 0

    stats = parse_transcript(Path(transcript))
    if stats["turns"] == 0:
        return 0

    reports_dir = Path(cwd) / REPORTS_DIR_NAME
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = reports_dir / f"{ts}-{session_id[:8]}.md"

    try:
        out.write_text(format_report(stats, session_id))
    except OSError:
        return 0

    # Print a one-line summary so the user sees it in terminal.
    total = (
        stats["input_tokens"]
        + stats["output_tokens"]
        + stats["cache_creation_tokens"]
    )
    dupes = sum(
        1
        for v in stats["tool_arg_hashes"].values()
        if len(v) > 1
    )
    print(
        f"[context-os] Session: {total:,} tok, "
        f"{stats['turns']} turns, {dupes} duplicate tool calls. "
        f"Full report: {out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
