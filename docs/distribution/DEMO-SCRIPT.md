# Demo recording script

Goal: a 60-90 second asciinema (or screen-recorded terminal) clip that shows the savings live. Drops into the HN post, the README, the X thread, and the LinkedIn post.

## Tooling

- `asciinema rec` (preferred — text, embeddable, plays in browser via asciinema-player)
- Fallback: QuickTime screen recording → upload to Loom or YouTube unlisted
- Don't use animated GIFs >2MB — they get blocked by Reddit/HN.

## Script (run live, do not edit)

```bash
# 0:00 — Title card (typed slowly for impact)
clear
echo "context-os v2.8.0 — live demo (no edits)"
echo "Goal: cut Claude Code's first-turn token spend"
echo ""

# 0:05 — Show what's installed
ls -la .claude/hooks/auto_context.py | awk '{print "auto_context.py:", $5, "bytes,", $9}'
wc -l .claude/hooks/auto_context.py

# 0:10 — Show the graph
ls -la .context-os/repo-graph.json | awk '{print "repo-graph.json:", $5, "bytes"}'
python3 -c "
import json
g = json.load(open('.context-os/repo-graph.json'))
print(f\"  files indexed: {len(g['files'])}\")
print(f\"  symbols extracted: {sum(len(g.get('symbol_index', {}).get(k, [])) for k in g.get('symbol_index', {}))}\")
print(f\"  hot files: {len(g.get('hot_files', []))}\")
"

# 0:20 — Show what auto_context injects, given a prompt
echo ""
echo "→ Prompt: 'where is the gitignore parser'"
echo ""
echo '{"prompt": "where is the gitignore parser"}' | python3 .claude/hooks/auto_context.py 2>/dev/null | head -30

# 0:35 — Run the cross-repo eval (live, ~30s)
echo ""
echo "→ Running cross-repo eval (3 OSS repos, 36 prompts)..."
python3 python/evals/runners/multi_repo_eval.py --skip-clone 2>&1 | grep -E "MRR|weighted|wrote"

# 1:05 — Run the regression floor
echo ""
echo "→ 9 CI-enforced regression gates..."
python3 python/evals/runners/ranker_floor.py 2>&1 | grep -E "PASS|all floors"

# 1:25 — Outro
echo ""
echo "github.com/sravan27/context-os"
echo "MIT · stdlib Python · no embeddings · no server"
```

## Pre-record checklist

- [ ] `asciinema --version` works
- [ ] Terminal is 100×30, monospace 14pt minimum
- [ ] `.context-os/repo-graph.json` exists (run `setup.sh` first)
- [ ] `/tmp/cos-multi-repo/` is staged (or use `--skip-clone false` and add 30s)
- [ ] No personal env vars or paths in PROMPT (`PS1='$ '`)
- [ ] Close all editor tabs, mute notifications

## Record command

```bash
asciinema rec demo.cast --command "bash docs/distribution/demo.sh" --idle-time-limit 1.5
asciinema upload demo.cast
```

The `--idle-time-limit 1.5` flag fast-forwards through long pauses so the
viewer doesn't sit through the 30s eval wait — great UX, honest semantics.

## Post-record

- [ ] Watch the recording end-to-end at 1× speed. If anything's broken, re-record. Do not edit.
- [ ] Get the asciinema.org URL.
- [ ] Embed in README.md right under the headline:
  ```
  [![demo](https://asciinema.org/a/<id>.svg)](https://asciinema.org/a/<id>)
  ```
- [ ] Drop the URL into:
  - HN first comment ("60-second demo of the eval running: <url>")
  - X thread tweet 4
  - LinkedIn post (paste URL, LinkedIn unfurls asciinema natively)
  - GitHub release notes (edit existing v2.8.0 release)

## Alternative: GIF for Reddit / Twitter

Convert asciinema → GIF if needed:

```bash
agg demo.cast demo.gif --speed 2
```

Cap GIF under 5MB or Twitter strips quality. Trim to the 30 second hot path
(graph build + eval running) — drop the title card and outro for the GIF
version.

## A note on honesty

Do NOT speed up the cross-repo eval more than 2×. The 30 seconds is part of
the demo — the message is "this is a real eval running on a real codebase,
not a marketing GIF." Speed = lost credibility. Idle-time-limit is fine
because it skips waits, not work.
