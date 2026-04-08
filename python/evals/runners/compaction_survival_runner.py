from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.evals.scorers.compaction_survival import score_compaction_case


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Context OS compaction-survival benchmarks")
    parser.add_argument(
        "--dataset",
        default="python/evals/datasets/compaction_survival_cases.json",
        help="Path to the compaction-survival dataset manifest",
    )
    parser.add_argument(
        "--output-prefix",
        default="python/evals/reports/compaction-survival-report",
        help="Output prefix for JSON and Markdown reports",
    )
    args = parser.parse_args()

    root = ROOT
    dataset_path = root / args.dataset
    output_prefix = root / args.output_prefix
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    cases = json.loads(dataset_path.read_text())
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    for case in cases:
        with TemporaryDirectory(prefix="context-os-compaction-") as temp_dir:
            temp_root = Path(temp_dir)
            context_dir = temp_root / ".context-os"
            context_dir.mkdir(parents=True, exist_ok=True)
            (context_dir / "session.json").write_text(json.dumps(case["state"], indent=2))
            (context_dir / "journal.jsonl").write_text("")

            output = run_cli(
                root,
                [
                    "cargo",
                    "run",
                    "-p",
                    "context-os",
                    "--quiet",
                    "--",
                    "resume",
                    "--root",
                    str(temp_root),
                    "--max-tokens",
                    str(case["max_tokens"]),
                ],
                parse_json=False,
            )
            packet_path = temp_root / "restart-packet.txt"
            packet_path.write_text(output)
            estimate = run_cli(
                root,
                [
                    "cargo",
                    "run",
                    "-p",
                    "context-os",
                    "--quiet",
                    "--",
                    "estimate",
                    "--input",
                    str(packet_path),
                    "--model",
                    "claude",
                ],
                parse_json=True,
            )

        score = score_compaction_case(
            case["name"],
            case,
            output,
            int(estimate["estimated_tokens"]),
        )
        result = {
            "name": score.name,
            "decision_retention": score.decision_retention,
            "failed_approach_retention": score.failed_approach_retention,
            "modified_file_retention": score.modified_file_retention,
            "next_step_retention": score.next_step_retention,
            "pinned_fact_retention": score.pinned_fact_retention,
            "current_subtask_retention": score.current_subtask_retention,
            "latest_decision_retention": score.latest_decision_retention,
            "packet_tokens": score.packet_tokens,
            "passed": score.passed,
        }
        results.append(result)
        if not score.passed:
            failures.append(case["name"])

    report = {
        "benchmark": "compaction_survival",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path.relative_to(root)),
        "summary": {
            "total_cases": len(cases),
            "passed_cases": len(cases) - len(failures),
            "failed_cases": failures,
            "average_decision_retention": average(
                item["decision_retention"] for item in results
            ),
            "average_failed_approach_retention": average(
                item["failed_approach_retention"] for item in results
            ),
            "average_modified_file_retention": average(
                item["modified_file_retention"] for item in results
            ),
            "average_next_step_retention": average(
                item["next_step_retention"] for item in results
            ),
            "average_packet_tokens": average(item["packet_tokens"] for item in results),
        },
        "cases": results,
        "gates": {
            "pinned_fact_retention": "1.0 required",
            "current_subtask_retention": "1.0 required",
            "latest_decision_retention": "1.0 required",
            "modified_file_retention": "1.0 required",
            "packet_tokens": "must stay within the per-case max_tokens budget",
        },
    }

    json_path = output_prefix.with_suffix(".json")
    md_path = output_prefix.with_suffix(".md")
    json_path.write_text(json.dumps(report, indent=2))
    md_path.write_text(render_markdown(report))

    print(
        json.dumps(
            {"json": str(json_path), "markdown": str(md_path), "summary": report["summary"]},
            indent=2,
        )
    )


def run_cli(root: Path, command: list[str], parse_json: bool) -> Any:
    completed = subprocess.run(
        command,
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    if parse_json:
        return json.loads(completed.stdout)
    return completed.stdout


def average(values) -> float:
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Compaction Survival Benchmark Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Dataset: `{report['dataset']}`",
        f"- Passed cases: `{report['summary']['passed_cases']}/{report['summary']['total_cases']}`",
        "",
        "| Case | Decision | Failed | Files | Next | Pinned | Subtask | Latest | Tokens | Passed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["cases"]:
        lines.append(
            f"| {item['name']} | {item['decision_retention']:.2f} | {item['failed_approach_retention']:.2f} | {item['modified_file_retention']:.2f} | {item['next_step_retention']:.2f} | {item['pinned_fact_retention']:.2f} | {item['current_subtask_retention']:.2f} | {item['latest_decision_retention']:.2f} | {item['packet_tokens']} | {'yes' if item['passed'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"- Pinned fact retention: {report['gates']['pinned_fact_retention']}",
            f"- Current subtask retention: {report['gates']['current_subtask_retention']}",
            f"- Latest decision retention: {report['gates']['latest_decision_retention']}",
            f"- Modified file retention: {report['gates']['modified_file_retention']}",
            f"- Packet token budget: {report['gates']['packet_tokens']}",
        ]
    )

    if report["summary"]["failed_cases"]:
        lines.extend(["", "## Failures", ""])
        for item in report["summary"]["failed_cases"]:
            lines.append(f"- `{item}`")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
