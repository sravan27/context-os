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
- CONTEXT_OS_AUTOCONTEXT_ABLATE=a,b   comma list of signals to disable. Names:
                                      `symbol_exact`, `symbol_ci` (case-insens),
                                      `path_exact`, `path_substr`, `import`,
                                      `hot`, `test_penalty`, `hub_penalty`.
                                      For ablation studies only.

Protocol:
- stdin: {"prompt": "...", "session_id": "...", ...}
- stdout: text block (prepended to prompt as context)
- exit 0 always
"""
import json
import math
import os
import re
import sys

# Small natural-language → code-term expansion. Kept deliberately small so
# it can't hijack unrelated prompts; tuned from dogfood failures where the
# prompt describes behavior ("enormous") and the code uses a different
# convention ("size"). Each mapping must be defensible in isolation.
EXPANSIONS = {
    "duplicate": ("dedup",), "duplicates": ("dedup",),
    "dedupe": ("dedup",), "deduplicate": ("dedup",),
    "block": ("guard",), "blocks": ("guard",), "blocking": ("guard",),
    "enormous": ("size", "large"), "huge": ("size", "large"),
    "big": ("size",), "gigantic": ("size", "large"),
    "benchmark": ("bench",), "benchmarks": ("bench",),
    "benchmarking": ("bench",), "bench": ("bench",),
    "simulator": ("replay", "simulate"), "simulation": ("replay", "simulate"),
    "simulate": ("replay", "simulate"),
    "adversarial": ("robust", "robustness"),
    "robustness": ("robust",), "robust": ("robust",),
    "warmup": ("prewarm", "warm"), "warm-up": ("prewarm", "warm"),
    "evaluation": ("eval",), "evaluate": ("eval",),
    "statistics": ("stats",), "statistical": ("stats",),
    "ablation": ("ablate", "ablat"),
    "ranking": ("rank",), "scoring": ("rank", "score"),
    "penalty": ("penalt",), "penalize": ("penalt",), "penalise": ("penalt",),
    "savings": ("saving", "save"), "saved": ("save",),
    "authentication": ("auth",), "authenticate": ("auth",),
    "authenticated": ("auth",), "authenticating": ("auth",),
    "authorization": ("auth",), "authorize": ("auth",),
    "exception": ("except",), "exceptions": ("except",),
    "configure": ("config",), "configuration": ("config",),
    "configured": ("config",), "configuring": ("config",),
    "persistence": ("persist",), "persisting": ("persist",),
    "persisted": ("persist",),
    "directory": ("dir",), "directories": ("dir",),
    "initialize": ("init",), "initialized": ("init",),
    "initialization": ("init",),
    "comparison": ("compare", "cmp"), "comparing": ("compare", "cmp"),
    "connection": ("conn",), "connections": ("conn",),
    "parser": ("parse",), "parsed": ("parse",), "parsing": ("parse",),
    "compiler": ("compile",), "compiled": ("compile",),
    "compilation": ("compile",),
    "printer": ("print",), "printing": ("print",),
    "matcher": ("match",), "matching": ("match",), "matches": ("match",),
    "walker": ("walk",), "walking": ("walk",),
    "searcher": ("search",), "searching": ("search",),
}

# Common English + code-chatter words that shouldn't drive symbol lookup.
# NOTE: entries that can legitimately appear in filenames (test, file, find,
# run, check, use) are kept here for natural-prompt filtering but are
# promoted back to tokens at query time if the graph actually has a file
# containing that token — see `_graph_aware_stopwords()`.
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


def _graph_aware_stopwords(graph):
    """Return stopword set with code-y tokens that appear as filename
    parts promoted back to tokens. Keeps "test"/"file"/"find" etc. usable
    as search terms on repos that have `test_foo.py` or `file_guard.py`,
    while still filtering them on repos where they're pure chatter."""
    files = graph.get("files") or {}
    filename_toks = set()
    for fpath in files.keys():
        base = os.path.splitext(os.path.basename(fpath))[0].lower()
        for part in re.split(r"[_\-.]+", base):
            if len(part) >= 3:
                filename_toks.add(part)
    # Promote only a defined whitelist — don't silently un-stopword
    # anything lexically unusual; stick to the known code-verbs set.
    promotable = {"test", "tests", "file", "files", "find", "check",
                  "run", "code", "fix", "add", "make", "use", "show",
                  "create", "update", "delete", "change", "remove"}
    promoted = promotable & filename_toks
    return STOPWORDS - promoted


