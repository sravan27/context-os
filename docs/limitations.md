# Limitations

## Current limitations

- Claude Code integration is scaffolded but not yet wired end to end
- Repo memory currently focuses on generic source/config indexing and Next.js-style route detection
- Session memory is file-backed today but not yet integrated with a live Claude Code hook/install flow
- Dashboard is scaffolded but not yet connected to live telemetry data
- The prompt linter uses heuristic rules and is not yet benchmark-calibrated
- Only four reducers are implemented in this checkpoint
- Response shaping is not implemented yet

## Safety tradeoff

Safe mode deliberately leaves some compression opportunities unused to preserve protected strings and maintain user trust.
