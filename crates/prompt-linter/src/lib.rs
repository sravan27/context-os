use regex::Regex;
use serde::{Deserialize, Serialize};
use token_estimator::{estimate_text, ModelFamily};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Low,
    Medium,
    High,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum WasteSource {
    Redundancy,
    Overbreadth,
    Ambiguity,
    MissingAcceptanceCriteria,
    MissingScope,
    BuriedStaticContext,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LintFinding {
    pub code: String,
    pub severity: Severity,
    pub waste_source: WasteSource,
    pub message: String,
    pub estimated_waste_tokens: u32,
    pub evidence: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StructuredPromptSuggestion {
    pub objective: String,
    pub scope: String,
    pub constraints: Vec<String>,
    pub relevant_files: Vec<String>,
    pub deliverable: String,
    pub acceptance_criteria: Vec<String>,
    pub rewrite: String,
    pub diff: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PromptLintReport {
    pub findings: Vec<LintFinding>,
    pub summary: String,
    pub suggestion: StructuredPromptSuggestion,
}

pub fn analyze_prompt(input: &str) -> PromptLintReport {
    let findings = collect_findings(input);
    let suggestion = build_suggestion(input, &findings);
    let summary = if findings.is_empty() {
        "Prompt looks reasonably scoped and already structured.".to_string()
    } else {
        format!(
            "{} findings detected across redundancy, scoping, and objective clarity.",
            findings.len()
        )
    };

    PromptLintReport {
        findings,
        summary,
        suggestion,
    }
}

fn collect_findings(input: &str) -> Vec<LintFinding> {
    let mut findings = Vec::new();
    let non_empty_lines: Vec<String> = input
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect();
    let paths = extract_paths(input);
    let lower = input.to_lowercase();

    let duplicate_lines = duplicate_lines(&non_empty_lines);
    if !duplicate_lines.is_empty() {
        let duplicate_text = duplicate_lines.join("\n");
        findings.push(LintFinding {
            code: "redundant_constraints".to_string(),
            severity: Severity::Medium,
            waste_source: WasteSource::Redundancy,
            message:
                "Repeated lines or constraints add token cost without adding new instruction value."
                    .to_string(),
            estimated_waste_tokens: estimate_text(&duplicate_text, ModelFamily::Claude)
                .estimated_tokens,
            evidence: duplicate_lines,
        });
    }

    let overbroad_markers = [
        "entire repo",
        "whole repo",
        "entire codebase",
        "whole codebase",
        "all files",
        "everything",
    ];
    let overbroad_hits: Vec<String> = overbroad_markers
        .iter()
        .filter(|marker| lower.contains(**marker))
        .map(|marker| marker.to_string())
        .collect();
    if !overbroad_hits.is_empty() {
        findings.push(LintFinding {
            code: "overbroad_scope".to_string(),
            severity: Severity::High,
            waste_source: WasteSource::Overbreadth,
            message: "The prompt asks for repo-wide work without narrowing the active scope."
                .to_string(),
            estimated_waste_tokens: 60,
            evidence: overbroad_hits,
        });
    }

    if paths.is_empty()
        && (lower.contains("repo") || lower.contains("codebase") || lower.contains("project"))
    {
        findings.push(LintFinding {
            code: "missing_file_scope".to_string(),
            severity: Severity::Medium,
            waste_source: WasteSource::MissingScope,
            message: "The prompt references a repository but does not identify relevant files or modules.".to_string(),
            estimated_waste_tokens: 35,
            evidence: vec!["No file or module paths detected".to_string()],
        });
    }

    let action_regex = Regex::new(r"\b(build|implement|fix|debug|add|update|refactor|review|document|scaffold|reduce|write|investigate)\b")
        .expect("valid regex");
    if !action_regex.is_match(&lower) {
        findings.push(LintFinding {
            code: "ambiguous_objective".to_string(),
            severity: Severity::Medium,
            waste_source: WasteSource::Ambiguity,
            message: "The prompt does not state a clear action verb or deliverable.".to_string(),
            estimated_waste_tokens: 25,
            evidence: vec![first_non_empty_line(input).unwrap_or_default()],
        });
    }

    let success_markers = [
        "acceptance criteria",
        "done when",
        "verify",
        "test",
        "tests",
        "success criteria",
        "must pass",
    ];
    if !success_markers.iter().any(|marker| lower.contains(marker)) {
        findings.push(LintFinding {
            code: "missing_acceptance_criteria".to_string(),
            severity: Severity::Medium,
            waste_source: WasteSource::MissingAcceptanceCriteria,
            message: "The prompt does not define how success should be verified.".to_string(),
            estimated_waste_tokens: 30,
            evidence: vec!["No explicit verification or acceptance language detected".to_string()],
        });
    }

    let static_context_markers = [
        "mission",
        "product thesis",
        "hard requirements",
        "non-negotiable",
    ];
    let static_hits: Vec<String> = static_context_markers
        .iter()
        .filter(|marker| lower.contains(**marker))
        .map(|marker| marker.to_string())
        .collect();
    if static_hits.len() >= 2 && non_empty_lines.len() > 12 {
        findings.push(LintFinding {
            code: "buried_static_context".to_string(),
            severity: Severity::Low,
            waste_source: WasteSource::BuriedStaticContext,
            message: "Long-lived project context appears inline and may be better pinned or compiled into repo memory.".to_string(),
            estimated_waste_tokens: 45,
            evidence: static_hits,
        });
    }

    findings
}

fn build_suggestion(input: &str, findings: &[LintFinding]) -> StructuredPromptSuggestion {
    let paths = extract_paths(input);
    let objective = infer_objective(input);
    let constraints = extract_constraints(input);
    let scope = if paths.is_empty() {
        "Narrow the task to the specific files, modules, or subsystems that need to change."
            .to_string()
    } else {
        format!("Focus on: {}", paths.join(", "))
    };

    let deliverable = infer_deliverable(input);
    let acceptance_criteria = infer_acceptance_criteria(input);
    let rewrite = format!(
        "Objective\n{}\n\nScope\n{}\n\nConstraints\n{}\n\nRelevant Files or Modules\n{}\n\nDeliverable\n{}\n\nAcceptance Criteria\n{}",
        objective,
        scope,
        render_list_or_placeholder(&constraints, "- Add constraints only if they materially change execution."),
        render_list_or_placeholder(&paths, "- Add file or module paths when known."),
        deliverable,
        render_list_or_placeholder(&acceptance_criteria, "- Define how success will be verified.")
    );

    let original_preview = input
        .lines()
        .take(8)
        .map(|line| format!("- {}", line.trim()))
        .collect::<Vec<_>>()
        .join("\n");
    let rewrite_preview = rewrite
        .lines()
        .take(12)
        .map(|line| format!("+ {line}"))
        .collect::<Vec<_>>()
        .join("\n");

    let diff = if findings.is_empty() {
        format!("+ {}", rewrite.replace('\n', "\n+ "))
    } else {
        format!("{original_preview}\n{rewrite_preview}")
    };

    StructuredPromptSuggestion {
        objective,
        scope,
        constraints,
        relevant_files: paths,
        deliverable,
        acceptance_criteria,
        rewrite,
        diff,
    }
}

fn duplicate_lines(lines: &[String]) -> Vec<String> {
    let mut duplicates = Vec::new();
    for line in lines {
        let count = lines.iter().filter(|candidate| *candidate == line).count();
        if count > 1 && !duplicates.contains(line) {
            duplicates.push(line.clone());
        }
    }
    duplicates
}

fn extract_paths(input: &str) -> Vec<String> {
    let regex = Regex::new(
        r"(?x)
        (?:
          (?:\./|\.\./|/)[A-Za-z0-9_\-./]+
          |
          (?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+
        )",
    )
    .expect("valid regex");

    let mut paths = Vec::new();
    for capture in regex.find_iter(input) {
        let value = capture
            .as_str()
            .trim_matches(|ch| ch == ',' || ch == '.')
            .to_string();
        if !paths.contains(&value) {
            paths.push(value);
        }
    }
    paths
}

fn extract_constraints(input: &str) -> Vec<String> {
    let mut constraints = Vec::new();
    for line in input.lines().map(str::trim) {
        if line.is_empty() {
            continue;
        }
        if line.starts_with('-')
            || line.contains("must")
            || line.contains("Must")
            || line.contains("do not")
            || line.contains("Do not")
            || line.contains("never")
            || line.contains("Never")
        {
            let normalized = line.trim_start_matches("- ").to_string();
            if !constraints.contains(&normalized) {
                constraints.push(normalized);
            }
        }
    }
    constraints.truncate(8);
    constraints
}

fn infer_objective(input: &str) -> String {
    for line in input.lines().map(str::trim) {
        if line.is_empty() {
            continue;
        }
        if Regex::new(r"(?i)\b(build|implement|fix|debug|add|update|refactor|review|document|scaffold|reduce|write|investigate)\b")
            .expect("valid regex")
            .is_match(line)
        {
            return line.to_string();
        }
    }

    first_non_empty_line(input)
        .unwrap_or("State the concrete task outcome in one sentence.".to_string())
}

fn infer_deliverable(input: &str) -> String {
    let lower = input.to_lowercase();
    if lower.contains("review") {
        "A concise review with findings ordered by severity.".to_string()
    } else if lower.contains("document") || lower.contains("write docs") {
        "Updated documentation with any required implementation changes.".to_string()
    } else if lower.contains("fix")
        || lower.contains("implement")
        || lower.contains("build")
        || lower.contains("scaffold")
        || lower.contains("add")
    {
        "Working code changes with tests or verification notes.".to_string()
    } else {
        "A concrete implementation or analysis artifact, not just general advice.".to_string()
    }
}

fn infer_acceptance_criteria(input: &str) -> Vec<String> {
    let mut criteria = Vec::new();
    let lower = input.to_lowercase();

    if lower.contains("status.md") {
        criteria.push("STATUS.md is updated to reflect the new milestone.".to_string());
    }
    if lower.contains("test") || lower.contains("verify") {
        criteria.push("Relevant tests or verification steps are run and reported.".to_string());
    }
    if lower.contains("safe mode") {
        criteria.push("Safe-mode protections are preserved and visible.".to_string());
    }

    if criteria.is_empty() {
        criteria.push("Relevant tests or checks pass for the touched scope.".to_string());
        criteria
            .push("The output clearly states what changed and any remaining risks.".to_string());
    }

    criteria
}

fn render_list_or_placeholder(items: &[String], placeholder: &str) -> String {
    if items.is_empty() {
        placeholder.to_string()
    } else {
        items
            .iter()
            .map(|item| format!("- {item}"))
            .collect::<Vec<_>>()
            .join("\n")
    }
}

fn first_non_empty_line(input: &str) -> Option<String> {
    input
        .lines()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .map(str::to_string)
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIXTURE: &str = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/long-prompt.txt"
    ));

    #[test]
    fn flags_redundancy_and_scope_gaps() {
        let report = analyze_prompt(FIXTURE);
        let codes = report
            .findings
            .iter()
            .map(|finding| finding.code.as_str())
            .collect::<Vec<_>>();
        assert!(codes.contains(&"redundant_constraints"));
        assert!(codes.contains(&"overbroad_scope"));
        assert!(codes.contains(&"missing_file_scope"));
        assert!(report.suggestion.rewrite.contains("Objective"));
        assert!(report.suggestion.diff.contains("+ Objective"));
    }
}
