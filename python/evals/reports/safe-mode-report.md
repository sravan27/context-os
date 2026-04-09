# Safe Mode Benchmark Report

- Generated at: `2026-04-09T14:58:18.749920+00:00`
- Dataset: `python/evals/datasets/safe_mode_cases.json`
- Passed cases: `7/7`

## Reducer Results

| Case | Recall | Reduction % | Before | After | Passed |
| --- | ---: | ---: | ---: | ---: | --- |
| stack_trace_safe | 1.00 | 42.28 | 149 | 86 | yes |
| test_log_safe | 1.00 | 36.20 | 163 | 104 | yes |
| json_safe | 1.00 | 13.07 | 199 | 173 | yes |
| config_safe | 1.00 | 12.99 | 77 | 67 | yes |
| build_log_safe | 1.00 | 33.04 | 566 | 379 | yes |
| lint_output_safe | 1.00 | 26.38 | 599 | 441 | yes |

## Prompt Linter Results

| Case | Finding Recall | Findings | Passed |
| --- | ---: | ---: | --- |
| prompt_lint_long_prompt | 1.00 | 4 | yes |

## Gates

- Safe reducer protected-string recall: 1.0 required
- Prompt-linter finding recall: 1.0 required for expected benchmark findings
- Safe transformed reducer token behavior: after_tokens must be <= before_tokens
