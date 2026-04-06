use regex::Regex;

use crate::{
    append_missing_protected_context, build_result, collapse_blank_lines, contains_fenced_code,
    fail_open, ProtectionRules, ProvenanceNote, Reducer, ReducerKind, ReductionMode, RiskLevel,
};

pub struct TestLogReducer;

impl Reducer for TestLogReducer {
    fn kind(&self) -> ReducerKind {
        ReducerKind::TestLog
    }

    fn detect(&self, input: &str) -> f32 {
        let mut score: f32 = 0.0;
        if input.contains("PASS ") || input.contains("FAIL ") {
            score += 0.5;
        }
        if input.contains("Test Suites:") || input.contains("Ran all test suites") {
            score += 0.35;
        }
        if input.contains("AssertionError") || input.contains("expected") {
            score += 0.2;
        }
        // Rust test output
        if input.contains("test result: ok.")
            || input.contains("test result: FAILED")
            || input.contains("running ") && input.contains(" tests")
        {
            score += 0.5;
        }
        // pytest output
        if input.contains("passed") && input.contains("failed")
            || input.contains("PASSED")
            || input.contains("FAILED")
        {
            score += 0.4;
        }
        score.min(1.0)
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
                "Input did not match test log heuristics",
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

        let pass_regex = Regex::new(r"^(?:PASS|ok)\s+(.+)$").expect("valid regex");
        let symbol_pass_regex = Regex::new(r"^\s*[✓✔]\s+(.+)$").expect("valid regex");
        let summary_regex =
            Regex::new(r"^(?:Test Suites:|Tests:|Snapshots:|Time:|Ran all test suites|test result:)")
                .expect("valid regex");

        let mut kept = Vec::new();
        let mut pass_count = 0usize;
        let mut progress_lines = 0usize;
        let mut in_fail_block = false;

        for line in input.lines() {
            let trimmed = line.trim();

            // Empty lines: keep if inside a failure block, skip otherwise
            if trimmed.is_empty() {
                if in_fail_block {
                    kept.push(String::new());
                }
                continue;
            }

            // Progress dots
            if trimmed.chars().all(|ch| matches!(ch, '.' | '·')) {
                progress_lines += 1;
                continue;
            }

            // Passing test lines — just count them
            if pass_regex.is_match(trimmed) || symbol_pass_regex.is_match(trimmed) {
                pass_count += 1;
                in_fail_block = false;
                continue;
            }

            // Rust-style passing: "test foo::bar ... ok"
            if trimmed.starts_with("test ") && trimmed.ends_with(" ... ok") {
                pass_count += 1;
                in_fail_block = false;
                continue;
            }

            // Failure markers — keep and enter fail block
            if trimmed.starts_with("FAIL ")
                || trimmed.starts_with("ERROR ")
                || trimmed.starts_with("FAILED")
                || (trimmed.starts_with("test ") && trimmed.ends_with(" ... FAILED"))
            {
                in_fail_block = true;
                kept.push(line.to_string());
                continue;
            }

            // Commands and summaries — always keep
            if trimmed.starts_with("$ ")
                || trimmed.starts_with("> ")
                || trimmed.starts_with("npm ")
                || trimmed.starts_with("pnpm ")
                || trimmed.starts_with("cargo ")
                || trimmed.starts_with("pytest ")
                || summary_regex.is_match(trimmed)
            {
                in_fail_block = false;
                kept.push(line.to_string());
                continue;
            }

            // Error details — keep
            if trimmed.contains("Error")
                || trimmed.contains("error[")
                || trimmed.contains("Expected:")
                || trimmed.contains("Received:")
                || trimmed.contains("panicked at")
                || trimmed.starts_with("at ")
                || (trimmed.starts_with("thread ") && trimmed.contains("panicked"))
            {
                in_fail_block = true;
                kept.push(line.to_string());
                continue;
            }

            // Inside a failure block — keep context lines (indented descriptions, stack frames)
            if in_fail_block {
                kept.push(line.to_string());
                continue;
            }

            // Outside a failure block — this is noise (passing test descriptions, etc.)
            // Skip it.
        }

        // Add compact summary of passing tests
        if pass_count > 0 {
            kept.push(format!("[context-os] {pass_count} tests passed (collapsed)"));
        }
        if progress_lines > 0 {
            kept.push(format!(
                "[context-os] progress_lines_removed={progress_lines}"
            ));
        }

        let reduced = collapse_blank_lines(&kept).join("\n");
        // Skip append_missing_protected_context for test logs — the passing test
        // file paths aren't critical context and re-adding them defeats the reduction.
        // Failure file paths are already preserved in the kept failure blocks.
        // Only re-add explicitly requested protected_literals.
        let reduced = if protections.protected_literals.is_empty() {
            reduced
        } else {
            let lite_protections = ProtectionRules {
                preserve_code_blocks: false,
                preserve_commands: false,
                preserve_file_paths: false,
                preserve_versions: false,
                preserve_identifiers: false,
                protected_literals: protections.protected_literals.clone(),
            };
            append_missing_protected_context(input, &reduced, &lite_protections)
        };

        let total_collapsed = pass_count + progress_lines;
        let explanation = if total_collapsed == 0 {
            "Test log contained no safe reduction opportunities beyond protection checks"
                .to_string()
        } else {
            format!(
                "Collapsed {pass_count} passing tests and {progress_lines} progress lines; preserved failures, errors, commands, and summaries"
            )
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
                reason: "pass-collapse".to_string(),
                detail: "Passing test entries replaced with count; failure details preserved"
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
                "Safe reduction did not lower the estimated token count; original test log preserved",
            );
        }

        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIXTURE: &str = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/test-log-jest.txt"
    ));

    #[test]
    fn preserves_failures_and_commands() {
        let reducer = TestLogReducer;
        let result = reducer.reduce(
            FIXTURE,
            ReductionMode::Safe,
            &ProtectionRules::safe_defaults(),
        );
        assert!(result.output.contains("$ pnpm test --filter api"));
        assert!(result.output.contains("FAIL tests/api/users.spec.ts"));
        assert!(result.output.contains("AssertionError"));
        assert!(result.output.contains("13 tests passed"));
        assert!(
            result.metadata.after_tokens < result.metadata.before_tokens,
            "Should reduce tokens: before={} after={}",
            result.metadata.before_tokens,
            result.metadata.after_tokens
        );
    }
}
