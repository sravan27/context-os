# Next.js example

A minimal Next.js 15 fixture to test Context OS against.

## Try it

```bash
cp -r examples/stacks/nextjs /tmp/nextjs-demo
cd /tmp/nextjs-demo
git init -q
bash /path/to/context-os/setup.sh --measure
bash /path/to/context-os/setup.sh
```

## What happens

1. Stack detection sees `package.json` + `next` dependency → marks stack as `node, typescript, next.js`.
2. `.claudeignore` blocks `.next/`, `node_modules/`, `dist/`, `out/`, `.vercel/`, `.turbo/` — the common Next.js noise.
3. `CLAUDE.md` repo map shows Claude that `app/` is the router entry.
4. Slash commands and explorer subagent install normally.

## Typical savings

On a real Next.js app with a populated `node_modules` (~12K files):

```
Noise filtering:         ~50K tokens
Response shaping:        ~20K tokens
Thinking cap (8K):       ~15K tokens
Haiku exploration:       ~10K tokens
Output compression:      ~8K tokens
────────────────────────────────────
TOTAL:                   ~103K tokens/session
```

On a fresh scaffold before `npm install`, noise filtering savings are near zero. The value appears after dependencies are installed.
