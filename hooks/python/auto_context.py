#!/usr/bin/env python3
"""
auto_context.py — Context OS UserPromptSubmit hook.

Static-analysis RAG without embeddings. Before Claude sees the user prompt,
we parse it for keywords/paths/symbols, look them up in the pre-built
`.context-os/repo-graph.json`, and emit a compact "candidate files" block
on stdout. Claude Code prepends it to the prompt as additional context.

Claude's first turn starts with structure already in hand — typical save is
5-10 exploratory tool calls on non-trivial repos.

Zero-dep stdlib. Fail-open on any error. Silent on no-match.

Env:
- CONTEXT_OS_AUTOCONTEXT=0            disable entirely
- CONTEXT_OS_AUTOCONTEXT_MAX=5        max candidates injected (default 5)
- CONTEXT_OS_AUTOCONTEXT_MIN_WORD=4   min keyword length to match (default 4)
- CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT=15  skip if prompt shorter than this

Protocol:
- stdin: {"prompt": "...", "session_id": "...", ...}
- stdout: text block (prepended to prompt as context)
- exit 0 always
"""
import json
import os
import re
import sys

# Common English + code-chatter words that shouldn't drive symbol lookup.
STOPWORDS = frozenset([
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "her",
    "was", "one", "our", "out", "day", "had", "has", "him", "his", "how",
    "man", "new", "now", "old", "see", "two", "way", "who", "boy", "did",
    "its", "let", "put", "say", "she", "too", "use", "from", "with", "that",
    "this", "have", "will", "your", "what", "when", "make", "like", "time",
    "just", "know", "take", "into", "them", "some", "could", "other", "than",
    "then", "look", "only", "come", "over", "also", "back", "after", "first",
    "well", "even", "want", "any", "way", "been", "which", "their", "work",
    "fix", "add", "remove", "update", "create", "delete", "change", "file",
    "files", "code", "function", "class", "method", "please", "thanks", "help",
    "need", "want", "should", "could", "would", "show", "tell", "find",
    "check", "test", "run", "see", "does", "doing", "done", "make", "try",
    "using", "used", "still", "where", "there", "where", "because", "about",
    "very", "really", "much", "more", "less", "most", "least", "without",
    "within", "across", "between", "through", "during", "before", "after",
    "above", "below", "under", "over", "same", "different", "new", "old",
    "good", "bad", "best", "worst", "better", "worse", "maybe", "probably",
    "definitely", "exactly", "actually", "somehow", "instead", "rather",
    "something", "someone", "somewhere", "anything", "anyone", "anywhere",
    "nothing", "nobody", "nowhere", "everything", "everyone", "everywhere",
    "lets", "let's", "we're", "we've", "you're", "you've", "they're",
    "it's", "isn't", "wasn't", "weren't", "don't", "doesn't", "didn't",
    "won't", "wouldn't", "can't", "couldn't", "shouldn't", "haven't",
    "hasn't", "hadn't", "aren't",
])

# Camel/snake split to extract sub-tokens from a compound identifier.
CAMEL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|[_\-\s]+")
WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Heuristic path: foo/bar or foo.ext or foo/bar.ext
PATH_RE = re.compile(r"[\w./\-]+(?:/[\w./\-]+|\.[A-Za-z]{1,5})")


