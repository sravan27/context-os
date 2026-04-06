from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ReducerScore:
    name: str
    protected_string_recall: float
    reduction_pct: float
    before_tokens: int
    after_tokens: int
    transformed: bool
    passed: bool


@dataclass
class PromptLintScore:
    name: str
    finding_recall: float
    finding_count: int
    passed: bool


def score_reducer_case(name: str, response: dict[str, Any], protected_strings: list[str]) -> ReducerScore:
    output = response["output"]
    metadata = response["metadata"]
    matched = sum(1 for item in protected_strings if item in output)
    recall = matched / len(protected_strings) if protected_strings else 1.0
    before_tokens = int(metadata["before_tokens"])
    after_tokens = int(metadata["after_tokens"])
    reduction_pct = (
        ((before_tokens - after_tokens) / before_tokens) * 100 if before_tokens else 0.0
    )
    transformed = bool(metadata["transformed"])
    passed = recall == 1.0 and (not transformed or after_tokens <= before_tokens)
    return ReducerScore(
        name=name,
        protected_string_recall=recall,
        reduction_pct=reduction_pct,
        before_tokens=before_tokens,
        after_tokens=after_tokens,
        transformed=transformed,
        passed=passed,
    )


def score_prompt_lint_case(name: str, response: dict[str, Any], expected_findings: list[str]) -> PromptLintScore:
    found = {item["code"] for item in response["findings"]}
    matched = sum(1 for item in expected_findings if item in found)
    recall = matched / len(expected_findings) if expected_findings else 1.0
    passed = recall == 1.0 and response["suggestion"]["rewrite"].strip() != ""
    return PromptLintScore(
        name=name,
        finding_recall=recall,
        finding_count=len(response["findings"]),
        passed=passed,
    )