def _stem_variants(tok):
    """Produce plural ↔ singular variants for one token. Conservative:
    only handles the common English cases (s, es) and requires the base
    to be at least 4 chars so we never strip meaningful suffixes off
    short tokens like `is`, `as`, `os`. Returns a set *including* the
    input token."""
    low = tok.lower()
    out = {low}
    if len(low) >= 5 and low.endswith("ies"):
        out.add(low[:-3] + "y")                 # cookies -> cooky? no, but:
    if len(low) >= 5 and low.endswith("es"):
        out.add(low[:-2])                       # matches -> match
    if len(low) >= 4 and low.endswith("s") and not low.endswith("ss"):
        out.add(low[:-1])                       # sessions -> session
    # And the other direction — singular → plural — so "cookie" matches
    # "cookies" in a basename.
    if len(low) >= 4 and not low.endswith("s"):
        out.add(low + "s")
    return out


def extract_tokens(prompt, min_word, stopwords=STOPWORDS):
    tokens = set()
    # Whole words
    for w in WORD_RE.findall(prompt):
        if len(w) < min_word:
            continue
        low = w.lower()
        if low in stopwords:
            continue
        tokens.add(w)
        # Camel/snake sub-parts
        for part in CAMEL_SPLIT.split(w):
            if len(part) >= min_word and part.lower() not in stopwords:
                tokens.add(part)
    # Natural-language → code-term expansion. Only fires on explicit
    # whole-word hits — never on partial matches.
    expanded = set()
    lowered = {t.lower(): t for t in tokens}
    for word in re.findall(r"[A-Za-z]+", prompt.lower()):
        if word in EXPANSIONS:
            for syn in EXPANSIONS[word]:
                if syn not in lowered:
                    expanded.add(syn)
    # Plural/singular variants — so "cookies" in prompt matches `cookies.py`
    # *and* "cookie" in prompt matches `cookies.py`. Guarded to ≥4 char bases
    # so we don't coin nonsense (`is`→`i`, `as`→`a`). No cross-token
    # conflation: each variant is only added if it isn't already present.
    stems = set()
    for t in tokens | expanded:
        for v in _stem_variants(t):
            if v not in lowered and len(v) >= min_word:
                stems.add(v)
    return tokens | expanded | stems


def extract_paths(prompt):
    paths = set()
    for m in PATH_RE.findall(prompt):
        # skip URLs-ish and bare numbers
        if "://" in m or m.count(".") > 4:
            continue
        if len(m) >= 3:
            paths.add(m)
    return paths


def _ablate_set():
    v = os.environ.get("CONTEXT_OS_AUTOCONTEXT_ABLATE", "")
    return {s.strip() for s in v.split(",") if s.strip()}


def _file_path_tokens(fpath):
    """Tokens extracted from a single file path (path segments +
    basename camel/snake split). Used for IDF + multi-token coverage."""
    toks = set()
    low = fpath.lower()
    for seg in re.split(r"[/\\]+", low):
        base = os.path.splitext(seg)[0]
        for part in re.split(r"[_\-.]+", base):
            if len(part) >= 2:
                toks.add(part)
            for sub in re.findall(r"[a-z]+|[0-9]+", part):
                if len(sub) >= 2:
                    toks.add(sub)
    return toks


def _path_token_df(files):
    """Document frequency per path-token across the whole graph."""
    df = {}
    for fpath in files.keys():
        for t in _file_path_tokens(fpath):
            df[t] = df.get(t, 0) + 1
    return df


def _idf(df, token, N):
    """Dampened IDF capped at 1.6 so rare tokens lift but don't dominate
    exact symbol/path matches. Floor 1.0; disabled df produces 1.0."""
    n = df.get(token, 0)
    if n == 0:
        return 1.0
    raw = math.log((N + 1) / (n + 0.5))
    return max(1.0, min(1.6, raw / 2.0))


def _normalize_prompt_forms(prompt):
    """Return three normalizations used to detect whole-basename hits."""
    low = prompt.lower()
    under = re.sub(r"[^a-z0-9]+", "_", low).strip("_")
    space = re.sub(r"[^a-z0-9]+", " ", low).strip()
    none = re.sub(r"[^a-z0-9]+", "", low)
    return under, space, none


