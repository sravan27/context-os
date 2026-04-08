use std::collections::HashMap;

use regex::Regex;

use crate::{
    append_missing_protected_context, build_result, collapse_blank_lines, contains_fenced_code,
    fail_open, ProtectionRules, ProvenanceNote, Reducer, ReducerKind, ReductionMode, RiskLevel,
};

pub struct LintOutputReducer;

impl Reducer for LintOutputReducer {
    fn kind(&self) -> ReducerKind {
        ReducerKind::LintOutput
    }

    fn detect(&self, input: &str) -> f32 {
        let mut score: f32 = 0.0;

        // Clippy / rustc lint format: warning[clippy::...] or error[E...]
        if input.contains("warning[") || input.contains("error[") {
            score += 0.5;
        }

        // ESLint: explicit mention or "line:col  error/warning  message  rule" pattern
        let eslint_line_re =
            Regex::new(r"(?m)^\s*\d+:\d+\s+(?:error|warning)\s+").expect("valid regex");
        if input.contains("eslint") || eslint_line_re.is_match(input) {
            score += 0.4;
        }

        // Pylint / flake8: explicit mention or code pattern like C0114, W0611, E0001
        let pylint_code_re = Regex::new(r"(?m)[CWERFI]\d{4}[:\s]").expect("valid regex");
        if input.contains("pylint") || input.contains("flake8") || pylint_code_re.is_match(input) {
            score += 0.4;
        }

        // TypeScript compiler errors: "error TS"
        if input.contains("error TS") {
            score += 0.4;
        }

        // Generic warning:/error: lines (multiple occurrences suggest lint output)
        let warning_error_re = Regex::new(r"(?m)(?:warning|error):").expect("valid regex");
        let match_count = warning_error_re.find_iter(input).count();
        if match_count >= 3 {
            score += 0.3;
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
                "Input did not match lint output heuristics",
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

        // Regex for lines that start error/warning blocks (clippy, rustc, eslint, etc.)
        let error_start_re =
            Regex::new(r"(?i)^(?:error\[|error:|error TS|error!)").expect("valid regex");
        let warning_start_re = Regex::new(r"(?i)^(?:warning\[|warning:)").expect("valid regex");
        let command_re = Regex::new(r"^(?:\$\s|>\s)").expect("valid regex");
        let summary_re = Regex::new(
            r"(?i)^(?:error: aborting|error aborting|For more information|found \d+|generated \d+|\d+ warnings?|\d+ errors?|warning: .* generated \d+|could not compile|finished)"
        ).expect("valid regex");
        // Clippy warning rule extractor: warning[clippy::foo] or warning: `unused_import`
        let clippy_rule_re = Regex::new(r"warning\[([^\]]+)\]").expect("valid regex");
        // Context lines in rustc/clippy output
        let context_line_re = Regex::new(r"^\s*(?:-->|= note:|= help:|help:|note:|\||\d+\s*\|)")
            .expect("valid regex");
        // File location line: --> src/foo.rs:12:5
        let location_re = Regex::new(r"-->\s+(\S+:\d+:\d+)").expect("valid regex");

        // ---- First pass: parse warnings into groups ----
        // We track each warning by its rule name and accumulate locations.
        // Errors are always kept in full.

        struct DiagBlock {
            is_error: bool,
            rule: String,       // e.g. "clippy::needless_return" or the first line
            location: String,   // e.g. "src/foo.rs:12:5"
            lines: Vec<String>, // all lines in the block
        }

        let mut blocks: Vec<DiagBlock> = Vec::new();
        let mut command_lines: Vec<String> = Vec::new();
        let mut summary_lines: Vec<String> = Vec::new();
        let mut other_lines: Vec<String> = Vec::new();

        let mut current_block: Option<DiagBlock> = None;

        for line in input.lines() {
            let trimmed = line.trim();

            // Command lines
            if command_re.is_match(trimmed) {
                if let Some(block) = current_block.take() {
                    blocks.push(block);
                }
                command_lines.push(line.to_string());
                continue;
            }

            // Summary lines
            if summary_re.is_match(trimmed) {
                if let Some(block) = current_block.take() {
                    blocks.push(block);
                }
                summary_lines.push(line.to_string());
                continue;
            }

            // Start of an error block
            if error_start_re.is_match(trimmed) {
                if let Some(block) = current_block.take() {
                    blocks.push(block);
                }
                current_block = Some(DiagBlock {
                    is_error: true,
                    rule: trimmed.to_string(),
                    location: String::new(),
                    lines: vec![line.to_string()],
                });
                continue;
            }

            // Start of a warning block
            if warning_start_re.is_match(trimmed) {
                if let Some(block) = current_block.take() {
                    blocks.push(block);
                }
                let rule = clippy_rule_re
                    .captures(trimmed)
                    .map(|c| c[1].to_string())
                    .unwrap_or_else(|| trimmed.to_string());
                current_block = Some(DiagBlock {
                    is_error: false,
                    rule,
                    location: String::new(),
                    lines: vec![line.to_string()],
                });
                continue;
            }

            // Context lines belonging to current block
            if let Some(ref mut block) = current_block {
                if context_line_re.is_match(trimmed)
                    || trimmed.is_empty()
                    || (trimmed.starts_with(|c: char| c.is_ascii_digit()) && trimmed.contains('|'))
                    || trimmed.starts_with("  ")
                    || trimmed.starts_with('\t')
                {
                    // Capture location if present
                    if let Some(caps) = location_re.captures(trimmed) {
                        if block.location.is_empty() {
                            block.location = caps[1].to_string();
                        }
                    }
                    block.lines.push(line.to_string());
                    continue;
                }
                // Non-context line: close block
                blocks.push(current_block.take().unwrap());
                other_lines.push(line.to_string());
                continue;
            }

            // Lines outside any block
            if !trimmed.is_empty() {
                other_lines.push(line.to_string());
            }
        }

        if let Some(block) = current_block.take() {
            blocks.push(block);
        }

        // ---- Second pass: group warnings by rule, keep errors in full ----
        let mut kept: Vec<String> = Vec::new();

        // Command lines first
        for line in &command_lines {
            kept.push(line.clone());
        }

        // All error blocks in full
        for block in &blocks {
            if block.is_error {
                for line in &block.lines {
                    kept.push(line.clone());
                }
            }
        }

        // Group warnings by rule
        let mut warning_groups: HashMap<String, Vec<&DiagBlock>> = HashMap::new();
        let mut warning_order: Vec<String> = Vec::new();
        for block in &blocks {
            if !block.is_error {
                if !warning_groups.contains_key(&block.rule) {
                    warning_order.push(block.rule.clone());
                }
                warning_groups
                    .entry(block.rule.clone())
                    .or_default()
                    .push(block);
            }
        }

        let mut collapsed_warning_count = 0usize;
        let mut unique_warning_count = 0usize;

        for rule in &warning_order {
            let group = &warning_groups[rule];
            if group.len() == 1 {
                // Unique warning — keep in full
                unique_warning_count += 1;
                for line in &group[0].lines {
                    kept.push(line.clone());
                }
            } else {
                // Multiple occurrences — keep one example, collapse rest
                unique_warning_count += 1;
                collapsed_warning_count += group.len() - 1;
                // Keep the first occurrence as the example
                for line in &group[0].lines {
                    kept.push(line.clone());
                }
                // Summarise the rest
                let locations: Vec<&str> = group[1..]
                    .iter()
                    .filter_map(|b| {
                        if b.location.is_empty() {
                            None
                        } else {
                            Some(b.location.as_str())
                        }
                    })
                    .collect();
                let loc_summary = if locations.is_empty() {
                    format!("{} more occurrences", group.len() - 1)
                } else {
                    format!("{} more: {}", group.len() - 1, locations.join(", "))
                };
                kept.push(format!("[context-os] {rule}: {loc_summary} (collapsed)"));
            }
        }

        // Summary lines
        for line in &summary_lines {
            kept.push(line.clone());
        }

        let reduced = collapse_blank_lines(&kept).join("\n");

        // Use lite_protections pattern (same as build_log.rs)
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

        let total_warnings = unique_warning_count + collapsed_warning_count;
        let total_errors = blocks.iter().filter(|b| b.is_error).count();

        let explanation = if collapsed_warning_count == 0 {
            "Lint output contained no duplicate warnings to collapse".to_string()
        } else {
            let mut rule_counts: Vec<String> = Vec::new();
            for rule in &warning_order {
                let group = &warning_groups[rule];
                if group.len() > 1 {
                    rule_counts.push(format!("{} ({})", rule, group.len()));
                }
            }
            format!(
                "{total_warnings} warnings: collapsed {collapsed_warning_count} duplicates across rules: {}; preserved {total_errors} errors in full",
                rule_counts.join(", ")
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
                reason: "lint-collapse".to_string(),
                detail:
                    "Duplicate warnings collapsed to counts; errors and unique warnings preserved"
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
                "Safe reduction did not lower the estimated token count; original lint output preserved",
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
        "/../../tests/fixtures/lint-output-clippy.txt"
    ));

    #[test]
    fn detects_clippy_output() {
        let reducer = LintOutputReducer;
        let confidence = reducer.detect(FIXTURE);
        assert!(
            confidence >= 0.4,
            "Should detect clippy lint output with confidence >= 0.4, got {confidence}"
        );
    }

    #[test]
    fn collapses_duplicate_warnings() {
        let reducer = LintOutputReducer;
        let result = reducer.reduce(
            FIXTURE,
            ReductionMode::Safe,
            &ProtectionRules::safe_defaults(),
        );
        // Command preserved
        assert!(
            result.output.contains("$ cargo clippy"),
            "Command line should be preserved"
        );
        // Error preserved in full
        assert!(
            result.output.contains("error[E0308]"),
            "Error should be preserved"
        );
        // At least one warning example preserved
        assert!(
            result.output.contains("warning[clippy::needless_return]"),
            "Warning example should be preserved"
        );
        // Duplicate warnings collapsed
        assert!(
            result.output.contains("collapsed"),
            "Duplicate warnings should be collapsed with a summary"
        );
        // Summary line preserved
        assert!(
            result.output.contains("generated")
                || result.output.contains("aborting")
                || result.output.contains("warnings"),
            "Summary line should be preserved"
        );
        // Token reduction happened
        assert!(
            result.metadata.after_tokens < result.metadata.before_tokens,
            "Should reduce tokens: before={} after={}",
            result.metadata.before_tokens,
            result.metadata.after_tokens
        );
    }
}
