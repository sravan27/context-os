# Limitations

## Current limitations

- Context OS does not bypass Anthropic limits; it preserves continuity and trims obvious waste
- Claude Code integration is hook-based and depends on the stability of Claude Code hook surfaces
- Repo memory currently focuses on generic source/config indexing and Next.js-style route detection
- Session memory capture is heuristic and event-driven; it is not semantic reasoning over every turn
- Dashboard is scaffolded but not yet connected to live telemetry data
- The prompt linter uses heuristic rules rather than model-based classification
- Only safe-mode reducers are benchmarked as recommended defaults today
- Response shaping is not implemented yet

## Safety tradeoff

Safe mode deliberately leaves some compression opportunities unused to preserve protected strings and maintain user trust.
