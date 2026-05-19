---
description: Show current context-os graph status, git state, and recent session signals for the active repository.
allowed-tools: [Bash]
disable-model-invocation: true
---

# Context OS Stats

Prefer the CLI status command when available:

```bash
context-os status
```

If the binary is not installed, show the local graph and git snapshot:

```bash
python3 - <<'PY'
import json, os, subprocess
root = os.getcwd()
graph = os.path.join(root, ".context-os", "repo-graph.json")
print("repo:", root)
print("graph:", "present" if os.path.exists(graph) else "missing")
if os.path.exists(graph):
    data = json.load(open(graph))
    print("files:", len(data.get("files", {})))
    print("hot:", ", ".join(h.get("path", "") for h in data.get("hot_files", [])[:3]))
try:
    print(subprocess.check_output(["git", "status", "--short", "--branch"], text=True).strip())
except Exception as exc:
    print("git:", exc)
PY
```

Keep the answer short and focused on whether auto-context is ready.
