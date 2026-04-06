from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.evals.scorers.safe_mode import score_prompt_lint_case, score_reducer_case


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Context OS safe-mode benchmarks")
    parser.add_argument(
        "--dataset",
        default="python/evals/datasets/safe_mode_cases.json",
        help="Path to the benchmark dataset manifest",
    )
    parser.add_argument(
        "--output-prefix",
        default="python/evals/reports/safe-mode-report",
        help="Output prefix for JSON and Markdown reports",
    )
    args = parser.parse_args()

    root = ROOT
    dataset_path = root / args.dataset
    output_prefix = root / args.output_prefix
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    cases = json.loads(dataset_path.read_text())
    reducer_results: list[dict[str, Any]] = []
    prompt_results: list[dict[str, Any]] = []
    failures: list[str] = []

    for case in cases:
        if case["type"] == "reducer":
            response = run_cli(
                root,
                [
                    "cargo",
                    "run",
                    "-p",
                    "context-os",
                    "--quiet",
                    "--",
                    "reduce",
                    "--kind",
                    case["reducer_kind"],
                    "--input",
                    case["input"],
                    "--mode",
                    "safe",
                ],
            )
            score = score_reducer_case(case["name"], response, case["protected_strings"])
            reducer_results.append(
                {
                    "name": score.name,
                    "protected_string_recall": score.protected_string_recall,
                    "reduction_pct": score.reduction_pct,
                    "before_tokens": score.before_tokens,
                    "after_tokens": score.after_tokens,
                    "transformed": score.transformed,
                    "passed": score.passed,
                }
            )
            if not score.passed:
                failures.append(case["name"])
        elif case["type"] == "prompt_lint":
            response = run_cli(
                root,
                [
                    "cargo",
                    "run",
                    "-p",
                    "context-os",
                    "--quiet",
                    "--",
                    "prompt-lint",
                    "--input",
                    case["input"],
                ],
            )
            score = score_prompt_lint_case(case["name"], response, case["expected_findings"])
            prompt_results.append(
                {
                    "name": score.name,
                    "finding_recall": score.finding_recall,
                    "finding_count": score.finding_count,
                    "passed": score.passed,
                }
            )
            if not score.passed:
                failures.append(case["name"])
        else:
            raise ValueError(f"unsupported case type: {case['type']}")

    report = {
        "benchmark": "safe_mode",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path.relative_to(root)),
        "summary": {
            "total_cases": len(cases),
            "passed_cases": len(cases) - len(failures),
            "failed_cases": failures,
            "reducer_case_count": len(reducer_results),
            "prompt_case_count": len(prompt_results),
            "average_reducer_recall": average(
                item["protected_string_recall"] for item in reducer_results
            ),
            "average_reduction_pct": average(item["reduction_pct"] for item in reducer_results),
            "average_prompt_finding_recall": average(
                item["finding_recall"] for item in prompt_results
            ),
        },
        "reducers": reducer_results,
        "prompt_linter": prompt_results,
        "gates": {
            "safe_mode_protected_string_recall": "1.0 required",
            "safe_mode_prompt_finding_recall": "1.0 required for expected benchmark findings",
            "transformed_safe_mode_cases": "after_tokens must be <= before_tokens",
        },
    }

    json_path = output_prefix.with_suffix(".json")
    md_path = output_prefix.with_suffix(".md")
    json_path.write_text(json.dumps(report, indent=2))
    md_path.write_text(render_markdown(report))

    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "summary": report["summary"]}, indent=2))


def run_cli(root: Path, command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def average(values) -> float:
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Safe Mode Benchmark Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Dataset: `{report['dataset']}`",
        f"- Passed cases: `{report['summary']['passed_cases']}/{report['summary']['total_cases']}`",
        "",
        "## Reducer Results",
        "",
        "| Case | Recall | Reduction % | Before | After | Passed |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["reducers"]:
        lines.append(
            f"| {item['name']} | {item['protected_string_recall']:.2f} | {item['reduction_pct']:.2f} | {item['before_tokens']} | {item['after_tokens']} | {'yes' if item['passed'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Prompt Linter Results",
            "",
            "| Case | Finding Recall | Findings | Passed |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for item in report["prompt_linter"]:
        lines.append(
            f"| {item['name']} | {item['finding_recall']:.2f} | {item['finding_count']} | {'yes' if item['passed'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"- Safe reducer protected-string recall: {report['gates']['safe_mode_protected_string_recall']}",
            f"- Prompt-linter finding recall: {report['gates']['safe_mode_prompt_finding_recall']}",
            f"- Safe transformed reducer token behavior: {report['gates']['transformed_safe_mode_cases']}",
        ]
    )

    if report["summary"]["failed_cases"]:
        lines.extend(["", "## Failures", ""])
        for item in report["summary"]["failed_cases"]:
            lines.append(f"- `{item}`")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
