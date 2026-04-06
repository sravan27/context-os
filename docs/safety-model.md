# Safety Model

## Default posture

Context OS defaults to safe mode. Safe mode optimizes for trust and recall before maximal compression.

## Non-negotiable rules

- No silent mutation of user intent in default mode
- No code block rewriting in safe mode
- No dropping explicit commands, file paths, version strings, or protected literals in safe mode
- Every transformation carries a reason, provenance note, and estimated before/after token counts
- Reducer failure passes through original content

## Failure handling

- Parser or reducer errors are surfaced in metadata
- Original content is preserved when reduction is unsafe or impossible
- Future aggressive modes must be benchmarked separately from safe mode
