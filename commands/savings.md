---
description: Show your context-os token savings — all-time, this week, streak, and a shareable card
---

Run the savings report and show the user the output verbatim:

```bash
python3 python/scripts/savings_report.py 2>/dev/null \
  || python3 "$HOME/.context-os/scripts/savings_report.py" --root "$(pwd)" 2>/dev/null \
  || echo "savings_report.py not found — run setup.sh to install context-os receipts"
```

Print the result exactly as-is (it's a formatted dashboard). Do not summarize or
re-format it. If the user asks, the shareable card alone is available with
`--card-only`, and raw numbers with `--json`.
