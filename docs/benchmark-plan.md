# Benchmark Plan

## Core metrics

- Estimated token reduction percentage
- Protected-string recall
- File-path and command recall
- Error and root-cause retention
- Latency overhead
- Session memory retention
- Downstream task quality proxies

## Fixture classes

- Stack traces
- Test and build logs
- JSON payloads
- Config-debugging files
- Markdown planning docs
- Long session traces
- Repo onboarding samples

## Gates

- Safe mode must retain 100% of protected literals in benchmark fixtures
- Safe mode must retain 100% of shell commands, file paths, and version strings in fixtures
- Balanced mode cannot be recommended if downstream quality drops beyond the configured tolerance

## Current implementation

- Dataset manifest:
  `python/evals/datasets/safe_mode_cases.json`
- Runner:
  `python/evals/runners/safe_mode_runner.py`
- Reports:
  `python/evals/reports/safe-mode-report.json`
  `python/evals/reports/safe-mode-report.md`
