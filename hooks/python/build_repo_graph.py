#!/usr/bin/env python3
"""
build_repo_graph.py — Context OS repo graph generator.

Zero-dependency (stdlib only) walker that extracts:
- Top-level symbols per source file (Rust, Python, JS, TS, Go)
- Import edges (who imports whom)
- Hot files from git log (change frequency, last 90 days)

Writes `.context-os/repo-graph.json` and prints a short markdown summary to
stdout for setup.sh to embed into CLAUDE.md. Runs in a few hundred ms on
most repos; skips node_modules/target/dist/etc. automatically.

Invoked:
    python3 build_repo_graph.py [repo_root]

Exit 0 always. Failure to parse any file is silent (partial graphs are fine).
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Language patterns. Each matches top-level declarations on their own line.
# Keep patterns conservative — false negatives > false positives.
# ---------------------------------------------------------------------------
LANG_PATTERNS = {
    "rust": {
        "exts": [".rs"],
        "symbol": re.compile(
            r"^\s*(?:pub(?:\s*\([^)]*\))?\s+)?(?:async\s+)?"
            r"(fn|struct|enum|trait|type|mod|const|static)\s+([A-Za-z_][A-Za-z0-9_]*)"
        ),
        "import": re.compile(r"^\s*use\s+([A-Za-z_][\w:]*)"),
    },
    "python": {
        "exts": [".py"],
        "symbol": re.compile(r"^(?:async\s+)?(def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"),
        "import": re.compile(
            r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))"
        ),
    },
    "javascript": {
        "exts": [".js", ".mjs", ".cjs", ".jsx"],
        "symbol": re.compile(
            r"^export\s+(?:default\s+)?(?:async\s+)?"
            r"(function|class|const|let|var)\s+([A-Za-z_$][\w$]*)"
        ),
        "import": re.compile(
            r"""^\s*(?:import\b[^"']*from\s+["']([^"']+)["']"""
            r"""|const\s+[\w{},\s*]+\s*=\s*require\(\s*["']([^"']+)["']\s*\))"""
        ),
    },
    "typescript": {
        "exts": [".ts", ".tsx"],
        "symbol": re.compile(
            r"^export\s+(?:default\s+)?(?:async\s+)?"
            r"(function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)"
        ),
        "import": re.compile(r"""^\s*import\b[^"']*from\s+["']([^"']+)["']"""),
    },
    "go": {
        "exts": [".go"],
        # match `func Name(` or `func (r *Recv) Name(` or `type Name`
        "symbol": re.compile(
            r"^func\s+(?:\([^)]*\)\s+)?([A-Z][\w]*)\s*\(|^type\s+([A-Z][\w]*)"
        ),
        "import": re.compile(r'^\s*"([^"]+)"'),
    },
}

EXCLUDE_DIRS = {
    "node_modules", "target", "dist", "build", ".next", ".git", ".venv", "venv",
    "__pycache__", ".pytest_cache", "coverage", ".turbo", ".cache",
    ".mypy_cache", ".ruff_cache", ".tox", "bower_components", "vendor",
    ".idea", ".vscode", ".context-os",
}
# Prefix-based excludes: dir name starts with any of these. Catches eval
# fixtures, sibling mock repos, etc. without enumerating every variant.
EXCLUDE_DIR_PREFIXES = (
    "autocontext_fixture",   # our own eval fixtures — don't pollute graph
)

# Absolute cap per file to keep pathological files from stalling the walker
MAX_LINES_SCAN = 20000


def walk_sources(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS and not d.startswith(".")
            and not any(d.startswith(p) for p in EXCLUDE_DIR_PREFIXES)
        ]
        for fn in filenames:
            if fn.startswith("."):
                continue
            ext = os.path.splitext(fn)[1]
            for lang, cfg in LANG_PATTERNS.items():
                if ext in cfg["exts"]:
                    path = os.path.join(dirpath, fn)
                    rel = os.path.relpath(path, root)
                    yield rel, lang, path, cfg
                    break


def extract(path, cfg):
    symbols = []
    imports = []
    line_count = 0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, 1):
                if i > MAX_LINES_SCAN:
                    break
                line_count = i
                s = cfg["symbol"].search(line)
                if s:
                    groups = [g for g in s.groups() if g]
                    if len(groups) >= 2:
                        symbols.append(
                            {"name": groups[1], "kind": groups[0], "line": i}
                        )
                    elif len(groups) == 1:
                        symbols.append(
                            {"name": groups[0], "kind": "symbol", "line": i}
                        )
                im = cfg["import"].search(line)
                if im:
                    modules = [g for g in im.groups() if g]
                    if modules:
                        imports.append(modules[0])
    except Exception:
        pass
    # dedupe imports preserving order
    seen = set()
    unique_imports = []
    for m in imports:
        if m not in seen:
            seen.add(m)
            unique_imports.append(m)
    return symbols, unique_imports, line_count


