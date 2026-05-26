---
description: Show a file's structural map (symbols + line ranges) so you can read only the slice you need
---

Run, substituting the file the user named (or the one in context):

```bash
python3 .context-os/scripts/outline.py "<file>" --root "$(pwd)" 2>/dev/null \
  || python3 python/scripts/outline.py "<file>" --root "$(pwd)" 2>/dev/null \
  || echo "No graph yet — run /rebuild-graph first."
```

Print the output verbatim. It lists every top-level symbol with its exact line
range. Use it to `Read(file, offset=N, limit=M)` the precise block you need
instead of loading the whole file into context.
