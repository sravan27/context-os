# Examples

Real before/after captures from running Context OS on common project shapes.

Each directory shows:
- `before/` — the bare project (a minimal but representative fixture)
- `after/` — the same project after running `setup.sh`
- `measure.txt` — the output of `setup.sh --measure`

Rerun locally:

```bash
cd examples/nextjs
cp -r before /tmp/nextjs-test && cd /tmp/nextjs-test
bash /path/to/context-os/setup.sh --measure
bash /path/to/context-os/setup.sh
```

## Included

| Stack | Source files | Noise files | Est. savings/session |
|-------|--------------|-------------|----------------------|
| Next.js 15 | ~50 | ~12,000 | ~100K tokens |
| Django 5 | ~30 | ~3,000 | ~70K tokens |
| Rust workspace | ~40 | ~8,000 | ~90K tokens |

Numbers vary with actual project size and `node_modules`/`target` state.

## Add your own

If Context OS helps your stack and you have a clean fixture to share, [open a PR](../CONTRIBUTING.md). Especially welcome:

- Monorepos (pnpm, Turborepo, Nx)
- Python ML (PyTorch, transformers, HuggingFace)
- Flutter / Dart
- Go modules with vendored dependencies
