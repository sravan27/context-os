use crate::{
    append_missing_protected_context, build_result, collapse_blank_lines, contains_fenced_code,
    fail_open, ProtectionRules, ProvenanceNote, Reducer, ReducerKind, ReductionMode, RiskLevel,
};

pub struct ConfigReducer;

impl Reducer for ConfigReducer {
    fn kind(&self) -> ReducerKind {
        ReducerKind::Config
    }

    fn detect(&self, input: &str) -> f32 {
        // Reject input that looks like a stack trace — YAML/TOML parsers are
        // lenient enough to accept traces, which causes misclassification.
        if looks_like_stack_trace(input) {
            return 0.0;
        }
        if looks_like_structured_config(input) && toml::from_str::<toml::Value>(input).is_ok() {
            return 0.9;
        }
        if looks_like_structured_config(input)
            && serde_yaml::from_str::<serde_yaml::Value>(input).is_ok()
        {
            return 0.75;
        }
        if looks_like_ini(input) {
            return 0.7;
        }
        0.0
    }

    fn reduce(
        &self,
        input: &str,
        mode: ReductionMode,
        protections: &ProtectionRules,
    ) -> crate::ReductionResult {
        let confidence = self.detect(input);
        if confidence == 0.0 {
            return fail_open(
                self.kind(),
                mode,
                RiskLevel::Low,
                confidence,
                input,
                "Input did not match config heuristics",
            );
        }

        if mode == ReductionMode::Safe
            && protections.preserve_code_blocks
            && contains_fenced_code(input)
        {
            return fail_open(
                self.kind(),
                mode,
                RiskLevel::Low,
                confidence,
                input,
                "Preserved fenced code block content in safe mode",
            );
        }

        let mut kept = Vec::new();
        let mut removed_comments = 0usize;

        for line in input.lines() {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                kept.push(String::new());
                continue;
            }

            if is_ignorable_comment(trimmed, protections) {
                removed_comments += 1;
                continue;
            }

            kept.push(line.to_string());
        }

        let reduced = collapse_blank_lines(&kept).join("\n");
        let reduced = append_missing_protected_context(input, &reduced, protections);
        let explanation = if removed_comments > 0 {
            format!(
                "Removed {removed_comments} low-signal config comments while preserving keys, sections, and protected values"
            )
        } else {
            "Config input was already concise; only protection checks were applied".to_string()
        };

        let result = build_result(
            self.kind(),
            mode,
            RiskLevel::Low,
            confidence,
            input,
            reduced,
            explanation,
            vec![ProvenanceNote {
                reason: "comment-prune".to_string(),
                detail:
                    "Low-signal comment lines were removed from config-style input in safe mode"
                        .to_string(),
            }],
        );

        if result.metadata.transformed
            && result.metadata.after_tokens >= result.metadata.before_tokens
        {
            return fail_open(
                self.kind(),
                mode,
                RiskLevel::Low,
                confidence,
                input,
                "Safe reduction did not lower the estimated token count; original config preserved",
            );
        }

        result
    }
}

fn looks_like_stack_trace(input: &str) -> bool {
    let at_lines = input
        .lines()
        .filter(|line| line.trim_start().starts_with("at "))
        .count();
    let has_error = input.contains("Error:") || input.contains("Exception")
        || input.contains("Traceback (most recent call last)");
    at_lines >= 2 && has_error
}

fn looks_like_ini(input: &str) -> bool {
    input.lines().any(|line| {
        let trimmed = line.trim();
        trimmed.starts_with('[') && trimmed.ends_with(']')
            || trimmed.contains('=')
            || trimmed.contains(':')
    })
}

fn looks_like_structured_config(input: &str) -> bool {
    let mut assignment_like = 0usize;
    let mut section_like = 0usize;

    for line in input.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') || trimmed.starts_with("//") {
            continue;
        }
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            section_like += 1;
        }
        if trimmed.contains('=') {
            assignment_like += 1;
            continue;
        }
        if trimmed.contains(':')
            && !trimmed.contains("://")
            && !trimmed.ends_with('.')
            && !trimmed.ends_with('?')
        {
            assignment_like += 1;
        }
    }

    section_like > 0 || assignment_like >= 2
}

fn is_ignorable_comment(line: &str, protections: &ProtectionRules) -> bool {
    let is_comment = line.starts_with('#') || line.starts_with(';') || line.starts_with("//");
    if !is_comment {
        return false;
    }

    let important_markers = ["TODO", "FIXME", "NOTE", "WARNING", "IMPORTANT"];
    if important_markers.iter().any(|marker| line.contains(marker)) {
        return false;
    }
    if protections
        .protected_literals
        .iter()
        .any(|literal| line.contains(literal))
    {
        return false;
    }
    if line.contains('/') || line.contains("v1.") || line.contains("v2.") {
        return false;
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIXTURE: &str = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/service-config.toml"
    ));

    #[test]
    fn removes_low_signal_comments_without_dropping_versions() {
        let reducer = ConfigReducer;
        let result = reducer.reduce(
            FIXTURE,
            ReductionMode::Safe,
            &ProtectionRules::safe_defaults(),
        );
        assert!(result.output.contains("service_version = \"v1.14.2\""));
        assert!(result.output.contains("listen_addr = \"127.0.0.1:8080\""));
        assert!(result.metadata.before_tokens >= result.metadata.after_tokens);
    }

    #[test]
    fn does_not_overfire_on_natural_language_prompt() {
        let reducer = ConfigReducer;
        let prompt = "Please review the repo and fix the issue.\nDo not silently change behavior.\nThis is production-grade work.";
        assert_eq!(reducer.detect(prompt), 0.0);
    }
}
