use regex::Regex;

use crate::{
    append_missing_protected_context, build_result, collapse_blank_lines, contains_fenced_code,
    fail_open, ProtectionRules, ProvenanceNote, Reducer, ReducerKind, ReductionMode, RiskLevel,
};

pub struct BuildLogReducer;

impl Reducer for BuildLogReducer {
    fn kind(&self) -> ReducerKind {
        ReducerKind::BuildLog
    }

    fn detect(&self, input: &str) -> f32 {
        let mut score: f32 = 0.0;

        // Cargo build output
        if input.contains("Compiling ") && input.contains(" v") {
            score += 0.55;
        }

        // Cargo/rustc errors
        if input.contains("error[E") || input.contains("warning[") {
            score += 0.3;
        }

        // npm/pnpm/yarn install output
        if input.contains("added ") && input.contains(" packages") {
            score += 0.45;
        }
        if input.contains("npm warn") || input.contains("npm ERR!") {
            score += 0.3;
        }

        // Webpack / vite
        if input.contains("webpack compiled")
            || input.contains("vite")
                && (input.contains("build") || input.contains("transforming"))
        {
            score += 0.45;
        }
        if input.contains("chunk ") && input.contains(" kB") {
            score += 0.3;
        }

        // tsc
        if input.contains("error TS") || input.contains("tsc") && input.contains("--") {
            score += 0.4;
        }

        // Go build
        if input.contains("go build") || input.contains("go: downloading") {
            score += 0.4;
        }

        // Gradle
        if input.contains("> Task :") || input.contains("BUILD SUCCESSFUL")
            || input.contains("BUILD FAILED")
        {
            score += 0.45;
        }

        // Maven
        if input.contains("[INFO] Building ") || input.contains("[INFO] BUILD ")
            || input.contains("[ERROR]")
        {
            score += 0.4;
        }

        // Downloading lines (generic)
        if input.contains("Downloading ") {
            score += 0.15;
        }

        // General build command prefixes
        if input.contains("$ cargo build")
            || input.contains("$ npm run build")
            || input.contains("$ pnpm build")
            || input.contains("$ yarn build")
            || input.contains("$ go build")
            || input.contains("$ gradle")
            || input.contains("$ mvn")
            || input.contains("$ tsc")
        {
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
                "Input did not match build log heuristics",
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

        let compiling_regex =
            Regex::new(r"^\s*Compiling\s+\S+\s+v[\d.]+").expect("valid regex");
        let downloading_regex =
            Regex::new(r"^\s*Downloading\s+").expect("valid regex");
        let progress_regex =
            Regex::new(r"^\s*[\[#=>\-\s\]]{5,}\s*\d*%?").expect("valid regex");
        let spinner_regex =
            Regex::new(r"^\s*[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏|/\-\\]").expect("valid regex");
        let npm_install_regex =
            Regex::new(r"^(?:added|removed|changed)\s+\d+\s+packages?").expect("valid regex");
        let chunk_regex =
            Regex::new(r"^\s*[\w./\-]+\s+\d+(?:\.\d+)?\s*(?:kB|KB|MB|bytes)\b").expect("valid regex");
        let webpack_chunk_regex =
            Regex::new(r"^\s*(?:asset|chunk)\s+").expect("valid regex");
        let vite_transform_regex =
            Regex::new(r"^\s*transforming\s+\(\d+\)").expect("valid regex");
        let summary_regex = Regex::new(
            r"(?i)^(?:error\[|error:|error TS|error!|warning\[|warning:|warn |error aborting|For more information|BUILD SUCCESSFUL|BUILD FAILED|\[INFO\] BUILD |\[ERROR\]|webpack compiled|Successfully compiled|✓ |✗ |failed to compile|Finished|Caused by)"
        ).expect("valid regex");
        let command_regex = Regex::new(
            r"^(?:\$\s|>\s)?(?:cargo|npm|pnpm|yarn|npx|go|gradle|gradlew|mvn|tsc|webpack|vite)\b"
        ).expect("valid regex");

        let mut kept = Vec::new();
        let mut compiling_count = 0usize;
        let mut downloading_count = 0usize;
        let mut progress_lines = 0usize;
        let mut npm_install_lines = 0usize;
        let mut chunk_lines = 0usize;
        let mut in_error_block = false;

        for line in input.lines() {
            let trimmed = line.trim();

            // Empty lines: keep if inside an error block, skip otherwise
            if trimmed.is_empty() {
                if in_error_block {
                    kept.push(String::new());
                }
                continue;
            }

            // Commands — always keep
            if command_regex.is_match(trimmed) {
                in_error_block = false;
                kept.push(line.to_string());
                continue;
            }

            // Error and warning lines — always keep
            if summary_regex.is_match(trimmed) {
                in_error_block = true;
                kept.push(line.to_string());
                continue;
            }

            // Lines with "error" or "warning" in them (rustc style context lines)
            if trimmed.contains("expected")
                || trimmed.contains("found")
                || trimmed.contains("help:")
                || trimmed.contains("note:")
                || trimmed.starts_with("--> ")
                || trimmed.starts_with("| ")
                || trimmed.starts_with("|")
                    && trimmed.len() > 1
                    && trimmed.chars().nth(1).map_or(false, |c| c == ' ' || c == '^')
            {
                in_error_block = true;
                kept.push(line.to_string());
                continue;
            }

            // Rustc error context: lines starting with line numbers
            if in_error_block
                && (trimmed.starts_with(|c: char| c.is_ascii_digit())
                    || trimmed.starts_with("..."))
            {
                kept.push(line.to_string());
                continue;
            }

            // Inside an error block — keep context
            if in_error_block && (trimmed.starts_with("  ") || trimmed.starts_with("\t")) {
                kept.push(line.to_string());
                continue;
            }

            // Compiling lines — collapse
            if compiling_regex.is_match(trimmed) {
                compiling_count += 1;
                in_error_block = false;
                continue;
            }

            // Downloading lines — collapse
            if downloading_regex.is_match(trimmed) {
                downloading_count += 1;
                in_error_block = false;
                continue;
            }

            // Progress bars and spinners — collapse
            if progress_regex.is_match(trimmed) || spinner_regex.is_match(trimmed) {
                progress_lines += 1;
                in_error_block = false;
                continue;
            }

            // npm install summary lines — collapse
            if npm_install_regex.is_match(trimmed) {
                npm_install_lines += 1;
                in_error_block = false;
                continue;
            }

            // Webpack/vite chunk listings — collapse
            if chunk_regex.is_match(trimmed)
                || webpack_chunk_regex.is_match(trimmed)
                || vite_transform_regex.is_match(trimmed)
            {
                chunk_lines += 1;
                in_error_block = false;
                continue;
            }

            // Not in error block — check if this is a "Compiling my-app" line (local crate)
            if trimmed.starts_with("Compiling ") {
                compiling_count += 1;
                in_error_block = false;
                continue;
            }

            // Downloading crates ... header
            if trimmed == "Downloading crates ..." {
                in_error_block = false;
                continue;
            }

            // Fall through: keep everything else (final summaries, etc.)
            in_error_block = false;
            kept.push(line.to_string());
        }

        // Add compact summaries
        if compiling_count > 0 {
            kept.push(format!(
                "[context-os] {compiling_count} crates compiled (collapsed)"
            ));
        }
        if downloading_count > 0 {
            kept.push(format!(
                "[context-os] {downloading_count} packages downloaded (collapsed)"
            ));
        }
        if npm_install_lines > 0 {
            kept.push(format!(
                "[context-os] {npm_install_lines} npm install lines (collapsed)"
            ));
        }
        if chunk_lines > 0 {
            kept.push(format!(
                "[context-os] {chunk_lines} chunk/asset listings (collapsed)"
            ));
        }
        if progress_lines > 0 {
            kept.push(format!(
                "[context-os] progress_lines_removed={progress_lines}"
            ));
        }

        let reduced = collapse_blank_lines(&kept).join("\n");
        // Use lite_protections for build logs — the compiled crate paths are not
        // critical context and re-adding them defeats the reduction.
        // Error file paths are already preserved in the kept error blocks.
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

        let total_collapsed =
            compiling_count + downloading_count + progress_lines + npm_install_lines + chunk_lines;
        let explanation = if total_collapsed == 0 {
            "Build log contained no safe reduction opportunities beyond protection checks"
                .to_string()
        } else {
            format!(
                "Collapsed {compiling_count} compiling lines, {downloading_count} downloading lines, {progress_lines} progress lines, {npm_install_lines} npm install lines, and {chunk_lines} chunk listings; preserved errors, warnings, commands, and summaries"
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
                reason: "build-collapse".to_string(),
                detail: "Successful compilation lines replaced with count; errors and warnings preserved".to_string(),
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
                "Safe reduction did not lower the estimated token count; original build log preserved",
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
        "/../../tests/fixtures/build-log-cargo.txt"
    ));

    #[test]
    fn detects_cargo_build_log() {
        let reducer = BuildLogReducer;
        let confidence = reducer.detect(FIXTURE);
        assert!(
            confidence >= 0.5,
            "Should detect cargo build log with high confidence, got {confidence}"
        );
    }

    #[test]
    fn preserves_errors_and_warnings() {
        let reducer = BuildLogReducer;
        let result = reducer.reduce(
            FIXTURE,
            ReductionMode::Safe,
            &ProtectionRules::safe_defaults(),
        );
        // Command preserved
        assert!(result.output.contains("$ cargo build --release"));
        // Errors preserved
        assert!(result.output.contains("error[E0308]: mismatched types"));
        assert!(result.output.contains("error[E0599]"));
        assert!(result.output.contains("src/routes/api.rs:82:20"));
        assert!(result.output.contains("src/workers/notify.rs:31:14"));
        // Warnings preserved
        assert!(result.output.contains("warning[unused_imports]"));
        assert!(result.output.contains("warning[dead_code]"));
        // Final summary preserved
        assert!(result.output.contains("error: aborting due to 2 previous errors"));
        assert!(result.output.contains("For more information"));
        // Compiling lines collapsed
        assert!(result.output.contains("crates compiled"));
        // Downloading lines collapsed
        assert!(result.output.contains("packages downloaded"));
        // Token reduction
        assert!(
            result.metadata.after_tokens < result.metadata.before_tokens,
            "Should reduce tokens: before={} after={}",
            result.metadata.before_tokens,
            result.metadata.after_tokens
        );
    }
}
