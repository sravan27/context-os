#!/usr/bin/env python3
"""
savings_test.py — correctness gate for context-os Receipts (causal, measured).

Synthesizes realistic transcripts (prompt → tool_use → tool_result, with
timestamps and result sizes) and asserts the Stop hook classifies and measures
correctly:

  1. ASSISTED: first tool action is a Read of a suggested file, no Glob/Grep
     first  → counts as a search avoided.
  2. EXPLORED: an episode that ran Glob/Grep  → NOT assisted; its exploration
     cost is measured from real tool_result sizes.
  3. MEASURED per-hit: when a session has an exploration baseline, the per-hit
     credit equals the measured average search cost (clamped), not a constant.
  4. ESTIMATE fallback: a session with no exploration falls back to 8k/hit and
     labels itself an estimate.
  5. soft_hits still tracks the broad suggested∩read intersection.
  6. Session isolation, milestone crossing, streak math, fail-open on
     garbage/missing transcript, empty-state report, /savings --json + card.
  7. The report surfaces the measured methodology ("A search cost N tokens").

Exits non-zero on any failed assertion (CI gate).
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TRACKER = os.path.join(REPO, "hooks", "python", "savings_tracker.py")
REPORT = os.path.join(REPO, "python", "scripts", "savings_report.py")
SMART_READ = os.path.join(REPO, "hooks", "python", "smart_read.py")

_fails = []
_base = datetime(2026, 5, 26, 12, 0, 0)
_clock = [0]


def _ts():
    _clock[0] += 1
    return (_base + timedelta(seconds=_clock[0])).isoformat()


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        _fails.append(name)


def run_tracker(payload, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, TRACKER], input=body,
                          capture_output=True, text=True, env=e)


def write_transcript(path, episodes):
    """episodes: list of (prompt_text, [(tool, file_or_pattern, result_chars)])."""
    tid = [0]
    lines = []

    def emit(obj):
        lines.append(json.dumps(obj))

    for prompt, actions in episodes:
        emit({"type": "user", "timestamp": _ts(),
              "message": {"role": "user",
                          "content": [{"type": "text", "text": prompt}]}})
        for (tool, target, rsize) in actions:
            tid[0] += 1
            tuid = f"t{tid[0]}"
            inp = {"file_path": target} if tool == "Read" else \
                {"pattern": target}
            emit({"type": "assistant", "timestamp": _ts(),
                  "message": {"role": "assistant",
                              "usage": {"input_tokens": 50, "output_tokens": 20},
                              "content": [{"type": "tool_use", "id": tuid,
                                           "name": tool, "input": inp}]}})
            emit({"type": "user", "timestamp": _ts(),
                  "message": {"role": "user",
                              "content": [{"type": "tool_result",
                                           "tool_use_id": tuid,
                                           "content": "x" * rsize}]}})
    open(path, "w").write("\n".join(lines) + "\n")


def setup_session(root, session, files, ts=1.0):
    sav = os.path.join(root, ".context-os", "savings")
    os.makedirs(sav, exist_ok=True)
    with open(os.path.join(sav, "suggestions.jsonl"), "a") as f:
        f.write(json.dumps({"ts": ts, "session": session, "n": len(files),
                            "files": files}) + "\n")


def ledger_rows(root):
    p = os.path.join(root, ".context-os", "savings", "ledger.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def total(root):
    p = os.path.join(root, ".context-os", "savings", "total.json")
    return json.loads(open(p).read()) if os.path.exists(p) else {}


def test_measured_assisted_vs_explored():
    root = tempfile.mkdtemp(prefix="cos-m1-")
    setup_session(root, "s1", ["pkg/foo.py", "pkg/bar.py"])
    tp = os.path.join(root, "t.jsonl")
    # ep1: straight to suggested foo.py (assisted, no search)
    # ep2: Glob(4000c=1000t) + Grep(8000c=2000t) + Read wrong(4000c=1000t) = 4000t
    write_transcript(tp, [
        ("where is the foo handler",
         [("Read", os.path.join(root, "pkg/foo.py"), 400)]),
        ("where is the bar thing",
         [("Glob", "**/*.py", 4000), ("Grep", "bar", 8000),
          ("Read", os.path.join(root, "pkg/wrong.py"), 4000)]),
    ])
    run_tracker({"transcript_path": tp, "session_id": "s1", "cwd": root})
    rows = ledger_rows(root)
    check("measured: one ledger row", len(rows) == 1)
    if rows:
        r = rows[0]
        check("measured: 1 assisted hit (straight-to-file)", r["hits"] == 1)
        check("measured: 1 explored episode", r["explored_episodes"] == 1)
        check("measured: exploration_tokens == 4000", r["exploration_tokens"] == 4000)
        check("measured: avg_search_cost == 4000", r["avg_search_cost"] == 4000)
        check("measured: method == measured", r["method"] == "measured")
        check("measured: per_hit == measured avg (4000)", r["per_hit"] == 4000)
        check("measured: tokens_saved == 1*4000", r["tokens_saved"] == 4000)


def test_glob_before_read_not_assisted():
    root = tempfile.mkdtemp(prefix="cos-m2-")
    setup_session(root, "s2", ["pkg/baz.py"])
    tp = os.path.join(root, "t.jsonl")
    # Grep first, THEN read the suggested file → explored, not assisted.
    write_transcript(tp, [
        ("where is baz",
         [("Grep", "baz", 8000), ("Read", os.path.join(root, "pkg/baz.py"), 400)]),
    ])
    run_tracker({"transcript_path": tp, "session_id": "s2", "cwd": root})
    rows = ledger_rows(root)
    check("not-assisted: ledger row exists", len(rows) == 1)
    if rows:
        check("not-assisted: 0 assisted hits (searched first)", rows[0]["hits"] == 0)
        check("not-assisted: soft_hit still records the read", rows[0]["soft_hits"] == 1)
        check("not-assisted: explored == 1", rows[0]["explored_episodes"] == 1)


def test_estimate_fallback_when_no_exploration():
    root = tempfile.mkdtemp(prefix="cos-m3-")
    setup_session(root, "s3", ["a/b.py"])
    tp = os.path.join(root, "t.jsonl")
    # only a straight-to-file open; nothing explored to calibrate against
    write_transcript(tp, [
        ("where is b", [("Read", os.path.join(root, "a/b.py"), 300)]),
    ])
    run_tracker({"transcript_path": tp, "session_id": "s3", "cwd": root})
    rows = ledger_rows(root)
    if rows:
        check("estimate: method == estimate (no baseline)", rows[0]["method"] == "estimate")
        check("estimate: per_hit == 8000 default", rows[0]["per_hit"] == 8000)
        check("estimate: 1 assisted hit", rows[0]["hits"] == 1)


def test_long_uuid_session_id():
    """Regression: auto_context logs session_id[:12]; the tracker must match
    on [:12], not the full UUID, or every suggestion is silently dropped
    (0 assisted hits — the live dogfood bug)."""
    root = tempfile.mkdtemp(prefix="cos-uuid-")
    full = "f5e1e4be-7a73-41c9-a287-a0ef97d13745"   # 36-char UUID
    sav = os.path.join(root, ".context-os", "savings")
    os.makedirs(sav, exist_ok=True)
    # auto_context writes the TRUNCATED id, as the real hook does
    with open(os.path.join(sav, "suggestions.jsonl"), "a") as f:
        f.write(json.dumps({"ts": 1.0, "session": full[:12],
                            "files": ["pkg/a.py"]}) + "\n")
    tp = os.path.join(root, "t.jsonl")
    write_transcript(tp, [
        ("where is a", [("Read", os.path.join(root, "pkg/a.py"), 300)]),
    ])
    # tracker receives the FULL session id from Claude Code
    run_tracker({"transcript_path": tp, "session_id": full, "cwd": root})
    rows = ledger_rows(root)
    check("uuid-session: suggestion matched despite 36-char id", bool(rows))
    if rows:
        check("uuid-session: assisted hit credited (was 0 in the live bug)",
              rows[0]["hits"] == 1)


def test_session_isolation():
    root = tempfile.mkdtemp(prefix="cos-m4-")
    setup_session(root, "sA", ["x/a.py"])
    setup_session(root, "OTHER", ["y/should_not_count.py"])
    tp = os.path.join(root, "t.jsonl")
    write_transcript(tp, [
        ("where is a", [("Read", os.path.join(root, "x/a.py"), 300)]),
    ])
    run_tracker({"transcript_path": tp, "session_id": "sA", "cwd": root})
    rows = ledger_rows(root)
    if rows:
        check("isolation: only sA suggestions counted",
              rows[0]["suggested_files"] == 1)


def test_no_suggestions_no_op():
    root = tempfile.mkdtemp(prefix="cos-m5-")
    os.makedirs(os.path.join(root, ".context-os", "savings"))
    tp = os.path.join(root, "t.jsonl")
    write_transcript(tp, [("hi", [("Read", "/x/y.py", 100)])])
    run_tracker({"transcript_path": tp, "session_id": "none", "cwd": root})
    check("no-suggestions: writes no ledger", ledger_rows(root) == [])


def test_milestone_and_streak():
    root = tempfile.mkdtemp(prefix="cos-m6-")
    sav = os.path.join(root, ".context-os", "savings")
    os.makedirs(sav)
    import time
    today = time.strftime("%Y-%m-%d")
    from datetime import date
    y = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    json.dump({"tokens_saved": 996000, "hits": 100, "sessions": 9,
               "first_date": "2026-01-01", "last_date": y, "streak": 4,
               "milestone": 500000}, open(os.path.join(sav, "total.json"), "w"))
    setup_session(root, "s6", ["a/b.py"])
    tp = os.path.join(root, "t.jsonl")
    # 1 assisted hit, estimate path = 8000 → 996000+8000 = 1,004,000 crosses 1M
    write_transcript(tp, [("where is b", [("Read", os.path.join(root, "a/b.py"), 300)])])
    r = run_tracker({"transcript_path": tp, "session_id": "s6", "cwd": root})
    check("milestone: crossing 1M announced",
          "MILESTONE" in r.stderr and "1,000,000" in r.stderr)
    t = total(root)
    check("streak: yesterday->today increments to 5", t.get("streak") == 5)
    check("milestone: recorded in total", t.get("milestone") == 1000000)


def test_fail_open():
    bad = run_tracker("{{{ not json")
    check("fail-open: garbage stdin exits 0", bad.returncode == 0)
    root = tempfile.mkdtemp(prefix="cos-m7-")
    setup_session(root, "s7", ["x.py"])
    r = run_tracker({"transcript_path": "/no/such.jsonl", "session_id": "s7",
                     "cwd": root})
    check("fail-open: missing transcript exits 0", r.returncode == 0)
    check("fail-open: missing transcript writes no ledger", ledger_rows(root) == [])


def test_report_surfaces_measurement():
    root = tempfile.mkdtemp(prefix="cos-m8-")
    empty = subprocess.run([sys.executable, REPORT, "--root", root],
                           capture_output=True, text=True)
    check("report: empty exits 0", empty.returncode == 0)
    check("report: empty mentions no receipts", "No receipts" in empty.stdout)
    # measured session
    setup_session(root, "s8", ["a/b.py"])
    tp = os.path.join(root, "t.jsonl")
    write_transcript(tp, [
        ("where is b", [("Read", os.path.join(root, "a/b.py"), 300)]),
        ("where is c", [("Grep", "c", 8000), ("Read", os.path.join(root, "a/c.py"), 4000)]),
    ])
    run_tracker({"transcript_path": tp, "session_id": "s8", "cwd": root})
    rep = subprocess.run([sys.executable, REPORT, "--root", root],
                         capture_output=True, text=True)
    check("report: shows measured methodology",
          "A search cost" in rep.stdout and "measured" in rep.stdout)
    js = subprocess.run([sys.executable, REPORT, "--root", root, "--json"],
                        capture_output=True, text=True)
    data = json.loads(js.stdout)
    check("report: json avg_search_cost > 0", data.get("avg_search_cost", 0) > 0)
    check("report: json measured_share == 1.0", abs(data.get("measured_share", 0) - 1.0) < 1e-9)
    card = subprocess.run([sys.executable, REPORT, "--root", root, "--card-only"],
                          capture_output=True, text=True)
    check("report: card renders box", "context-os" in card.stdout and "receipts" in card.stdout)


def _mk_graph(root, rel, n_lines, n_syms):
    """Write a minimal repo-graph with one big file of n_syms top-level syms."""
    cos = os.path.join(root, ".context-os")
    os.makedirs(cos, exist_ok=True)
    step = max(2, n_lines // max(1, n_syms))
    syms = []
    for i in range(n_syms):
        start = 1 + i * step
        syms.append({"name": f"fn_{i}", "kind": "fn", "line": start,
                     "end": min(n_lines, start + step - 1),
                     "sig": f"def fn_{i}(a, b)"})
    graph = {"version": 2, "files": {rel: {"lang": "python", "lines": n_lines,
             "symbols": syms, "imports": []}}, "symbol_index": {},
             "imported_by": {}, "path_df": {}}
    json.dump(graph, open(os.path.join(cos, "repo-graph.json"), "w"))


def run_smart_read(payload, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, SMART_READ],
                          input=json.dumps(payload), capture_output=True,
                          text=True, env=e)


def test_smart_read_offers_outline():
    root = tempfile.mkdtemp(prefix="cos-sr1-")
    rel = "pkg/big.py"
    fp = os.path.join(root, rel)
    os.makedirs(os.path.dirname(fp))
    open(fp, "w").write("\n".join(f"line {i}" for i in range(900)))
    _mk_graph(root, rel, 900, 12)
    import shutil
    state = os.path.expanduser("~/.context-os/state/smartread-srsess1.json")
    if os.path.exists(state):
        os.remove(state)
    r = run_smart_read({"tool_name": "Read", "tool_input": {"file_path": fp},
                        "cwd": root, "session_id": "srsess1"})
    check("smart_read: blocks whole read of big file (exit 2)", r.returncode == 2)
    check("smart_read: outline shows line ranges", "L1-" in r.stderr and "fn_0" in r.stderr)
    check("smart_read: suggests a sliced Read", "offset=" in r.stderr)
    # logged a slice event
    sl = os.path.join(root, ".context-os", "savings", "slices.jsonl")
    rows = [json.loads(l) for l in open(sl)] if os.path.exists(sl) else []
    check("smart_read: logged a slice event", len(rows) == 1 and rows[0]["saved"] > 0)
    # second read of same file is allowed (no loop/nag)
    r2 = run_smart_read({"tool_name": "Read", "tool_input": {"file_path": fp},
                         "cwd": root, "session_id": "srsess1"})
    check("smart_read: same file allowed second time (exit 0)", r2.returncode == 0)
    if os.path.exists(state):
        os.remove(state)


def test_smart_read_passthrough():
    root = tempfile.mkdtemp(prefix="cos-sr2-")
    rel = "pkg/big.py"
    fp = os.path.join(root, rel)
    os.makedirs(os.path.dirname(fp))
    open(fp, "w").write("\n".join(f"line {i}" for i in range(900)))
    _mk_graph(root, rel, 900, 12)
    # sliced read → never intercepted
    r = run_smart_read({"tool_name": "Read",
                        "tool_input": {"file_path": fp, "offset": 10, "limit": 20},
                        "cwd": root, "session_id": "srsess2"})
    check("smart_read: sliced read passes through (exit 0)", r.returncode == 0)
    # small file → not intercepted
    small = os.path.join(root, "small.py")
    open(small, "w").write("\n".join(str(i) for i in range(50)))
    _mk_graph(root, "small.py", 50, 5)
    r2 = run_smart_read({"tool_name": "Read", "tool_input": {"file_path": small},
                         "cwd": root, "session_id": "srsess3"})
    check("smart_read: small file passes through (exit 0)", r2.returncode == 0)
    # disabled
    r3 = run_smart_read({"tool_name": "Read", "tool_input": {"file_path": fp},
                         "cwd": root, "session_id": "srsess4"},
                        env={"CONTEXT_OS_SMART_READ": "0"})
    check("smart_read: CONTEXT_OS_SMART_READ=0 disables (exit 0)", r3.returncode == 0)


def test_basename_collision_not_overcounted():
    """Hardening: reading a file whose basename matches a suggested file but
    lives in a DIFFERENT directory must NOT be credited as a hit. The old
    bare-basename fallback over-counted on common names (mod.rs, __init__.py,
    index.ts) that collide across dirs."""
    root = tempfile.mkdtemp(prefix="cos-bc-")
    setup_session(root, "bc", ["pkg/a/foo.py"])
    tp = os.path.join(root, "t.jsonl")
    write_transcript(tp, [
        ("where is foo", [("Read", os.path.join(root, "other/dir/foo.py"), 200)]),
    ])
    run_tracker({"transcript_path": tp, "session_id": "bc", "cwd": root})
    rows = ledger_rows(root)
    check("basename-collision: unrelated foo.py NOT credited as hit", bool(rows))
    if rows:
        check("basename-collision: hits == 0 (under-claim wins over over-claim)",
              rows[0]["hits"] == 0)


def test_prune_log_caps_unbounded_growth():
    """Hardening: suggestions.jsonl / slices.jsonl must not grow forever.
    Tracker prunes to last 10k lines when file exceeds 20k."""
    root = tempfile.mkdtemp(prefix="cos-pr-")
    sav = os.path.join(root, ".context-os", "savings")
    os.makedirs(sav)
    f = os.path.join(sav, "suggestions.jsonl")
    with open(f, "w") as fh:
        for i in range(25_000):
            fh.write(json.dumps({"ts": float(i), "session": "pr",
                                 "files": ["a.py"]}) + "\n")
    tp = os.path.join(root, "t.jsonl")
    write_transcript(tp, [("hi", [("Read", os.path.join(root, "a.py"), 100)])])
    run_tracker({"transcript_path": tp, "session_id": "pr", "cwd": root})
    n_after = sum(1 for _ in open(f))
    check("prune: 25k-line suggestions.jsonl capped at 10k (keep)", n_after == 10_000)


def test_occupancy_compounding():
    """smart_read's compounding win: a sliced file read early persists across
    the turns that follow → budget_freed = saved × remaining turns (capped)."""
    root = tempfile.mkdtemp(prefix="cos-occ-")
    sav = os.path.join(root, ".context-os", "savings")
    os.makedirs(sav)
    with open(os.path.join(sav, "slices.jsonl"), "w") as f:
        f.write(json.dumps({"ts": 1, "session": "occ", "file": "big.py",
                            "full_tokens": 20000, "outline_tokens": 1000,
                            "saved": 19000}) + "\n")
    # transcript: read big.py at turn 1, then 5 more assistant turns
    tp = os.path.join(root, "t.jsonl")
    eps = [("read big", [("Read", os.path.join(root, "big.py"), 20000)])]
    for i in range(5):
        eps.append((f"step {i}", [("Edit", os.path.join(root, "big.py"), 50)]))
    write_transcript(tp, eps)
    run_tracker({"transcript_path": tp, "session_id": "occ", "cwd": root})
    rows = ledger_rows(root)
    check("occupancy: ledger row written", bool(rows))
    if rows:
        bf = rows[0].get("budget_freed", 0)
        # read at turn 1, ~6 total turns → remaining ~5 → 19000*5 = 95000 (capped 60)
        check("occupancy: budget_freed > first-load saving", bf > 19000)
        check("occupancy: scales with remaining turns (≈saved×remaining)",
              50000 <= bf <= 120000)


def test_slices_feed_receipts():
    root = tempfile.mkdtemp(prefix="cos-sr3-")
    sav = os.path.join(root, ".context-os", "savings")
    os.makedirs(sav)
    # only slices this session, no auto_context suggestions
    with open(os.path.join(sav, "slices.jsonl"), "w") as f:
        f.write(json.dumps({"ts": 1, "session": "slsess", "file": "a.py",
                            "full_tokens": 20000, "outline_tokens": 1000,
                            "saved": 19000}) + "\n")
    tp = os.path.join(root, "t.jsonl")
    write_transcript(tp, [("read a", [("Read", os.path.join(root, "a.py"), 300)])])
    r = run_tracker({"transcript_path": tp, "session_id": "slsess", "cwd": root})
    rows = ledger_rows(root)
    check("slices→receipts: ledger row written from slices alone", len(rows) == 1)
    if rows:
        check("slices→receipts: slice_saved credited", rows[0]["tokens_saved"] == 19000)
        check("slices→receipts: slices counted", rows[0]["slices"] == 1)
    check("slices→receipts: receipt mentions outline", "outline" in r.stderr)


def main():
    print("[savings_test] context-os Receipts — causal/measured correctness\n")
    test_measured_assisted_vs_explored()
    test_glob_before_read_not_assisted()
    test_estimate_fallback_when_no_exploration()
    test_long_uuid_session_id()
    test_session_isolation()
    test_no_suggestions_no_op()
    test_milestone_and_streak()
    test_fail_open()
    test_report_surfaces_measurement()
    test_smart_read_offers_outline()
    test_smart_read_passthrough()
    test_basename_collision_not_overcounted()
    test_prune_log_caps_unbounded_growth()
    test_occupancy_compounding()
    test_slices_feed_receipts()
    print()
    if _fails:
        print(f"[savings_test] {len(_fails)} FAILED: {', '.join(_fails)}")
        return 1
    print("[savings_test] all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
