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
- Compaction dataset:
  `python/evals/datasets/compaction_survival_cases.json`
- Compaction runner:
  `python/evals/runners/compaction_survival_runner.py`
- Compaction reports:
  `python/evals/reports/compaction-survival-report.json`
  `python/evals/reports/compaction-survival-report.md`

## Current safe recommendation gates

- Safe reducer protected-string recall: 100%
- Prompt-linter expected finding recall: 100%
- Compaction survival pinned-fact retention: 100%
- Compaction survival current-subtask retention: 100%
- Compaction survival latest-decision retention: 100%
- Compaction survival modified-file retention: 100%
