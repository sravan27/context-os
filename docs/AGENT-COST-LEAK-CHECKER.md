# AI Agent Cost Leak Checker

`python/agent_cost_leak_check.py` scans a local repository for coding-agent cost-leak signals:

- missing `CLAUDE.md`, `AGENTS.md`, or equivalent agent guidance
- missing `.claudeignore`, `.cursorignore`, or `.aiderignore`
- generated, build, vendor, fixture, snapshot, or lockfile noise
- large tracked blobs that can waste context when opened casually
- weak documentation, test, eval, or benchmark signals
- large or multi-language repo shape that benefits from a repo map

The scanner is intentionally conservative. It is not a token bill estimator and it does not read private file contents. It is a triage gate for teams using Claude Code, Codex, Cursor, or internal coding agents.

## Run Locally

```bash
python3 python/agent_cost_leak_check.py --repo .
python3 python/agent_cost_leak_check.py --repo . --json
```

Fail if the score rises above a chosen threshold:

```bash
python3 python/agent_cost_leak_check.py --repo . --max-score 40
```

## GitHub Actions

Add this to `.github/workflows/agent-cost-leak.yml`:

```yaml
name: Agent cost leak check

on:
  pull_request:
  push:
    branches: [main]

jobs:
  agent-cost-leak:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Download checker
        run: |
          curl -fsSL \
            https://raw.githubusercontent.com/sravan27/context-os/main/python/agent_cost_leak_check.py \
            -o /tmp/agent_cost_leak_check.py

      - name: Run checker
        run: |
          python3 /tmp/agent_cost_leak_check.py --repo . --max-score 40 | tee agent-cost-leak-report.md

      - name: Add report to job summary
        if: always()
        run: cat agent-cost-leak-report.md >> "$GITHUB_STEP_SUMMARY"
```

Start with `--max-score 60` if your repo is large or generated-heavy, then lower the threshold after adding ignore rules, repo guidance, and explicit validation notes.

## Private Audit

The paid audit applies the same idea to private repo structure, prompts, and real agent transcripts, then ships a report plus one concrete fix path:

https://sravan27.github.io/money-27-proof/agent-cost-leak-audit.html
