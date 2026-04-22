#!/usr/bin/env python3
"""
_ablation_child.py — child process for autocontext_ablation.

Reads a small JSON payload on stdin (fixture + prompts), runs
`autocontext_eval.eval_fixture` (which shells out to auto_context.py with
`CONTEXT_OS_AUTOCONTEXT_ABLATE` already in env), and writes the per-fixture
result JSON on stdout. Kept in its own file so the parent can toggle env
between runs — `subprocess.run(env=...)` doesn't touch the parent's env.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
from autocontext_eval import eval_fixture  # noqa: E402


def main():
    payload = json.load(sys.stdin)
    fx_id = payload["fixture_id"]
    fx_root = payload["fixture_root"]
    prompts = payload["prompts"]
    result = eval_fixture(fx_id, fx_root, prompts, "auto_context")
    # Keep rows so aggregate() can re-weight across fixtures. We trim
    # heavy fields to keep the stdout payload small.
    for r in result.get("rows", []):
        r.pop("prompt", None)
        r.pop("expected", None)
        r["predicted"] = r.get("predicted", [])[:5]
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
