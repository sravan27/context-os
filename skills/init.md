---
name: init
description: Initialize context-os in the current project — scan repo, generate CLAUDE.md, set up session continuity
user_invocable: true
---

Run context-os init to set up the current project:

```bash
context-os init
```

This will:
1. Scan the repo and generate a structural map in CLAUDE.md
2. Create .context-os/ directory for session state
3. Add .context-os/ to .gitignore

Show the output to the user.
