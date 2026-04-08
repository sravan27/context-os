from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompactionScore:
    name: str
    decision_retention: float
    failed_approach_retention: float
    modified_file_retention: float
    next_step_retention: float
    pinned_fact_retention: float
    current_subtask_retention: float
    latest_decision_retention: float
    packet_tokens: int
    passed: bool


def score_compaction_case(name: str, case: dict, output: str, packet_tokens: int) -> CompactionScore:
    required = case["required"]

    def recall(items: list[str]) -> float:
        if not items:
            return 1.0
        matched = sum(1 for item in items if item in output)
        return matched / len(items)

    current_subtask = required.get("current_subtask", "")
    latest_decision = required.get("latest_decision", "")

    decision_retention = recall(required.get("decisions", []))
    failed_approach_retention = recall(required.get("failed_approaches", []))
    modified_file_retention = recall(required.get("modified_files", []))
    next_step_retention = recall(required.get("next_actions", []))
    pinned_fact_retention = recall(required.get("pinned_facts", []))
    current_subtask_retention = 1.0 if not current_subtask or current_subtask in output else 0.0
    latest_decision_retention = 1.0 if not latest_decision or latest_decision in output else 0.0

    passed = (
        pinned_fact_retention == 1.0
        and current_subtask_retention == 1.0
        and latest_decision_retention == 1.0
        and modified_file_retention == 1.0
        and packet_tokens <= int(case["max_tokens"])
    )

    return CompactionScore(
        name=name,
        decision_retention=decision_retention,
        failed_approach_retention=failed_approach_retention,
        modified_file_retention=modified_file_retention,
        next_step_retention=next_step_retention,
        pinned_fact_retention=pinned_fact_retention,
        current_subtask_retention=current_subtask_retention,
        latest_decision_retention=latest_decision_retention,
        packet_tokens=packet_tokens,
        passed=passed,
    )