def rank(prompt, graph, max_hits, min_word):
    files = graph.get("files") or {}
    symbol_index = graph.get("symbol_index") or {}
    imported_by = graph.get("imported_by") or {}
    hot = {h.get("path"): h.get("touches", 0)
           for h in (graph.get("hot_files") or [])}

    off = _ablate_set()

    stopwords = _graph_aware_stopwords(graph)
    tokens = extract_tokens(prompt, min_word, stopwords)
    paths = extract_paths(prompt)

    # IDF over filename-tokens. Rare tokens get higher weight so
    # `robustness` (1 file) beats `auto` (many files) on path matches.
    N = max(1, len(files))
    # Prefer precomputed df from build_repo_graph.py (graph version ≥ 2).
    # Drops per-query O(N·tokens) scan, critical above ~10k files.
    path_df = graph.get("path_df")
    if not path_df:
        path_df = _path_token_df(files)

    def path_idf(tok):
        return _idf(path_df, tok.lower(), N)

    under, space, _none = _normalize_prompt_forms(prompt)

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

    # 1. Exact + case-insensitive symbol matches — IDF-weighted so rare
    #    symbols (e.g. `bootstrap_ci`) outrank common ones (`rank`, `main`).
    sym_lc = {k.lower(): k for k in symbol_index.keys()}
    for tok in tokens:
        if "symbol_exact" not in off and tok in symbol_index:
            idf = max(1.0, path_idf(tok))
            for loc in symbol_index[tok]:
                bump(loc["file"], loc["line"], loc.get("kind", ""),
                     tok, int(10 * idf),
                     f"symbol `{tok}`")
        elif "symbol_ci" not in off and tok.lower() in sym_lc:
            real = sym_lc[tok.lower()]
            idf = max(1.0, path_idf(tok))
            for loc in symbol_index[real]:
                bump(loc["file"], loc["line"], loc.get("kind", ""),
                     real, int(8 * idf),
                     f"symbol `{real}` (case-insensitive)")

    # 2a. Basename-in-prompt — strong signal. Matches `foo_bar.py` when
    #     prompt contains "foo_bar", "foo bar", or "foobar". Catches the
    #     realistic case ("the robustness_test suite", "file_size_guard
    #     hook") that plain path-substring misses on token boundaries.
    if "path_exact" not in off:
        for fpath in files.keys():
            base_root = os.path.splitext(os.path.basename(fpath))[0].lower()
            if len(base_root) < 5:
                continue
            base_under = re.sub(r"[^a-z0-9]+", "_", base_root).strip("_")
            base_space = re.sub(r"[^a-z0-9]+", " ", base_root).strip()
            if (base_under and base_under in under) or \
               (base_space and " " + base_space + " " in " " + space + " "):
                bump(fpath, 1, "file", os.path.basename(fpath),
                     15, f"basename `{base_root}` in prompt")

    # 2b. Path / substring in file keys — IDF-weighted so common tokens
    #     don't dominate. Two changes from v2.7:
    #     (a) Exact basename-root match (`sessions` matches basename of
    #         sessions.py) promoted to its own weight (+6), separate from
    #         general substring (+3). Catches the uniform-naming case where
    #         `request` is in every path but `sessions`-as-basename is
    #         the actual discriminator.
    #     (b) Substring bonus is scaled by discriminativity (1 − df/N).
    #         A token present in every file contributes ~0; a token in
    #         one file contributes ~full weight. Smooth, no hard cutoff.
    # Case-fold + dedupe before path matching. Prevents triple-counting
    # `Request`, `request`, `requests` (all the same concept) as three
    # independent bumps per file.
    path_tokens_seen = set()
    path_tokens_dedup = []
    for tok in list(tokens) + list(paths):
        tl = tok.lower()
        if tl in path_tokens_seen:
            continue
        path_tokens_seen.add(tl)
        path_tokens_dedup.append(tok)

    for tok in path_tokens_dedup:
        tl = tok.lower()
        tok_df = path_df.get(tl, 0) if path_df else 0
        # Discriminativity multiplier: 1.0 when unique, 0 when in all files.
        disc = max(0.0, 1.0 - (tok_df / float(N)))
        for fpath in files.keys():
            fl = fpath.lower()
            base = os.path.basename(fl)
            if (("path_exact" not in off) and
                    (fl == tl or fl.endswith("/" + tl)
                     or ("/" in tl and tl in fl))):
                bump(fpath, 1, "file", os.path.basename(fpath),
                     int(8 * max(1.0, path_idf(tok))),
                     f"path `{tok}`")
            elif ("path_substr" not in off) and len(tl) >= 4:
                base_root = os.path.splitext(base)[0]
                if base_root == tl:
                    # Exact basename match is always informative.
                    bump(fpath, 1, "file", os.path.basename(fpath),
                         int(6 * max(1.0, path_idf(tok))),
                         f"basename `{tok}`")
                elif tl in fl:
                    # Scale bonus by how discriminative this token is.
                    score = int(3 * max(1.0, path_idf(tok)) * disc)
                    if score > 0:
                        bump(fpath, 1, "file", os.path.basename(fpath),
                             score,
                             f"path contains `{tok}`")

    # 3. Import module matches — surface importers. Tight rule: only
    # fires when a prompt token exactly equals a module name or matches
    # its last path segment (so "login" matches `src.auth.login` but not
    # "auth" matching the whole `src.auth.session` module). Previous
    # substring form bumped importer files above real edit targets on
    # broad tokens; ablation showed MRR −0.047. Weight reduced 5→3.
    if "import" not in off:
        for tok in tokens:
            tl = tok.lower()
            for mod, importers in imported_by.items():
                ml = mod.lower()
                last = ml.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
                if tl == ml or tl == last:
                    for imp in importers[:3]:
                        bump(imp, 1, "importer", mod,
                             3, f"imports `{mod}`")

    # 3b. Multi-token coverage bonus — a file matching 3 distinct prompt
    #     tokens beats a file matching 1, even if individual match scores
    #     are similar. Caps at +8 to avoid dominating exact matches.
    if "path_substr" not in off and tokens:
        lowered_tokens = {t.lower() for t in tokens}
        for key, c in list(candidates.items()):
            fl = c["file"].lower()
            base_toks = _file_path_tokens(c["file"])
            hits = sum(1 for t in lowered_tokens
                       if t in base_toks or (len(t) >= 4 and t in fl))
            if hits >= 2:
                bonus = min(8, 2 * (hits - 1))
                c["score"] += bonus
                c["reasons"].append(f"{hits}-token path coverage")

    # 4. Hot-file boost
    if "hot" not in off:
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
    if "test_penalty" not in off and not mentions_tests:
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

    # 6. Hub-file penalty — re-export / gateway files (mod.rs, models.py,
    # __init__.py, index.ts) often host many symbols and get matched on
    # broad prompt tokens, bumping them above the real edit target. Only
    # penalize when the filename itself isn't named in the prompt.
    if "hub_penalty" not in off:
        hub_files = {"mod.rs", "models.py", "index.ts", "index.js",
                     "index.tsx", "index.jsx", "__init__.py", "lib.rs"}
        for key, c in candidates.items():
            base = os.path.basename(c["file"]).lower()
            if base in hub_files:
                mentioned = any(
                    base.split(".")[0] in prompt_low
                    or base in prompt_low
                    for _ in [0]
                )
                if not mentioned:
                    c["score"] -= 2
                    c["reasons"].append("hub-file penalty")

    # File-level score aggregation. A file with 3 different relevant
    # symbols (e.g. `Request`, `Response`, `PreparedRequest` all in
    # models.py) should outrank a file with 1 weak path-substring hit.
    # Previously the first line was ranked in isolation, so 3 symbol
    # hits at +10 each looked like three separate candidates instead
    # of one file scoring +30. We aggregate per file, take the
    # highest-scoring line as the representative, and rank files by
    # the summed score.
    per_file_score = {}
    per_file_best = {}
    for c in candidates.values():
        f = c["file"]
        per_file_score[f] = per_file_score.get(f, 0) + c["score"]
        cur_best = per_file_best.get(f)
        if cur_best is None or c["score"] > cur_best["score"]:
            per_file_best[f] = c

    # Build the output list: one representative candidate per file,
    # whose visible `score` is the aggregate. Ordered by aggregate desc.
    out = []
    for f in sorted(per_file_score.keys(),
                    key=lambda x: (-per_file_score[x], x)):
        rep = dict(per_file_best[f])
        rep["score"] = per_file_score[f]
        out.append(rep)
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
