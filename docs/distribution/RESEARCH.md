# Distribution research (snapshot 2026-04-25)

Background facts gathered before launch — pin to this date, will rot fast.

## anthropics/claude-code repo

- 117.7k stars · 19.6k forks
- Issues enabled. **Discussions disabled.** No `CONTRIBUTING.md` at root.
- Issue templates: `bug_report`, `feature_request`, `documentation`, `model_behavior`. `blank_issues_enabled: false` — must use a template.
- Community discussion funneled to **Anthropic Discord**: https://anthropic.com/discord
- Top human contributors:
  - `bcherny` — Boris Cherny, Head of Claude Code (70 commits, top contributor)
  - `ant-kurt` — Kurt (Anthropic) (32)
  - `bogini` (21)
  - `fvolcic` (20)
  - `ashwin-ant` — Ashwin (Anthropic) (19)
  - `OctavianGuzu` (13)
  - `chrislloyd` — Chris Lloyd (8)
  - `ThariqS` — Thariq Shihipar (8)
  - `catherinewu` — Cat Wu, Head of Product Claude Code (8)
- Recent issues that drew engagement (use as framing reference):
  - #50623 "[Bug] Opus 4.7 performance degradation and excessive token consumption" — labeled `area:cost`
  - #44855 "[Bug] Stop hooks failing, causing rapid token consumption"
  - #51487 "Explore agent used unnecessarily — 84k tokens wasted"
  - #46652 "[Regression v2.1.89] Max subscription severely degraded"
  - #46802 "[FEATURE] Document optimal context window ranges for 1M token models"
- Pattern: `area:cost` label + concrete token numbers + reproducible diff get traction.

## Anthropic developer outreach channels

- **Discord:** https://anthropic.com/discord (~90k members) — only sanctioned community channel.
- **Channels feature** (research preview): plugin allowlist via `anthropics/claude-plugins-official` GitHub repo. Getting on that allowlist is direct surface area.
- **X accounts to watch / engage:**
  - `@bcherny` — Boris Cherny, 261.5k followers
  - `@catherinewu` — Cat Wu
  - `@alexalbert__` — Alex Albert (DevRel)
  - `@trq212` — Thariq Shihipar
  - `@AnthropicAI` — corporate
- **Newsletters that lift launches:** Lenny's Newsletter, Pragmatic Engineer, Every podcast.

## Hacker News landscape — Show HN, last 6 months

| Title | Pts | Comments | Framing lesson |
|---|---:|---:|---|
| CodeBurn — Analyze Claude Code token usage by task | 112 | 26 | "$1400/week with no visibility" — personal cost hook + surprising stat (56% on no-tool turns) |
| Ctx — `/resume` across Claude Code and Codex | 72 | 28 | Cross-tool portability pain framing |
| Claude Code rewritten as a bash script | 62 | 19 | Anti-bloat ("I built it in 1k lines") |
| (anti-pattern) "open-sourced internals" framing | 7 | low | Title that signals self-promotion underperforms |

**Winning framing pattern:** specific dollar/token number in title + first-person motivation + one striking statistic in the body.

## Closest competitors / prior art

- **zilliztech/claude-context** — MCP, vector search via Zilliz Cloud, ~40% claim, cloud-coupled.
- **Madhan230205/token-reducer** — closest match: hybrid RAG (BM25 + ONNX), AST chunking, local-first, claims 90%+. Treat as the strongest direct competitor on framing.
- **egorfedorov/claude-context-optimizer** — PostToolUse hooks, read-cache + contextignore, 63% claim. Hook-based architecture.
- **evanrianto/claude-codebase-indexer** — semantic vector search.
- **ItMeDiaTech/rag-cli** — Chroma + multi-agent.
- **web-werkstatt/ai-context-optimizer** — multi-tool (Cline/Copilot/Claude/Cursor), 76% claim.
- **Aider, Cline, Continue.dev** — adjacent, not Claude Code plugins. Aider already cited as 4.2× more token-efficient than Claude Code (Morph benchmark) — useful to position against.

## Differentiation angle for context-os

> Static-analysis RAG as a **primitive** (not vector-DB-coupled). Live A/B with real Claude calls (not synthetic eval). Cross-repo evidence on 3 unseen OSS repos. CI-gated regression floor. MIT.

Lead with "live A/B 40.9% on real Claude calls" — most competitors quote synthetic numbers; we can quote both, plus cross-repo aggregate, plus statistical significance.

## Sources

- https://github.com/anthropics/claude-code
- https://github.com/anthropics/claude-plugins-official
- https://discord.com/invite/6PPFFzqPDZ
- https://code.claude.com/docs/en/channels
- https://x.com/bcherny
- https://news.ycombinator.com/item?id=47759035 (CodeBurn)
- https://news.ycombinator.com/item?id=47836740 (Ctx)
- https://news.ycombinator.com/item?id=47594804 (bash-script)
- https://github.com/zilliztech/claude-context
- https://github.com/Madhan230205/token-reducer
- https://egorfedorov.github.io/claude-context-optimizer/
- https://www.lennysnewsletter.com/p/head-of-claude-code-what-happens
