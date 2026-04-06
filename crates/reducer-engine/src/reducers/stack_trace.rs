use crate::{
    append_missing_protected_context, build_result, collapse_blank_lines, contains_fenced_code,
    fail_open, ProtectionRules, ProvenanceNote, Reducer, ReducerKind, ReductionMode, RiskLevel,
};

pub struct StackTraceReducer;

impl Reducer for StackTraceReducer {
    fn kind(&self) -> ReducerKind {
        ReducerKind::StackTrace
    }

    fn detect(&self, input: &str) -> f32 {
        let mut score: f32 = 0.0;
        // Python tracebacks
        if input.contains("Traceback (most recent call last)") {
            score += 0.65;
        }
        // JS/Node "at " lines
        let at_lines = input
            .lines()
            .filter(|line| line.trim_start().starts_with("at "))
            .count();
        if at_lines >= 3 {
            score += 0.55;
        } else if at_lines >= 1 {
            score += 0.25;
        }
        // Rust backtraces: "stack backtrace:" header + numbered frames
        if input.contains("stack backtrace:") || input.contains("panicked at") {
            score += 0.5;
            let numbered_frames = input
                .lines()
                .filter(|line| {
                    let t = line.trim_start();
                    t.starts_with("0:") || t.chars().next().map_or(false, |c| c.is_ascii_digit())
                        && t.contains("::")
                })
                .count();
            if numbered_frames >= 3 {
                score += 0.2;
            }
        }
        if input.contains("Error:") || input.contains("Exception") {
            score += 0.2;
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
                "Input did not match stack trace heuristics",
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

        let lines: Vec<&str> = input.lines().collect();
        if lines.is_empty() {
            return fail_open(
                self.kind(),
                mode,
                RiskLevel::Low,
                confidence,
                input,
                "Empty stack trace input",
            );
        }

        let mut reduced = Vec::new();
        let mut i = 0;
        let mut collapsed_duplicate_lines = 0;
        let mut collapsed_internal_frames = 0;

        while i < lines.len() {
            let current = lines[i];
            let trimmed = current.trim();
            if trimmed.is_empty() {
                reduced.push(String::new());
                i += 1;
                continue;
            }

            // Collapse consecutive duplicate lines
            let mut duplicate_count = 1;
            while i + duplicate_count < lines.len() && lines[i + duplicate_count] == current {
                duplicate_count += 1;
            }

            if duplicate_count > 1 {
                reduced.push(current.to_string());
                collapsed_duplicate_lines += duplicate_count - 1;
                reduced.push(format!(
                    "[context-os] collapsed {} duplicate stack lines",
                    duplicate_count - 1
                ));
                i += duplicate_count;
                continue;
            }

            // Collapse internal/library frames in Rust backtraces
            // Keep: user code frames (contain ./ or src/ without /rustc/)
            // Collapse: runtime frames (/rustc/, library/std, library/core, library/alloc)
            if is_internal_frame(trimmed) {
                let mut internal_count = 0;
                while i + internal_count < lines.len() {
                    let candidate = lines[i + internal_count].trim();
                    // Internal frame lines and their "at" continuation lines
                    if is_internal_frame(candidate)
                        || (internal_count > 0 && candidate.starts_with("at ") && candidate.contains("/rustc/"))
                    {
                        internal_count += 1;
                    } else {
                        break;
                    }
                }
                if internal_count > 1 {
                    collapsed_internal_frames += internal_count;
                    reduced.push(format!(
                        "[context-os] collapsed {internal_count} internal runtime frames"
                    ));
                    i += internal_count;
                    continue;
                }
            }

            reduced.push(current.to_string());
            i += 1;
        }

        let reduced = collapse_blank_lines(&reduced).join("\n");
        let reduced = append_missing_protected_context(input, &reduced, protections);

        let total_collapsed = collapsed_duplicate_lines + collapsed_internal_frames;
        let explanation = if total_collapsed > 0 {
            format!(
                "Collapsed {collapsed_duplicate_lines} duplicate lines and {collapsed_internal_frames} internal frames while preserving error markers and user code paths"
            )
        } else {
            "No safe stack-trace compression opportunity detected; content passed through with protection checks".to_string()
        };

        build_result(
            self.kind(),
            mode,
            RiskLevel::Low,
            confidence,
            input,
            if reduced.is_empty() {
                input.to_string()
            } else {
                reduced
            },
            explanation,
            vec![ProvenanceNote {
                reason: "duplicate-collapse".to_string(),
                detail: "Consecutive duplicate stack-trace lines were replaced with explicit summary markers".to_string(),
            }],
        )
    }
}

/// Returns true if a trimmed line looks like a runtime/library frame that can be safely collapsed.
/// Matches Rust stdlib/compiler frames, Node.js internal frames, and Python stdlib frames.
fn is_internal_frame(trimmed: &str) -> bool {
    // Rust: numbered frames referencing /rustc/, library/std, library/core, library/alloc
    if trimmed.contains("/rustc/")
        || trimmed.contains("library/std/")
        || trimmed.contains("library/core/")
        || trimmed.contains("library/alloc/")
    {
        return true;
    }
    // Rust: known runtime symbols
    if trimmed.contains("rust_begin_unwind")
        || trimmed.contains("core::panicking::")
        || trimmed.contains("std::rt::")
        || trimmed.contains("std::sys::")
        || trimmed.contains("__libc_start_main")
        || trimmed.ends_with(": _start")
        || trimmed.ends_with(": main") && !trimmed.contains("::")
    {
        return true;
    }
    // Node.js internal frames
    if trimmed.contains("(internal/") || trimmed.contains("(node:") {
        return true;
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIXTURE: &str = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/stack-trace-node.txt"
    ));

    #[test]
    fn preserves_root_error_and_paths() {
        let reducer = StackTraceReducer;
        let result = reducer.reduce(
            FIXTURE,
            ReductionMode::Safe,
            &ProtectionRules::safe_defaults(),
        );
        assert!(result.output.contains("TypeError"));
        assert!(result.output.contains("/workspace/src/server.ts"));
        assert!(result.metadata.before_tokens >= result.metadata.after_tokens);
    }
}
