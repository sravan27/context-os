#!/usr/bin/env python3
"""
agent_cost_leak_check.py - local repo scan for coding-agent cost-leak signals.

This is the private-repo companion to the public checker page. It does not
estimate a dollar bill; it flags repository shapes that tend to make coding
agents burn context on repeated exploration, generated files, missing guidance,
and unclear validation paths.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


SOURCE_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".py", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".cs", ".c", ".cc", ".cpp", ".h", ".hpp", ".swift",
    ".scala", ".ex", ".exs", ".clj",
}
DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt", ".adoc"}
TEST_HINTS = ("/test/", "/tests/", "/spec/", "__tests__", ".test.", ".spec.")
GENERATED_HINTS = (
    "/dist/", "/build/", "/coverage/", "/vendor/", "/generated/",
    "/fixtures/", "/snapshots/", "package-lock.json", "yarn.lock",
    "pnpm-lock.yaml", "bun.lockb", "poetry.lock", "Cargo.lock",
)
AI_CONFIGS = (
    "CLAUDE.md", ".claudeignore", ".claude/settings.json", ".cursor/rules",
    ".github/copilot-instructions.md", "AGENTS.md",
)
EVAL_HINTS = ("/eval", "/bench", "benchmark", "pytest", "vitest", "jest",
              "playwright", "cypress")
WALK_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    ".mypy_cache", ".pytest_cache", "target",
}


@dataclass
class FileInfo:
    path: str
    size: int


@dataclass
class Finding:
    title: str
    detail: str
    points: int


def git_files(repo: Path) -> List[FileInfo] | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    files: List[FileInfo] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="replace")
        path = repo / rel
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        files.append(FileInfo(rel.replace(os.sep, "/"), size))
    return files


def walked_files(repo: Path) -> List[FileInfo]:
    files: List[FileInfo] = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in WALK_SKIP_DIRS]
        for name in names:
            path = Path(root) / name
            try:
                rel = path.relative_to(repo).as_posix()
                size = path.stat().st_size
            except OSError:
                continue
            files.append(FileInfo(rel, size))
    return files


def load_files(repo: Path) -> List[FileInfo]:
    return git_files(repo) or walked_files(repo)


def extension(path: str) -> str:
    return Path(path).suffix.lower()


def includes_any(path: str, needles: Iterable[str]) -> bool:
    normalized = "/" + path.lower()
    return any(needle.lower() in normalized for needle in needles)


def analyze(repo: Path, files: List[FileInfo]) -> dict:
    paths = [f.path for f in files]
    lower_paths = {p.lower() for p in paths}
    extensions: dict[str, int] = {}
    source_files = doc_files = test_files = generated_files = 0
    large_files = total_bytes = eval_signals = 0

    for item in files:
        lower = item.path.lower()
        ext = extension(lower)
        if ext in SOURCE_EXTENSIONS:
            source_files += 1
        if ext in DOC_EXTENSIONS:
            doc_files += 1
        if includes_any(lower, TEST_HINTS):
            test_files += 1
        if includes_any(lower, GENERATED_HINTS):
            generated_files += 1
        if item.size > 180_000:
            large_files += 1
        if includes_any(lower, EVAL_HINTS):
            eval_signals += 1
        total_bytes += item.size
        if ext:
            extensions[ext] = extensions.get(ext, 0) + 1

    def has(target: str) -> bool:
        return target.lower() in lower_paths

    has_agent_instructions = (
        has("CLAUDE.md") or has("AGENTS.md") or
        has(".github/copilot-instructions.md")
    )
    has_agent_ignore = has(".claudeignore") or has(".cursorignore") or has(".aiderignore")
    ai_config_count = sum(1 for target in AI_CONFIGS if has(target))
    language_count = sum(1 for ext in extensions if ext in SOURCE_EXTENSIONS)

    findings: List[Finding] = []
    score = 0

    def add(condition: bool, points: int, title: str, detail: str) -> None:
        nonlocal score
        if not condition:
            return
        score += points
        findings.append(Finding(title, detail, points))

    add(not has_agent_instructions, 18, "No agent instruction file found",
        "Add CLAUDE.md, AGENTS.md, or equivalent guidance with architecture, commands, and constraints.")
    add(not has_agent_ignore, 18, "No agent ignore file found",
        "Add .claudeignore, .cursorignore, or equivalent rules for generated files, lockfiles, snapshots, and large fixtures.")
    add(generated_files > max(8, int(source_files * 0.12)), 16,
        "Generated or lockfile noise is visible",
        f"{generated_files} generated, build, lock, vendor, or fixture-like files may be low-signal reads.")
    add(large_files > 8, 14, "Large tracked blobs increase read risk",
        f"{large_files} files are larger than 180 KB and can waste context if agents open them during exploration.")
    add(source_files > 1600, 12, "Large source tree needs a repo map",
        f"{source_files} source files detected. Static file/symbol hints can reduce blind grep/read loops.")
    add(doc_files < max(3, int(source_files * 0.015)), 10,
        "Low docs-to-code signal",
        f"{doc_files} doc files for {source_files} source files. Agents may need compact architecture notes.")
    add(test_files == 0 and source_files > 40, 8, "No obvious test surface",
        "No obvious test/spec paths were found. Agents need a clear validation route.")
    add(language_count >= 5, 8, "Multi-language repo shape",
        f"{language_count} source extension families found. Add per-language ownership notes or a generated repo graph.")
    add(eval_signals == 0, 8, "No eval or benchmark signal",
        "No obvious eval/benchmark harness was detected. Agent changes are cheaper when success checks are explicit.")

    if not findings:
        findings.append(Finding(
            "Low public-surface leak signal",
            "Repo has guidance, manageable file counts, and visible validation signals. Inspect real agent transcripts for deeper waste.",
            0,
        ))

    score = min(score, 100)
    top_extensions = sorted(extensions.items(), key=lambda kv: kv[1], reverse=True)[:5]
    summary = (
        "High leak risk. Add ignore rules, a repo map, and explicit agent workflow constraints."
        if score >= 70 else
        "Moderate leak risk. A focused cleanup is worth doing before scaling agent usage."
        if score >= 38 else
        "Lower public-surface risk. Measure real agent transcripts and task flows next."
    )

    return {
        "repo": str(repo),
        "score": score,
        "summary": summary,
        "metrics": {
            "files": len(files),
            "source_files": source_files,
            "doc_files": doc_files,
            "test_files": test_files,
            "generated_or_lock_files": generated_files,
            "large_files": large_files,
            "ai_config_hits": ai_config_count,
            "language_families": language_count,
            "size_mb": round(total_bytes / (1024 * 1024), 2),
            "top_extensions": top_extensions,
        },
        "findings": [finding.__dict__ for finding in findings],
    }


def render_markdown(report: dict) -> str:
    lines = [
        f"# AI Agent Cost Leak Check: {report['repo']}",
        "",
        f"Score: **{report['score']}/100**",
        "",
        report["summary"],
        "",
        "## Metrics",
        "",
    ]
    for key, value in report["metrics"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Findings", ""])
    for finding in report["findings"]:
        lines.append(f"- **{finding['title']}** (+{finding['points']}): {finding['detail']}")
    lines.extend([
        "",
        "Private audit: https://sravan27.github.io/money-27-proof/agent-cost-leak-audit.html",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan a local repo for coding-agent cost-leak signals.",
    )
    parser.add_argument("--repo", default=".", help="Path to the repository to scan.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    args = parser.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve()
    if not repo.exists():
        print(f"repo does not exist: {repo}", file=sys.stderr)
        return 2

    report = analyze(repo, load_files(repo))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
