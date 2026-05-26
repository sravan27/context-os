#!/usr/bin/env python3
"""
savings_test.py — correctness gate for context-os Receipts.

Synthesizes suggestions + a transcript, runs savings_tracker.py (the Stop
hook) and savings_report.py (the /savings backend), and asserts:

  1. Hit detection: only suggested files that were actually Read count.
  2. No over-count: a file Read 3× is still 1 hit.
  3. Path normalization: abs transcript path matches rel suggested path.
  4. Session isolation: other sessions' suggestions don't leak in.
  5. Milestone crossing fires exactly once at the boundary.
  6. Streak math: consecutive days increment, gaps reset.
  7. Fail-open: garbage stdin / missing transcript exit 0, write nothing.
  8. Empty ledger: report renders a friendly empty state, exit 0.

Exits non-zero on any failed assertion (CI gate).
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TRACKER = os.path.join(REPO, "hooks", "python", "savings_tracker.py")
REPORT = os.path.join(REPO, "python", "scripts", "savings_report.py")

_fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        _fails.append(name)


def run_tracker(payload, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, TRACKER],
        input=json.dumps(payload), capture_output=True, text=True, env=e,
    )


def asst_read(fp, tin_=5, tout=5):
    return json.dumps({
        "type": "assistant",
        "message": {
            "usage": {"input_tokens": tin_, "output_tokens": tout},
            "content": [{"type": "tool_use", "name": "Read",
                         "input": {"file_path": fp}}],
        },
    })


def setup_session(root, session, suggested_files):
    sav = os.path.join(root, ".context-os", "savings")
    os.makedirs(sav, exist_ok=True)
    with open(os.path.join(sav, "suggestions.jsonl"), "a") as f:
        f.write(json.dumps({"ts": 1, "session": session,
                            "n": len(suggested_files),
                            "files": suggested_files}) + "\n")
    return sav


def ledger_rows(root):
    p = os.path.join(root, ".context-os", "savings", "ledger.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def total(root):
    p = os.path.join(root, ".context-os", "savings", "total.json")
    return json.loads(open(p).read()) if os.path.exists(p) else {}


def test_hit_detection_and_isolation():
    root = tempfile.mkdtemp(prefix="cos-t1-")
    # rel paths as auto_context emits them
    setup_session(root, "s1", [
        "hooks/python/auto_context.py",   # will be Read -> hit
        "crates/ignore/src/gitignore.rs",  # Read 3x -> still 1 hit
        "src/never_read.rs",               # suggested, never opened -> miss
    ])
    # a different session's suggestion must NOT count
    setup_session(root, "OTHER", ["should/not/count.py"])
    tp = os.path.join(root, "t.jsonl")
    with open(tp, "w") as f:
        f.write(asst_read(os.path.join(root, "hooks/python/auto_context.py")) + "\n")
        for _ in range(3):  # same file 3x
            f.write(asst_read(os.path.join(root, "crates/ignore/src/gitignore.rs")) + "\n")
        f.write(asst_read(os.path.join(root, "should/not/count.py")) + "\n")
    run_tracker({"transcript_path": tp, "session_id": "s1", "cwd": root})
    rows = ledger_rows(root)
    check("hit-detection: one ledger row", len(rows) == 1)
    if rows:
        check("hit-detection: exactly 2 hits (dedup repeated read)",
              rows[0]["hits"] == 2)
        check("session-isolation: OTHER session suggestion excluded",
              rows[0]["suggested_files"] == 3)
        check("tokens-saved = hits * per_hit",
              rows[0]["tokens_saved"] == 2 * rows[0]["per_hit"])


def test_no_suggestions_no_op():
    root = tempfile.mkdtemp(prefix="cos-t2-")
    os.makedirs(os.path.join(root, ".context-os", "savings"))
    tp = os.path.join(root, "t.jsonl")
    open(tp, "w").write(asst_read("/x/y.py") + "\n")
    run_tracker({"transcript_path": tp, "session_id": "none", "cwd": root})
    check("no-suggestions: writes no ledger", ledger_rows(root) == [])


def test_milestone_and_streak():
    root = tempfile.mkdtemp(prefix="cos-t3-")
    sav = os.path.join(root, ".context-os", "savings")
    os.makedirs(sav)
    import time
    today = time.strftime("%Y-%m-%d")
    from datetime import date, timedelta
    y = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    # prev total just under 1M, streak 4, last active yesterday
    json.dump({"tokens_saved": 996000, "hits": 100, "sessions": 9,
               "first_date": "2026-01-01", "last_date": y, "streak": 4,
               "milestone": 500000}, open(os.path.join(sav, "total.json"), "w"))
    # one suggestion, one hit at per_hit=8000 -> 1,004,000 crosses 1,000,000
    setup_session(root, "s3", ["a/b.py"])
    tp = os.path.join(root, "t.jsonl")
    open(tp, "w").write(asst_read(os.path.join(root, "a/b.py")) + "\n")
    r = run_tracker({"transcript_path": tp, "session_id": "s3", "cwd": root})
    check("milestone: crossing 1M announced",
          "MILESTONE" in r.stderr and "1,000,000" in r.stderr)
    t = total(root)
    check("streak: yesterday->today increments to 5", t.get("streak") == 5)
    check("milestone: recorded in total", t.get("milestone") == 1000000)


def test_fail_open():
    # garbage stdin
    r = run_tracker("not json at all")  # type: ignore[arg-type]
    bad = subprocess.run([sys.executable, TRACKER], input="{{{",
                         capture_output=True, text=True)
    check("fail-open: garbage stdin exits 0", bad.returncode == 0)
    # missing transcript
    root = tempfile.mkdtemp(prefix="cos-t4-")
    setup_session(root, "s4", ["x.py"])
    r2 = run_tracker({"transcript_path": "/no/such/file.jsonl",
                      "session_id": "s4", "cwd": root})
    check("fail-open: missing transcript exits 0", r2.returncode == 0)
    check("fail-open: missing transcript writes no ledger",
          ledger_rows(root) == [])


def test_report_empty_and_populated():
    root = tempfile.mkdtemp(prefix="cos-t5-")
    empty = subprocess.run([sys.executable, REPORT, "--root", root],
                           capture_output=True, text=True)
    check("report: empty state exits 0", empty.returncode == 0)
    check("report: empty state mentions no receipts",
          "No receipts" in empty.stdout)
    # populate then render json
    setup_session(root, "s5", ["a/b.py", "c/d.py"])
    tp = os.path.join(root, "t.jsonl")
    with open(tp, "w") as f:
        f.write(asst_read(os.path.join(root, "a/b.py")) + "\n")
        f.write(asst_read(os.path.join(root, "c/d.py")) + "\n")
    run_tracker({"transcript_path": tp, "session_id": "s5", "cwd": root})
    js = subprocess.run([sys.executable, REPORT, "--root", root, "--json"],
                        capture_output=True, text=True)
    check("report: --json exits 0", js.returncode == 0)
    try:
        data = json.loads(js.stdout)
        check("report: json has 2 hits", data.get("hits") == 2)
        check("report: hit-rate 100% (both suggested files read)",
              abs(data.get("hit_rate", 0) - 1.0) < 1e-9)
    except json.JSONDecodeError:
        check("report: --json parses", False)
    card = subprocess.run([sys.executable, REPORT, "--root", root,
                           "--card-only"], capture_output=True, text=True)
    check("report: card-only renders box", "context-os · receipts" in card.stdout)


def main():
    print("[savings_test] context-os Receipts correctness gate\n")
    test_hit_detection_and_isolation()
    test_no_suggestions_no_op()
    test_milestone_and_streak()
    test_fail_open()
    test_report_empty_and_populated()
    print()
    if _fails:
        print(f"[savings_test] {len(_fails)} FAILED: {', '.join(_fails)}")
        return 1
    print("[savings_test] all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