def hot_files(root, max_items=20):
    try:
        out = subprocess.check_output(
            [
                "git", "-C", root, "log", "--name-only",
                "--since=90.days", "--pretty=format:", "-n", "500",
            ],
            stderr=subprocess.DEVNULL, text=True, timeout=15,
        )
    except Exception:
        return []
    counts = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        top = line.split("/", 1)[0]
        if top in EXCLUDE_DIRS:
            continue
        # Also honor prefix excludes at any path depth (fixture dirs etc.).
        if any(seg.startswith(p) for seg in line.split("/")
               for p in EXCLUDE_DIR_PREFIXES):
            continue
        # skip obvious lockfiles and binaries
        base = os.path.basename(line).lower()
        if base in {"package-lock.json", "yarn.lock", "cargo.lock",
                   "poetry.lock", "pnpm-lock.yaml", "composer.lock"}:
            continue
        counts[line] = counts.get(line, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:max_items]
    return [{"path": p, "touches": c} for p, c in ranked]


_PATH_TOK_RE_CAMEL = re.compile(r"[a-z]+|[0-9]+")
_PATH_TOK_RE_SPLIT = re.compile(r"[_\-.]+")


def _path_tokens(fpath):
    """Tokens used by the hook's IDF weighting. Mirror of the hook's
    `_file_path_tokens` — precomputing here avoids an O(N) scan on
    every UserPromptSubmit. At 50k files this drops p99 by ~70%."""
    toks = set()
    low = fpath.lower()
    for seg in re.split(r"[/\\]+", low):
        base = os.path.splitext(seg)[0]
        for part in _PATH_TOK_RE_SPLIT.split(base):
            if len(part) >= 2:
                toks.add(part)
            for sub in _PATH_TOK_RE_CAMEL.findall(part):
                if len(sub) >= 2:
                    toks.add(sub)
    return toks


def build(root):
    files = {}
    symbol_index = {}
    imported_by = {}
    path_df = {}   # token -> document frequency across file paths

    for rel, lang, path, cfg in walk_sources(root):
        symbols, imports, lines = extract(path, cfg)
        files[rel] = {
            "lang": lang,
            "lines": lines,
            "symbols": symbols,
            "imports": imports,
        }
        for sym in symbols:
            symbol_index.setdefault(sym["name"], []).append(
                {"file": rel, "line": sym["line"], "kind": sym["kind"]}
            )
        for im in imports:
            imported_by.setdefault(im, []).append(rel)
        for t in _path_tokens(rel):
            path_df[t] = path_df.get(t, 0) + 1

    return {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": os.path.abspath(root),
        "file_count": len(files),
        "symbol_count": sum(len(f["symbols"]) for f in files.values()),
        "hot_files": hot_files(root),
        "files": files,
        "symbol_index": symbol_index,
        "imported_by": imported_by,
        "path_df": path_df,
    }


def summary_md(graph):
    lines = []
    lines.append(
        f"- Graph: {graph['file_count']} files, "
        f"{graph['symbol_count']} top-level symbols indexed."
    )
    hf = graph.get("hot_files", [])
    if hf:
        top = ", ".join(f"`{h['path']}` ({h['touches']})" for h in hf[:5])
        lines.append(f"- Hot files (90d): {top}")
    lines.append(
        "- Query via `/find <symbol>`, `/deps <file>`, `/hot` — "
        "reads `.context-os/repo-graph.json` (no grep)."
    )
    return "\n".join(lines)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    try:
        graph = build(root)
    except Exception as e:
        sys.stderr.write(f"[context-os] repo-graph build failed: {e}\n")
        return 0
    out_dir = os.path.join(root, ".context-os")
    try:
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "repo-graph.json")
        with open(out_path, "w") as f:
            json.dump(graph, f, separators=(",", ":"))
        sys.stderr.write(
            f"[context-os] repo-graph: {out_path} "
            f"({graph['file_count']} files, {graph['symbol_count']} symbols)\n"
        )
    except Exception as e:
        sys.stderr.write(f"[context-os] repo-graph write failed: {e}\n")
        return 0
    print(summary_md(graph))
    return 0


if __name__ == "__main__":
    sys.exit(main())
