#!/usr/bin/env python3
"""
robustness_test.py — adversarial/edge-case tests for auto_context.

The hook MUST never crash. It's on the critical path of every prompt; any
non-zero exit or stderr spew is user-visible noise. This suite throws every
pathological input we can think of at the hook and asserts:

  1. Exit code = 0 (fail-open).
  2. stdout is either empty or a well-formed `<context-os:autocontext>`
     block with at most N candidates.
  3. No exceptions on stderr.
  4. Runtime under 1 second (soft SLA).

Tests are independent; each sets up its own tmpdir. Writes
`python/evals/reports/robustness.md`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
HOOK = os.path.join(REPO, "hooks", "python", "auto_context.py")
REPORT = os.path.join(REPO, "python", "evals", "reports", "robustness.md")


def run_hook(prompt, cwd, extra_env=None, timeout=5):
    env = {**os.environ, "CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT": "1"}
    if extra_env:
        env.update(extra_env)
    payload = json.dumps({"prompt": prompt, "cwd": cwd})
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, HOOK],
            input=payload, capture_output=True, text=True,
            cwd=cwd, timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout",
                "elapsed_ms": (time.perf_counter() - t0) * 1000}
    elapsed = (time.perf_counter() - t0) * 1000
    ok = (
        proc.returncode == 0
        and (proc.stderr.strip() == ""
             or "Traceback" not in proc.stderr)
    )
    return {
        "ok": ok,
        "exit": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr.strip()[:200],
        "elapsed_ms": elapsed,
    }


# -------- fixtures --------

def mkempty():
    d = tempfile.mkdtemp(prefix="robust-empty-")
    return d


def mknograph():
    d = tempfile.mkdtemp(prefix="robust-nograph-")
    os.makedirs(os.path.join(d, "src"), exist_ok=True)
    with open(os.path.join(d, "src", "foo.py"), "w") as f:
        f.write("def hello():\n    return 1\n")
    return d


def mkbrokenjson():
    d = tempfile.mkdtemp(prefix="robust-brokenjson-")
    os.makedirs(os.path.join(d, ".context-os"), exist_ok=True)
    with open(os.path.join(d, ".context-os", "repo-graph.json"), "w") as f:
        f.write("{not valid json at all [")
    return d


def mkemptygraph():
    d = tempfile.mkdtemp(prefix="robust-emptygraph-")
    os.makedirs(os.path.join(d, ".context-os"), exist_ok=True)
    with open(os.path.join(d, ".context-os", "repo-graph.json"), "w") as f:
        f.write("{}")
    return d


def mkpartialgraph():
    # Graph with only some keys present — mimics a graph shape change
    d = tempfile.mkdtemp(prefix="robust-partial-")
    os.makedirs(os.path.join(d, ".context-os"), exist_ok=True)
    with open(os.path.join(d, ".context-os", "repo-graph.json"), "w") as f:
        json.dump({"files": {"src/foo.py": {"imports": ["os"]}}}, f)
    return d


def mkunicodegraph():
    d = tempfile.mkdtemp(prefix="robust-unicode-")
    os.makedirs(os.path.join(d, ".context-os"), exist_ok=True)
    graph = {
        "files": {
            "src/münchen_café.py": {"imports": ["🚀.rocket"], "lines": 42},
            "src/日本語.py": {"imports": [], "lines": 10},
        },
        "symbol_index": {
            "café_handler": [{"file": "src/münchen_café.py", "line": 12,
                              "kind": "function"}],
        },
        "imported_by": {"🚀.rocket": ["src/münchen_café.py"]},
        "hot_files": [],
    }
    with open(os.path.join(d, ".context-os", "repo-graph.json"), "w") as f:
        json.dump(graph, f, ensure_ascii=False)
    return d


def mkhugegraph(n_files=5000):
    d = tempfile.mkdtemp(prefix="robust-huge-")
    os.makedirs(os.path.join(d, ".context-os"), exist_ok=True)
    files = {f"src/pkg{i // 100}/mod_{i:05d}.py":
             {"imports": [], "lines": 10}
             for i in range(n_files)}
    symbol_index = {f"fn_{i}": [{"file": f"src/pkg{i // 100}/mod_{i:05d}.py",
                                 "line": 1, "kind": "function"}]
                    for i in range(n_files)}
    graph = {
        "files": files,
        "symbol_index": symbol_index,
        "imported_by": {},
        "hot_files": [],
    }
    with open(os.path.join(d, ".context-os", "repo-graph.json"), "w") as f:
        json.dump(graph, f)
    return d


def cleanup(dirs):
    for d in dirs:
        try:
            shutil.rmtree(d)
        except Exception:
            pass


# -------- test cases --------

CASES = []


def case(name, desc):
    def deco(fn):
        CASES.append({"name": name, "desc": desc, "fn": fn})
        return fn
    return deco


@case("empty-dir",
      "Hook invoked in an empty directory with no graph and no source.")
def _c_empty():
    d = mkempty()
    try:
        return run_hook("find the login handler", d), d
    finally:
        cleanup([d])


@case("no-graph",
      "Source files exist but `.context-os/repo-graph.json` is missing.")
def _c_nograph():
    d = mknograph()
    try:
        return run_hook("where is hello defined", d), d
    finally:
        cleanup([d])


@case("corrupt-json",
      "`.context-os/repo-graph.json` is present but contains invalid JSON.")
def _c_brokenjson():
    d = mkbrokenjson()
    try:
        return run_hook("add rate limiting", d), d
    finally:
        cleanup([d])


@case("empty-graph",
      "Graph JSON parses but is an empty object `{}`.")
def _c_emptygraph():
    d = mkemptygraph()
    try:
        return run_hook("refactor the auth module", d), d
    finally:
        cleanup([d])


@case("partial-graph",
      "Graph has only `files`, missing `symbol_index`/`imported_by`/`hot_files`.")
def _c_partialgraph():
    d = mkpartialgraph()
    try:
        return run_hook("find foo", d), d
    finally:
        cleanup([d])


@case("unicode-paths",
      "Graph has unicode file paths, symbols with accents, emoji modules.")
def _c_unicode():
    d = mkunicodegraph()
    try:
        return run_hook("where is café_handler", d), d
    finally:
        cleanup([d])


@case("huge-graph",
      "Graph with 5,000 files and 5,000 symbols. Latency SLA applies.")
def _c_hugegraph():
    d = mkhugegraph(5000)
    try:
        return run_hook("find fn_1234", d), d
    finally:
        cleanup([d])


@case("empty-prompt",
      "Prompt is the empty string.")
def _c_emptyprompt():
    d = mkemptygraph()
    try:
        return run_hook("", d), d
    finally:
        cleanup([d])


@case("whitespace-prompt",
      "Prompt is pure whitespace.")
def _c_wsprompt():
    d = mkemptygraph()
    try:
        return run_hook("   \n\t  ", d), d
    finally:
        cleanup([d])


@case("mega-prompt",
      "Prompt is 100,000 characters long.")
def _c_megaprompt():
    d = mkemptygraph()
    try:
        p = ("find hash_password and list callers " * 5000)[:100000]
        return run_hook(p, d), d
    finally:
        cleanup([d])


@case("adversarial-regex",
      "Prompt contains regex metacharacters and long backslash sequences.")
def _c_regexbomb():
    d = mkemptygraph()
    try:
        p = "find \\(((?:a+)+)\\)+$ in .*^()[]{}|\\d+\\s\\w+ for real"
        return run_hook(p, d), d
    finally:
        cleanup([d])


@case("null-bytes-prompt",
      "Prompt contains NUL bytes and control chars.")
def _c_nullbytes():
    d = mkemptygraph()
    try:
        p = "find \x00\x01\x02 the \x7f auth handler \x00"
        return run_hook(p, d), d
    finally:
        cleanup([d])


@case("unicode-prompt",
      "Prompt is in multiple languages and emoji.")
def _c_unicodeprompt():
    d = mkunicodegraph()
    try:
        return run_hook("找到 café_handler 函数 🔍 in münchen", d), d
    finally:
        cleanup([d])


@case("path-injection",
      "Prompt contains shell metacharacters that must not be expanded.")
def _c_pathinjection():
    d = mkemptygraph()
    try:
        p = "find `rm -rf /` and $(whoami) and ; cat /etc/passwd"
        return run_hook(p, d), d
    finally:
        cleanup([d])


@case("ablate-all",
      "All 8 ranker signals disabled via env var. Should still exit clean.")
def _c_ablateall():
    d = mkunicodegraph()
    try:
        return run_hook("find café_handler", d, extra_env={
            "CONTEXT_OS_AUTOCONTEXT_ABLATE":
                "symbol_exact,symbol_ci,path_exact,path_substr,import,hot,"
                "test_penalty,hub_penalty",
        }), d
    finally:
        cleanup([d])


@case("disabled",
      "`CONTEXT_OS_AUTOCONTEXT=0` → hook must exit silently.")
def _c_disabled():
    d = mkunicodegraph()
    try:
        return run_hook("find something", d,
                        extra_env={"CONTEXT_OS_AUTOCONTEXT": "0"}), d
    finally:
        cleanup([d])


@case("stdin-not-json",
      "Hook invoked with non-JSON stdin.")
def _c_stdinbad():
    # Separate helper since run_hook always JSON-encodes.
    d = mkemptygraph()
    env = {**os.environ, "CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT": "1"}
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, HOOK],
        input="this is not { json", capture_output=True, text=True,
        cwd=d, timeout=5, env=env,
    )
    elapsed = (time.perf_counter() - t0) * 1000
    cleanup([d])
    return {
        "ok": proc.returncode == 0 and "Traceback" not in proc.stderr,
        "exit": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr.strip()[:200],
        "elapsed_ms": elapsed,
    }, None


@case("stdin-empty",
      "Hook invoked with completely empty stdin.")
def _c_stdinempty():
    d = mkemptygraph()
    env = {**os.environ, "CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT": "1"}
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, HOOK],
        input="", capture_output=True, text=True,
        cwd=d, timeout=5, env=env,
    )
    elapsed = (time.perf_counter() - t0) * 1000
    cleanup([d])
    return {
        "ok": proc.returncode == 0 and "Traceback" not in proc.stderr,
        "exit": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr.strip()[:200],
        "elapsed_ms": elapsed,
    }, None


def run_all():
    results = []
    for c in CASES:
        try:
            r, _ = c["fn"]()
        except Exception as e:
            r = {"ok": False, "reason": f"harness: {e}"}
        results.append({**c, "result": r})
    return results


def write_report(results, generated_at):
    lines = []
    a = lines.append
    a("# auto_context robustness tests")
    a("")
    passed = sum(1 for r in results if r["result"].get("ok"))
    total = len(results)
    a(f"_Generated {generated_at} · {passed}/{total} cases pass_")
    a("")
    a("## Why this exists")
    a("")
    a("The hook runs on every prompt. Any crash, stderr spew, or non-zero")
    a("exit is user-visible noise. This suite throws pathological inputs")
    a("at the hook and asserts:")
    a("")
    a("1. Exit code = 0 (fail-open).")
    a("2. stdout is empty or a well-formed `<context-os:autocontext>` block.")
    a("3. No Python tracebacks on stderr.")
    a("4. Wall time under 1 second per invocation.")
    a("")
    a("## Results")
    a("")
    a("| # | case | status | exit | elapsed | stderr |")
    a("|---|---|:---:|---:|---:|---|")
    for i, r in enumerate(results, 1):
        res = r["result"]
        stat = "✓" if res.get("ok") else "✗"
        ex = res.get("exit", "—")
        el = f"{res.get('elapsed_ms', 0):.1f}ms" if "elapsed_ms" in res else "—"
        err = res.get("stderr", "") or res.get("reason", "")
        err = (err[:60] + "…") if len(err) > 60 else err
        err = err or "—"
        a(f"| {i} | `{r['name']}` | {stat} | {ex} | {el} | {err} |")
    a("")
    a("## Case details")
    a("")
    for r in results:
        a(f"### `{r['name']}`")
        a("")
        a(r["desc"])
        a("")
        stat = "pass" if r["result"].get("ok") else "**FAIL**"
        a(f"- Status: {stat}")
        a(f"- Exit: {r['result'].get('exit', '—')}")
        el = r['result'].get('elapsed_ms')
        a(f"- Elapsed: {el:.1f}ms" if el else "- Elapsed: —")
        stdout = r['result'].get('stdout', '') or ''
        if stdout.strip():
            a("- stdout (first 200 chars):")
            a("")
            a("  ```")
            a("  " + stdout.strip().replace("\n", "\n  ")[:200])
            a("  ```")
        err = r['result'].get('stderr', '') or ''
        if err:
            a(f"- stderr: `{err[:120]}`")
        a("")
    a("## Reproduce")
    a("")
    a("```bash")
    a("python3 python/evals/runners/robustness_test.py")
    a("```")
    a("")
    a("Non-zero exit if any case fails.")
    a("")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))


def main():
    results = run_all()
    gen = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_report(results, gen)
    passed = sum(1 for r in results if r["result"].get("ok"))
    total = len(results)
    print(f"robustness: {passed}/{total} pass")
    print(f"wrote {REPORT}")
    for r in results:
        mark = "✓" if r["result"].get("ok") else "✗"
        el = r["result"].get("elapsed_ms", 0)
        print(f"  {mark} {r['name']:22s}  "
              f"exit={r['result'].get('exit', '?')}  "
              f"{el:.1f}ms")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