def load_graph(root):
    path = os.path.join(root, ".context-os", "repo-graph.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def extract_tokens(prompt, min_word):
    tokens = set()
    # Whole words
    for w in WORD_RE.findall(prompt):
        if len(w) < min_word:
            continue
        low = w.lower()
        if low in STOPWORDS:
            continue
        tokens.add(w)
        # Camel/snake sub-parts
        for part in CAMEL_SPLIT.split(w):
            if len(part) >= min_word and part.lower() not in STOPWORDS:
                tokens.add(part)
    return tokens


def extract_paths(prompt):
    paths = set()
    for m in PATH_RE.findall(prompt):
        # skip URLs-ish and bare numbers
        if "://" in m or m.count(".") > 4:
            continue
        if len(m) >= 3:
            paths.add(m)
    return paths


def rank(prompt, graph, max_hits, min_word):
    files = graph.get("files") or {}
    symbol_index = graph.get("symbol_index") or {}
    imported_by = graph.get("imported_by") or {}
    hot = {h.get("path"): h.get("touches", 0)
           for h in (graph.get("hot_files") or [])}

    tokens = extract_tokens(prompt, min_word)
    paths = extract_paths(prompt)

    # (file, line) -> {score, symbol, kind, reasons}
    candidates = {}

    def bump(file, line, kind, symbol, score, reason):
        key = (file, line)
        cur = candidates.get(key)
        if cur is None:
            candidates[key] = {
                "file": file, "line": line, "kind": kind, "symbol": symbol,
                "score": score, "reasons": [reason],
            }
        else:
            cur["score"] += score
            if reason not in cur["reasons"]:
                cur["reasons"].append(reason)

    # 1. Exact + case-insensitive symbol matches
    sym_lc = {k.lower(): k for k in symbol_index.keys()}
    for tok in tokens:
        # exact
        if tok in symbol_index:
            for loc in symbol_index[tok]:
                bump(loc["file"], loc["line"], loc.get("kind", ""),
                     tok, 10, f"symbol `{tok}`")
        # case-insensitive
        elif tok.lower() in sym_lc:
            real = sym_lc[tok.lower()]
            for loc in symbol_index[real]:
                bump(loc["file"], loc["line"], loc.get("kind", ""),
                     real, 8, f"symbol `{real}` (case-insensitive)")

    # 2. Path / substring in file keys
    for tok in list(tokens) + list(paths):
        tl = tok.lower()
        for fpath in files.keys():
            fl = fpath.lower()
            if fl == tl or fl.endswith("/" + tl) or ("/" in tl and tl in fl):
                bump(fpath, 1, "file", os.path.basename(fpath),
                     8, f"path `{tok}`")
            elif len(tl) >= 5 and tl in fl:
                bump(fpath, 1, "file", os.path.basename(fpath),
                     3, f"path contains `{tok}`")

    # 3. Import module matches — surface importers
    for tok in tokens:
        for mod, importers in imported_by.items():
            if tok == mod or (len(tok) >= 5 and tok in mod):
                for imp in importers[:3]:
                    bump(imp, 1, "importer", mod,
                         5, f"imports `{mod}`")

    # 4. Hot-file boost
    for key, c in candidates.items():
        if c["file"] in hot:
            c["score"] += 2
            c["reasons"].append(f"hot ({hot[c['file']]} touches/90d)")

    # 5. Test-file penalty — unless the prompt is explicitly about testing,
    # a test file is usually a less-relevant neighbor than the source it
    # exercises. Reduces false positives like `tests/test_foo.py` beating
    # `src/foo.py` on name-path matches.
    prompt_low = prompt.lower()
    mentions_tests = any(
        w in prompt_low for w in ("test", "tests", "pytest", "fixture")
    )
    if not mentions_tests:
        for key, c in candidates.items():
            f = c["file"]
            base = os.path.basename(f).lower()
            if (f.startswith("tests/") or f.startswith("test/")
                    or "/tests/" in f or "/test/" in f
                    or base.startswith("test_") or base.endswith("_test.py")
                    or base.endswith(".test.ts") or base.endswith(".test.js")
                    or base.endswith(".spec.ts") or base.endswith(".spec.js")):
                c["score"] -= 3
                c["reasons"].append("test-file penalty")

    ranked = sorted(candidates.values(),
                    key=lambda c: (-c["score"], c["file"], c["line"]))
    # Dedupe: keep at most 2 hits per file
    per_file = {}
    out = []
    for c in ranked:
        if per_file.get(c["file"], 0) >= 2:
            continue
        per_file[c["file"]] = per_file.get(c["file"], 0) + 1
        out.append(c)
        if len(out) >= max_hits:
            break
    return out


def format_block(hits, graph):
    if not hits:
        return ""
    files = graph.get("files") or {}
    lines = ["<context-os:autocontext>",
             "Graph-matched candidates (structure only, no files read yet):"]
    for c in hits:
        file = c["file"]
        sym = c["symbol"]
        kind = c["kind"]
        line = c["line"]
        finfo = files.get(file, {})
        imports = finfo.get("imports", [])
        marker = f"{file}:{line}" if line > 1 else file
        parts = [f"`{marker}`"]
        if kind and kind not in ("file", "importer"):
            parts.append(f"{sym} ({kind})")
        elif kind == "importer":
            parts.append(f"uses `{sym}`")
        if imports and len(imports) <= 3 and kind != "importer":
            parts.append(f"imports: {', '.join(imports)}")
        elif imports and kind != "importer":
            parts.append(f"{len(imports)} imports")
        lines.append("- " + " · ".join(parts))
    lines.append(
        "Verify before reading. `/find <symbol>` · `/deps <file>` for more. "
        "Disable: CONTEXT_OS_AUTOCONTEXT=0."
    )
    lines.append("</context-os:autocontext>")
    return "\n".join(lines)


def main():
    if os.environ.get("CONTEXT_OS_AUTOCONTEXT") == "0":
        return 0

    try:
        min_word = int(os.environ.get("CONTEXT_OS_AUTOCONTEXT_MIN_WORD", "4"))
        max_hits = int(os.environ.get("CONTEXT_OS_AUTOCONTEXT_MAX", "5"))
        min_prompt = int(os.environ.get("CONTEXT_OS_AUTOCONTEXT_MIN_PROMPT", "15"))
    except ValueError:
        return 0

    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0

    prompt = (event.get("prompt") or "").strip()
    if len(prompt) < min_prompt:
        return 0

    # Skip common continuation tokens
    low = prompt.lower()
    if low in {"continue", "ok", "yes", "no", "go", "fix it", "do it",
               "run it", "try again", "retry", "next", "what", "why"}:
        return 0

    cwd = event.get("cwd") or os.getcwd()
    graph = load_graph(cwd)
    if not graph:
        return 0

    hits = rank(prompt, graph, max_hits, min_word)
    block = format_block(hits, graph)
    if block:
        sys.stdout.write(block + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
