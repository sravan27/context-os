#!/usr/bin/env python3
"""
live_session_bench.py — real-Claude A/B benchmark for auto_context.

Runs `claude --print --output-format json` twice per prompt:
  - control:   CONTEXT_OS_AUTOCONTEXT=0  (hook installed but disabled)
  - treatment: CONTEXT_OS_AUTOCONTEXT=1  (hook active — default)

Captures the usage JSON from each run and reports the token/cost delta.
This is the only number that matters for "does this save real Claude
tokens?" — the simulated session_replay.py is a ceiling estimate; this
is ground truth.

Cost awareness: each --print call with Sonnet costs ~$0.02 for trivial
prompts. N=6 prompts × 2 modes = 12 runs ≈ $0.25. Scale up only after
the harness is known-good.

Requires: `claude` CLI in PATH, user authenticated (claude/login).

Usage:
  python3 python/evals/runners/live_session_bench.py               # default fixture
  python3 python/evals/runners/live_session_bench.py --cwd /path   # custom target
  python3 python/evals/runners/live_session_bench.py --runs 3      # N repeats per mode
  python3 python/evals/runners/live_session_bench.py --prompts file.json
  python3 python/evals/runners/live_session_bench.py --dry-run     # print plan, no calls
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from statistics import mean, median

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
REPORT_DIR = os.path.join(REPO_ROOT, "python", "evals", "reports")
REPORT = os.path.join(REPORT_DIR, "live-session-bench.md")
RAW = os.path.join(REPORT_DIR, "live-session-bench-raw.json")

# Default prompts are realistic developer tasks on the autocontext_fixture
# — chosen so auto_context has something to latch onto (named symbols,
# domain terms) AND so the baseline would do real exploration.
DEFAULT_PROMPTS = [
    {
        "id": "p1-hash-password",
        "prompt": "Find where hash_password is defined and list the files "
                  "that call it. Don't make changes, just report findings.",
    },
    {
        "id": "p2-session-ttl",
        "prompt": "I want to make the session TTL configurable per "
                  "environment. Which files do I need to touch? Name them.",
    },
    {
        "id": "p3-rate-limit",
        "prompt": "Where is RATE_LIMIT_CONFIG used and how would I expose "
                  "it through the Settings class? Just list the files "
                  "and the rough change needed.",
    },
    {
        "id": "p4-verify-password-bug",
        "prompt": "verify_password might return True on a malformed stored "
                  "hash. Find the function, read it, and tell me if the "
                  "bug is real.",
    },
    {
        "id": "p5-migrations-add-col",
        "prompt": "I need to add a created_at column to the users table. "
                  "Where do I add a migration and update the model? List "
                  "the files.",
    },
    {
        "id": "p6-middleware-logging",
        "prompt": "auth_middleware should log the user_id when denying a "
                  "request. Which file, and what does the current code "
                  "look like?",
    },
]


def run_claude(prompt, cwd, hook_on, model, timeout_s):
    env = {**os.environ}
    env["CONTEXT_OS_AUTOCONTEXT"] = "1" if hook_on else "0"
    env["CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT"] = "1"  # fire on any non-empty
    env["CONTEXT_OS_PREWARM"] = "0"  # isolate auto_context's effect
    cmd = ["claude", "--print", "--output-format", "json", "--model", model,
           "--permission-mode", "bypassPermissions", prompt]
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True,
            text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "wall_s": timeout_s}
    wall = time.time() - t0
    if proc.returncode != 0:
        return {"error": "exit",
                "returncode": proc.returncode,
                "stderr": proc.stderr[-500:],
                "wall_s": wall}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "json",
                "stdout": proc.stdout[-500:],
                "wall_s": wall}
    u = data.get("usage", {})
    total = (
        u.get("input_tokens", 0)
        + u.get("cache_creation_input_tokens", 0)
        + u.get("cache_read_input_tokens", 0)
        + u.get("output_tokens", 0)
    )
    return {
        "wall_s": wall,
        "duration_ms": data.get("duration_ms"),
        "duration_api_ms": data.get("duration_api_ms"),
        "num_turns": data.get("num_turns"),
        "stop_reason": data.get("stop_reason"),
        "is_error": data.get("is_error"),
        "result": (data.get("result") or "")[:400],
        "total_cost_usd": data.get("total_cost_usd"),
        "input_tokens": u.get("input_tokens", 0),
        "output_tokens": u.get("output_tokens", 0),
        "cache_read_input_tokens": u.get("cache_read_input_tokens", 0),
        "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0),
        "total_tokens": total,
    }


def bench(cwd, prompts, runs, model, timeout_s, dry_run):
    rows = []
    total_cost = 0.0
    for p in prompts:
        per_prompt = {"id": p["id"], "prompt": p["prompt"],
                      "control": [], "treatment": []}
        for mode_name, hook_on in [("control", False), ("treatment", True)]:
            for r in range(runs):
                if dry_run:
                    per_prompt[mode_name].append({"dry_run": True})
                    continue
                sys.stderr.write(
                    f"  {p['id']} · {mode_name} · run {r+1}/{runs} ..."
                )
                sys.stderr.flush()
                res = run_claude(p["prompt"], cwd, hook_on, model, timeout_s)
                if "total_cost_usd" in res and res["total_cost_usd"]:
                    total_cost += res["total_cost_usd"]
                if "error" in res:
                    sys.stderr.write(" err\n")
                else:
                    sys.stderr.write(
                        f" {res['total_tokens']:,} tok\n"
                    )
                per_prompt[mode_name].append(res)
        rows.append(per_prompt)
    return rows, total_cost


def agg(rows, field, mode):
    out = []
    for r in rows:
        vals = [x[field] for x in r[mode] if field in x]
        if vals:
            out.append(mean(vals))
    return out


def write_report(rows, cwd, model, runs, total_cost, generated_at):
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(RAW, "w") as f:
        json.dump({"rows": rows, "cwd": cwd, "model": model,
                   "runs_per_mode": runs, "generated_at": generated_at},
                  f, indent=2)

    lines = [
        "# Live Claude A/B — auto_context",
        "",
        f"_Generated {generated_at} · model `{model}` · "
        f"{runs} run(s) per mode · N={len(rows)} prompts · "
        f"cwd `{os.path.relpath(cwd, REPO_ROOT) if cwd.startswith(REPO_ROOT) else cwd}` · "
        f"total cost ${total_cost:.4f}_",
        "",
        "## What this measures",
        "",
        "Real `claude --print --output-format json` calls, with and without "
        "the `auto_context` UserPromptSubmit hook active. Each prompt is "
        "run once per mode (or N times per mode with `--runs N`); same "
        "fixture, same model, same cold cache per call. Delta comes from "
        "Claude seeing the `<context-os:autocontext>` block (treatment) vs "
        "not (control) — everything else is identical.",
        "",
        "## Per-prompt totals (mean across runs)",
        "",
        "| id | control tok | treatment tok | Δ tok | Δ % | control $ | treatment $ | Δ $ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def _mean(lst):
        vals = [v for v in lst if isinstance(v, (int, float))]
        return mean(vals) if vals else 0.0

    deltas = []
    for r in rows:
        c_tok = _mean([x.get("total_tokens", 0) for x in r["control"]])
        t_tok = _mean([x.get("total_tokens", 0) for x in r["treatment"]])
        c_usd = _mean([x.get("total_cost_usd", 0) or 0 for x in r["control"]])
        t_usd = _mean([x.get("total_cost_usd", 0) or 0
                       for x in r["treatment"]])
        d_tok = c_tok - t_tok
        d_pct = (d_tok / c_tok) if c_tok else 0.0
        d_usd = c_usd - t_usd
        deltas.append((c_tok, t_tok, d_tok, d_pct, c_usd, t_usd, d_usd))
        lines.append(
            f"| {r['id']} | {c_tok:,.0f} | {t_tok:,.0f} | "
            f"**{d_tok:+,.0f}** | **{d_pct:+.1%}** | "
            f"${c_usd:.4f} | ${t_usd:.4f} | **${d_usd:+.4f}** |"
        )

    if deltas:
        tot_c = sum(d[0] for d in deltas)
        tot_t = sum(d[1] for d in deltas)
        tot_cu = sum(d[4] for d in deltas)
        tot_tu = sum(d[5] for d in deltas)
        med_pct = median([d[3] for d in deltas])
        wins = sum(1 for d in deltas if d[2] > 0)
        lines += [
            "",
            "## Aggregate",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Total control tokens | **{tot_c:,.0f}** |",
            f"| Total treatment tokens | **{tot_t:,.0f}** |",
            f"| Total savings | **{tot_c - tot_t:+,.0f} tok "
            f"({(tot_c - tot_t) / max(tot_c, 1):+.1%})** |",
            f"| Median savings per prompt | **{med_pct:+.1%}** |",
            f"| Prompts where treatment < control | **{wins}/{len(deltas)}** |",
            f"| Total control cost | ${tot_c_cost(deltas):.4f} |",
            f"| Total treatment cost | ${tot_t_cost(deltas):.4f} |",
            f"| Total cost savings | **${tot_c_cost(deltas) - tot_t_cost(deltas):+.4f}** |",
            "",
        ]

    lines += [
        "## Caveats",
        "",
        f"- N={len(rows)} prompts. Small sample — individual prompt variance "
        "is high. Use `--runs N` to average multiple Claude invocations per "
        "mode and suppress single-call noise.",
        "- Cold cache per call: Claude Code doesn't share cache between "
        "separate `--print` invocations, so each run pays full cache creation. "
        "This biases toward larger absolute numbers and smaller percentage "
        "deltas than a long interactive session would show.",
        "- `claude --permission-mode bypassPermissions` lets the model "
        "actually run Read/Glob/Grep. Without this, the control arm can't "
        "explore and the bench is meaningless.",
        "- Model and fixture held constant across arms. Only variable: "
        "`CONTEXT_OS_AUTOCONTEXT` env var (0 = hook installed but inert, "
        "1 = hook emits the block).",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python3 python/evals/runners/live_session_bench.py \\",
        f"  --cwd {os.path.relpath(cwd, REPO_ROOT) if cwd.startswith(REPO_ROOT) else cwd} \\",
        f"  --model {model} --runs {runs}",
        "```",
        "",
        "Raw per-call data: `python/evals/reports/live-session-bench-raw.json`.",
        "",
    ]
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))


def tot_c_cost(deltas):
    return sum(d[4] for d in deltas)


def tot_t_cost(deltas):
    return sum(d[5] for d in deltas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", default="/tmp/cos-livebench",
                    help="Target directory (should have context-os installed).")
    ap.add_argument("--prompts", default=None,
                    help="JSON file with prompts list (default: builtin).")
    ap.add_argument("--runs", type=int, default=1,
                    help="Repeats per mode per prompt (reduce noise).")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cwd = os.path.abspath(args.cwd)
    if not os.path.isdir(cwd):
        sys.stderr.write(f"cwd not found: {cwd}\n")
        return 2
    if not os.path.isfile(os.path.join(cwd, ".claude", "hooks",
                                       "auto_context.py")):
        sys.stderr.write(
            f"auto_context hook not installed at {cwd} — "
            "run setup.sh there first.\n"
        )
        return 2

    if args.prompts:
        with open(args.prompts) as f:
            prompts = json.load(f)
            if isinstance(prompts, dict) and "prompts" in prompts:
                prompts = prompts["prompts"]
    else:
        prompts = DEFAULT_PROMPTS

    sys.stderr.write(
        f"live bench: N={len(prompts)} · runs={args.runs} · "
        f"model={args.model} · cwd={cwd}\n"
        f"est. cost: ${len(prompts) * 2 * args.runs * 0.02:.2f}\n"
    )
    if args.dry_run:
        sys.stderr.write("DRY RUN — no claude calls.\n")

    rows, cost = bench(cwd, prompts, args.runs, args.model,
                       args.timeout, args.dry_run)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_report(rows, cwd, args.model, args.runs, cost, generated_at)

    n = len(rows)
    if rows and not args.dry_run:
        deltas = []
        for r in rows:
            c = mean([x.get("total_tokens", 0) for x in r["control"]
                      if "total_tokens" in x]) if r["control"] else 0
            t = mean([x.get("total_tokens", 0) for x in r["treatment"]
                      if "total_tokens" in x]) if r["treatment"] else 0
            deltas.append((c, t))
        tot_c = sum(d[0] for d in deltas)
        tot_t = sum(d[1] for d in deltas)
        wins = sum(1 for c, t in deltas if t < c)
        sys.stderr.write(
            f"\nlive bench · N={n} · "
            f"control={tot_c:,.0f} tok · treatment={tot_t:,.0f} tok · "
            f"Δ={(tot_c - tot_t) / max(tot_c, 1):+.1%} · "
            f"wins={wins}/{n} · cost=${cost:.4f}\n"
        )
    sys.stderr.write(
        f"report: {os.path.relpath(REPORT, REPO_ROOT)}\n"
        f"raw:    {os.path.relpath(RAW, REPO_ROOT)}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
