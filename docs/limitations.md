# Limitations

## What the headline numbers do and don't mean

- **The −40.9% live A/B is cold-cache `claude --print` one-shots (N=36, 6 prompts, one repo, an earlier build).** That setup isolates the hook's effect cleanly, but it is **not** a warm interactive session. In a warm session, prompt caching makes re-sent context cheap, so the **dollar** savings are materially smaller than 40.9%. The durable, version-independent wins are fewer first-turn tool calls and hitting the context limit / compaction later — not a 41% smaller bill. The bankable, CI-gated claim is retrieval quality (MRR), not the bill figure.
- **`smart_read` and Receipts only see the `Read` tool.** When Claude views a file via Bash (`cat`, `sed -n`, `head`, `grep`) instead of `Read`, smart_read does not intercept the whole-file dump and Receipts does not count it. In Bash-heavy sessions both under-deliver. (Typical interactive Claude Code favors the `Read` tool, where coverage is full; autonomous/agentic sessions that lean on Bash are the gap.)
- **Receipts under-count by design.** Assisted hits require Claude's first action to be a `Read` of a surfaced file; the per-hit credit is conservative and clamped. Real impact is likely higher than the dashboard shows, not lower.
- **auto_context is lexical retrieval.** On prompts that already name the exact class/symbol, well-tuned BM25 ties it (the `psf/requests` regime). It targets navigation ("where/how does X work"), not string-replace greps.

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
