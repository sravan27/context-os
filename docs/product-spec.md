# Product Spec

## Thesis

Context OS is a local context optimization layer for coding agents. It reduces repeated context waste caused by repo rediscovery, noisy logs, long sessions, and brittle compaction.

## MVP goals

- Intercept or shape coding workflow context locally
- Preserve user trust through explicit, reversible transformations
- Provide typed reducers instead of a single lossy summarizer
- Compile durable repo memory to reduce onboarding tax
- Lint prompt structure before waste reaches the model context window
- Measure savings and quality tradeoffs with local benchmarks

## MVP non-goals

- Cloud analytics
- Autonomous coding orchestration
- Black-box prompt rewriting
- Marketing-style compression claims without benchmark labeling

## Initial wedge

- Primary user: heavy Claude Code users working in real repositories
- Secondary target: future compatibility with Codex, Gemini CLI, and Aider-like workflows
