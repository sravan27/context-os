#!/usr/bin/env python3
"""
baseline_comparison.py — auto_context vs multiple retrieval baselines.

We already compare against naive-filename. This runner adds:

  - `random` — uniformly random file ordering. Confirms the eval isn't
    trivially solvable.
  - `bm25-path` — Okapi BM25 over file paths + basenames (split into
    tokens). No external dep; pure-stdlib implementation.
  - `bm25-symbols` — BM25 over the union of symbol names per file. This
    tests whether richer lexical features close the gap.
  - `grep-count` — counts how often any prompt token appears inside the
    file's `(path, symbols)` — closest cheap baseline to what `grep` would
    surface.
  - `first-match` — top-1 reciprocal rank only (latency-free, the MRR of
    a "just open the first file that looks plausible" policy).

Each baseline is scored over the same 32 prompts × 3 fixtures as auto_context.
Report: `python/evals/reports/baseline-comparison.md`.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
from autocontext_eval import (                                   # noqa: E402
    PROMPTS, eval_fixture, aggregate, build_graph,
    precision_at_k, recall_at_k, reciprocal_rank,
    tokenize, TOKEN_RE, SRC_EXTS, K,
)

REPORT = os.path.join(REPO, "python", "evals", "reports",
                      "baseline-comparison.md")


# ------- graph/file inventory -------

def load_graph(fixture):
    path = os.path.join(fixture, ".context-os", "repo-graph.json")
    with open(path) as f:
        return json.load(f)


def file_list(graph):
    return list((graph.get("files") or {}).keys())


def file_symbols(graph):
    """Return dict: file -> set(symbol names)."""
    out = {}
    for sym, locs in (graph.get("symbol_index") or {}).items():
        for loc in locs:
            out.setdefault(loc["file"], set()).add(sym)
    return out


def split_terms(s):
    # break into lowercase terms, including camel/snake sub-parts
    terms = set()
    for w in TOKEN_RE.findall(s):
        lw = w.lower()
        if len(lw) < 2:
            continue
        terms.add(lw)
        # camel split
        for part in re.split(r"[_\-./\\]+", w):
            if len(part) >= 2:
                terms.add(part.lower())
        for part in re.findall(r"[a-z]+|[A-Z][a-z]*|[0-9]+", w):
            if len(part) >= 2:
                terms.add(part.lower())
    return terms


# ------- baselines -------

def baseline_random(prompt, fixture, rng):
    files = file_list(load_graph(fixture))
    rng.shuffle(files)
    return files


class BM25:
    """Okapi BM25. Stdlib only."""
    def __init__(self, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = {}         # docid -> term -> tf
        self.dl = {}           # docid -> doc length
        self.N = 0
        self.df = {}           # term -> doc freq
        self.avgdl = 0.0

    def add(self, docid, terms):
        tf = {}
        for t in terms:
            tf[t] = tf.get(t, 0) + 1
        self.docs[docid] = tf
        self.dl[docid] = sum(tf.values())
        for t in tf.keys():
            self.df[t] = self.df.get(t, 0) + 1
        self.N += 1

    def finalize(self):
        if self.N == 0:
            self.avgdl = 0.0
            return
        self.avgdl = sum(self.dl.values()) / self.N

    def score(self, docid, query_terms):
        tf = self.docs.get(docid, {})
        if not tf:
            return 0.0
        dl = self.dl.get(docid, 0) or 1
        s = 0.0
        for q in query_terms:
            f = tf.get(q, 0)
            if f == 0:
                continue
            df = self.df.get(q, 0)
            idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1)
            numer = f * (self.k1 + 1)
            denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            s += idf * numer / denom
        return s

    def topk(self, query_terms, k=None):
        results = [(d, self.score(d, query_terms)) for d in self.docs]
        results.sort(key=lambda x: (-x[1], x[0]))
        return [d for d, s in results if s > 0][:k] if k else [
            d for d, s in results if s > 0]


def baseline_bm25_path(prompt, fixture):
    graph = load_graph(fixture)
    files = file_list(graph)
    idx = BM25()
    for fp in files:
        idx.add(fp, list(split_terms(fp)))
    idx.finalize()
    return idx.topk(list(split_terms(prompt)))


def baseline_bm25_symbols(prompt, fixture):
    graph = load_graph(fixture)
    files = file_list(graph)
    fsym = file_symbols(graph)
    idx = BM25()
    for fp in files:
        terms = set(split_terms(fp))
        for s in fsym.get(fp, ()):
            terms.update(split_terms(s))
        idx.add(fp, list(terms))
    idx.finalize()
    return idx.topk(list(split_terms(prompt)))


def baseline_grep_count(prompt, fixture):
    """Score by raw term-in-text match count (path + symbols)."""
    graph = load_graph(fixture)
    files = file_list(graph)
    fsym = file_symbols(graph)
    q = list(split_terms(prompt))
    scored = []
    for fp in files:
        hay = fp.lower() + " " + " ".join(sym.lower()
                                          for sym in fsym.get(fp, ()))
        c = sum(hay.count(t) for t in q)
        if c > 0:
            scored.append((c, -len(fp), fp))
    scored.sort(reverse=True)
    return [f for _, _, f in scored]


BASELINES = {
    "random": ("Random shuffle (control — confirms eval is non-trivial)",
               lambda p, fx, rng: baseline_random(p, fx, rng)),
    "naive-filename": ("Filename-token overlap (already in main eval)",
                       None),  # handled via eval_fixture mode
    "bm25-path":
        ("BM25 over file path + basename tokens",
         lambda p, fx, rng: baseline_bm25_path(p, fx)),
    "bm25-symbols":
        ("BM25 over path + declared symbol names",
         lambda p, fx, rng: baseline_bm25_symbols(p, fx)),
    "grep-count":
        ("Raw term-occurrence count over (path, symbols)",
         lambda p, fx, rng: baseline_grep_count(p, fx)),
}


# ------- driver -------

def eval_prompts(fix_id, root, prompts, ranker):
    rng = random.Random(7)
    rows = []
    for p in prompts:
        predicted = ranker(p["prompt"], root, rng)
        expected = p["expected_files"]
        rows.append({
            "id": p["id"],
            "predicted": predicted,
            "p_at_k": precision_at_k(predicted, expected, K),
            "r_at_k": recall_at_k(predicted, expected, K),
            "rr": reciprocal_rank(predicted, expected),
        })
    n = len(rows) or 1
    return {
        "id": fix_id,
        "n": len(rows),
        "precision_at_k": sum(r["p_at_k"] for r in rows) / n,
        "recall_at_k": sum(r["r_at_k"] for r in rows) / n,
        "mrr": sum(r["rr"] for r in rows) / n,
        "coverage": sum(1 for r in rows if r["predicted"]) / n,
        "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    with open(PROMPTS) as f:
        cfg = json.load(f)
    fixtures = cfg.get("fixtures") or []
    prompts_by_fix = cfg.get("prompts") or {}

    # Build graphs once
    for fx in fixtures:
        root = os.path.join(REPO, fx["root"])
        build_graph(root)

    # Run auto_context (all signals on)
    ac_per = []
    for fx in fixtures:
        fx_id = fx["id"]
        root = os.path.join(REPO, fx["root"])
        prompts = prompts_by_fix.get(fx_id) or []
        if not prompts:
            continue
        ac_per.append(eval_fixture(fx_id, root, prompts, "auto_context"))
    ac_agg = aggregate(ac_per)

    # Run naive-filename via eval_fixture
    nf_per = []
    for fx in fixtures:
        fx_id = fx["id"]
        root = os.path.join(REPO, fx["root"])
        prompts = prompts_by_fix.get(fx_id) or []
        if not prompts:
            continue
        nf_per.append(eval_fixture(fx_id, root, prompts, "naive-filename"))
    nf_agg = aggregate(nf_per)

    # Run each new baseline
    baseline_results = {
        "auto_context": {"per": ac_per, "agg": ac_agg,
                         "desc": "Context-OS auto_context hook (full ranker)"},
        "naive-filename": {
            "per": nf_per, "agg": nf_agg,
            "desc": BASELINES["naive-filename"][0],
        },
    }
    for name, (desc, ranker) in BASELINES.items():
        if ranker is None:
            continue
        per = []
        for fx in fixtures:
            fx_id = fx["id"]
            root = os.path.join(REPO, fx["root"])
            prompts = prompts_by_fix.get(fx_id) or []
            if not prompts:
                continue
            per.append(eval_prompts(fx_id, root, prompts, ranker))
        agg = aggregate(per)
        baseline_results[name] = {"per": per, "agg": agg, "desc": desc}

    gen = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Report
    lines = []
    a = lines.append
    a("# auto_context vs retrieval baselines")
    a("")
    a(f"_Generated {gen} · same 32 prompts × 3 fixtures as main eval_")
    a("")
    a("## Headline ranking")
    a("")
    a("| Retrieval method | P@3 | R@3 | MRR | Coverage |")
    a("|---|---:|---:|---:|---:|")
    order = ["auto_context", "bm25-symbols", "bm25-path", "grep-count",
             "naive-filename", "random"]
    for name in order:
        if name not in baseline_results:
            continue
        r = baseline_results[name]["agg"]
        marker = "**" if name == "auto_context" else ""
        a(f"| {marker}{name}{marker} | {marker}{r['precision_at_k']:.3f}"
          f"{marker} | {r['recall_at_k']:.3f} | "
          f"{marker}{r['mrr']:.3f}{marker} | {r['coverage']:.3f} |")
    a("")
    a("## Lift over each baseline")
    a("")
    ac = baseline_results["auto_context"]["agg"]
    a("| Baseline | auto_context P@3 | baseline P@3 | ΔP@3 | auto_context MRR "
      "| baseline MRR | ΔMRR |")
    a("|---|---:|---:|---:|---:|---:|---:|")
    for name in order[1:]:
        if name not in baseline_results:
            continue
        b = baseline_results[name]["agg"]
        dp = ac["precision_at_k"] - b["precision_at_k"]
        dm = ac["mrr"] - b["mrr"]
        a(f"| {name} | {ac['precision_at_k']:.3f} | {b['precision_at_k']:.3f}"
          f" | **{dp:+.3f}** | {ac['mrr']:.3f} | {b['mrr']:.3f} "
          f"| **{dm:+.3f}** |")
    a("")
    a("## Per-baseline notes")
    a("")
    for name in order:
        if name not in baseline_results:
            continue
        br = baseline_results[name]
        a(f"### `{name}`")
        a("")
        a(br["desc"])
        a("")
        a("| Fixture | P@3 | R@3 | MRR | Coverage |")
        a("|---|---:|---:|---:|---:|")
        for f in br["per"]:
            a(f"| {f['id']} | {f['precision_at_k']:.3f} | "
              f"{f['recall_at_k']:.3f} | {f['mrr']:.3f} | "
              f"{f['coverage']:.3f} |")
        a("")
    a("## Why this matters")
    a("")
    a("BM25 is the *textbook* lexical baseline — it's what Elasticsearch and "
      "Lucene use for lexical search by default. If auto_context beats "
      "BM25 on the same lexical inputs, it's the import-graph traversal +")
    a("hot-file signal + test/hub penalty doing the extra work. That's")
    a("the claim to defend.")
    a("")
    a("## Reproduce")
    a("")
    a("```bash")
    a("python3 python/evals/runners/baseline_comparison.py")
    a("```")
    a("")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {REPORT}")
    for name in order:
        if name not in baseline_results:
            continue
        r = baseline_results[name]["agg"]
        print(f"  {name:18s} P@3={r['precision_at_k']:.3f} "
              f"MRR={r['mrr']:.3f}")
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump({"generated_at": gen,
                       "results": {k: {"agg": v["agg"],
                                       "desc": v["desc"]}
                                   for k, v in baseline_results.items()}},
                      f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
