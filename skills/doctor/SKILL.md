---
description: Validate context-os setup, graph availability, and local hook health in the current repository.
allowed-tools: [Bash]
disable-model-invocation: true
---

# Context OS Doctor

Prefer the CLI doctor when available:

```bash
context-os doctor --root .
```

If the binary is not installed, run the lightweight local checks:

```bash
test -f .context-os/repo-graph.json && echo "repo graph: present" || echo "repo graph: missing"
python3 hooks/python/build_repo_graph.py . >/dev/null && echo "graph builder: ok"
printf '{"prompt":"where is the main entrypoint","cwd":"%s"}\n' "$PWD" | python3 hooks/python/auto_context.py
```

Show the output and name the next concrete fix.
