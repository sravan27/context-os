---
description: Initialize context-os in the current project by building the local repo graph and installing Claude Code guidance.
argument-hint: [--global]
allowed-tools: [Bash]
disable-model-invocation: true
---

# Initialize Context OS

Run the installer in the current project:

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash
```

If the user supplied `--global`, pass it through:

```bash
curl -fsSL https://raw.githubusercontent.com/sravan27/context-os/main/setup.sh | bash -s -- --global
```

Show the command output. If installation fails, report the exact failing line and suggest running `context-os:doctor` after fixing it.
