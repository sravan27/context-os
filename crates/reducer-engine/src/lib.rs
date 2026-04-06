pub mod reducers;

use std::fmt;
use std::str::FromStr;

use regex::Regex;
use serde::{Deserialize, Serialize};
use token_estimator::{estimate_text, ModelFamily};

pub use reducers::{
    build_log::BuildLogReducer, config::ConfigReducer, json::JsonReducer,
    lint_output::LintOutputReducer, stack_trace::StackTraceReducer, test_log::TestLogReducer,
};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ReductionMode {
    Safe,
    Balanced,
    Aggressive,
}

impl fmt::Display for ReductionMode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Safe => write!(f, "safe"),
            Self::Balanced => write!(f, "balanced"),
            Self::Aggressive => write!(f, "aggressive"),
        }
    }
}

impl FromStr for ReductionMode {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "safe" => Ok(Self::Safe),
            "balanced" => Ok(Self::Balanced),
            "aggressive" => Ok(Self::Aggressive),
            _ => Err(format!("unknown reduction mode: {value}")),
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ReducerKind {
    StackTrace,
    TestLog,
    BuildLog,
    LintOutput,
    Json,
    Config,
    Markdown,
    Csv,
    NlInstruction,
    ConservativeCodeContext,
}

impl fmt::Display for ReducerKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::StackTrace => write!(f, "stack_trace"),
            Self::TestLog => write!(f, "test_log"),
            Self::BuildLog => write!(f, "build_log"),
            Self::LintOutput => write!(f, "lint_output"),
            Self::Json => write!(f, "json"),
            Self::Config => write!(f, "config"),
            Self::Markdown => write!(f, "markdown"),
            Self::Csv => write!(f, "csv"),
            Self::NlInstruction => write!(f, "nl_instruction"),
            Self::ConservativeCodeContext => write!(f, "conservative_code_context"),
        }
    }
}

impl FromStr for ReducerKind {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "stack-trace" | "stack_trace" => Ok(Self::StackTrace),
            "test-log" | "test_log" => Ok(Self::TestLog),
            "build-log" | "build_log" => Ok(Self::BuildLog),
            "lint-output" | "lint_output" => Ok(Self::LintOutput),
            "json" => Ok(Self::Json),
            "config" => Ok(Self::Config),
            "markdown" => Ok(Self::Markdown),
            "csv" => Ok(Self::Csv),
            "nl-instruction" | "nl_instruction" => Ok(Self::NlInstruction),
            "conservative-code-context" | "conservative_code_context" => {
                Ok(Self::ConservativeCodeContext)
            }
            _ => Err(format!("unknown reducer kind: {value}")),
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RiskLevel {
    Low,
    Medium,
    High,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ProtectionRules {
    pub preserve_code_blocks: bool,
    pub preserve_commands: bool,
    pub preserve_file_paths: bool,
    pub preserve_versions: bool,
    pub preserve_identifiers: bool,
    pub protected_literals: Vec<String>,
}

impl Default for ProtectionRules {
    fn default() -> Self {
        Self::safe_defaults()
    }
}

impl ProtectionRules {
    pub fn safe_defaults() -> Self {
        Self {
            preserve_code_blocks: true,
            preserve_commands: true,
            preserve_file_paths: true,
            preserve_versions: true,
            preserve_identifiers: true,
            protected_literals: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SavingsEstimate {
    pub before_tokens: u32,
    pub after_tokens: u32,
    pub reduction_tokens: u32,
    pub reduction_ratio: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ProvenanceNote {
    pub reason: String,
    pub detail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ReductionMetadata {
    pub kind: ReducerKind,
    pub mode: ReductionMode,
    pub risk: RiskLevel,
    pub detected_confidence: f32,
    pub transformed: bool,
    pub before_tokens: u32,
    pub after_tokens: u32,
    pub explanation: String,
    pub provenance: Vec<ProvenanceNote>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ReductionResult {
    pub output: String,
    pub metadata: ReductionMetadata,
}

pub trait Reducer: Send + Sync {
    fn kind(&self) -> ReducerKind;
    fn detect(&self, input: &str) -> f32;
    fn reduce(
        &self,
        input: &str,
        mode: ReductionMode,
        protections: &ProtectionRules,
    ) -> ReductionResult;

    fn estimate_savings(
        &self,
        input: &str,
        mode: ReductionMode,
        protections: &ProtectionRules,
    ) -> SavingsEstimate {
        let result = self.reduce(input, mode, protections);
        SavingsEstimate {
            before_tokens: result.metadata.before_tokens,
            after_tokens: result.metadata.after_tokens,
            reduction_tokens: result
                .metadata
                .before_tokens
                .saturating_sub(result.metadata.after_tokens),
            reduction_ratio: reduction_ratio(
                result.metadata.before_tokens,
                result.metadata.after_tokens,
            ),
        }
    }
}

pub struct ReducerRegistry {
    reducers: Vec<Box<dyn Reducer>>,
}

impl Default for ReducerRegistry {
    fn default() -> Self {
        Self {
            reducers: vec![
                Box::new(StackTraceReducer),
                Box::new(TestLogReducer),
                Box::new(BuildLogReducer),
                Box::new(LintOutputReducer),
                Box::new(JsonReducer),
                Box::new(ConfigReducer),
            ],
        }
    }
}

impl ReducerRegistry {
    pub fn detect_best(&self, input: &str) -> Option<(ReducerKind, f32)> {
        self.reducers
            .iter()
            .map(|reducer| (reducer.kind(), reducer.detect(input)))
            .max_by(|a, b| a.1.total_cmp(&b.1))
            .filter(|(_, confidence)| *confidence > 0.0)
    }

    pub fn reduce(
        &self,
        kind: ReducerKind,
        input: &str,
        mode: ReductionMode,
        protections: &ProtectionRules,
    ) -> Option<ReductionResult> {
        self.reducers
            .iter()
            .find(|reducer| reducer.kind() == kind)
            .map(|reducer| reducer.reduce(input, mode, protections))
    }
}

pub fn build_result(
    kind: ReducerKind,
    mode: ReductionMode,
    risk: RiskLevel,
    detected_confidence: f32,
    input: &str,
    output: String,
    explanation: String,
    provenance: Vec<ProvenanceNote>,
) -> ReductionResult {
    let before = estimate_text(input, ModelFamily::Claude).estimated_tokens;
    let after = estimate_text(&output, ModelFamily::Claude).estimated_tokens;
    let transformed = input != output;

    ReductionResult {
        output,
        metadata: ReductionMetadata {
            kind,
            mode,
            risk,
            detected_confidence,
            transformed,
            before_tokens: before,
            after_tokens: after,
            explanation,
            provenance,
        },
    }
}

pub fn fail_open(
    kind: ReducerKind,
    mode: ReductionMode,
    risk: RiskLevel,
    detected_confidence: f32,
    input: &str,
    explanation: &str,
) -> ReductionResult {
    build_result(
        kind,
        mode,
        risk,
        detected_confidence,
        input,
        input.to_string(),
        explanation.to_string(),
        vec![ProvenanceNote {
            reason: "fail-open".to_string(),
            detail: "Reducer returned original content".to_string(),
        }],
    )
}

pub fn reduction_ratio(before_tokens: u32, after_tokens: u32) -> f32 {
    if before_tokens == 0 {
        0.0
    } else {
        (before_tokens.saturating_sub(after_tokens)) as f32 / before_tokens as f32
    }
}

pub fn contains_fenced_code(input: &str) -> bool {
    input.contains("```")
}

pub fn append_missing_protected_context(
    input: &str,
    reduced: &str,
    protections: &ProtectionRules,
) -> String {
    let mut missing = Vec::new();

    if protections.preserve_commands {
        for command in extract_command_lines(input) {
            if !reduced.contains(&command) {
                missing.push(command);
            }
        }
    }

    if protections.preserve_file_paths {
        for path in extract_matches(input, r"(?m)(?:\./|\.\./|/)[A-Za-z0-9_\-./]+") {
            if !reduced.contains(&path) {
                missing.push(path);
            }
        }
    }

    if protections.preserve_versions {
        for version in extract_matches(input, r"\bv?\d+\.\d+(?:\.\d+)?(?:[-+][A-Za-z0-9.\-]+)?\b") {
            if !reduced.contains(&version) {
                missing.push(version);
            }
        }
    }

    if protections.preserve_identifiers {
        for identifier in extract_matches(
            input,
            r"\b(?:[A-Za-z]+Error|[A-Za-z]+Exception|ERR_[A-Z_]+|E\d{3,})\b",
        ) {
            if !reduced.contains(&identifier) {
                missing.push(identifier);
            }
        }
    }

    for literal in &protections.protected_literals {
        if input.contains(literal) && !reduced.contains(literal) {
            missing.push(literal.clone());
        }
    }

    missing.dedup();
    if missing.is_empty() {
        return reduced.to_string();
    }

    let mut output = reduced.trim_end().to_string();
    output.push_str("\n\n[context-os preserved values]\n");
    for value in missing {
        output.push_str("- ");
        output.push_str(&value);
        output.push('\n');
    }
    output
}

pub fn extract_matches(input: &str, pattern: &str) -> Vec<String> {
    let regex = Regex::new(pattern).expect("valid regex");
    let mut values = Vec::new();
    for capture in regex.find_iter(input) {
        let value = capture.as_str().to_string();
        if !values.contains(&value) {
            values.push(value);
        }
    }
    values
}

pub fn extract_command_lines(input: &str) -> Vec<String> {
    let command_regex = Regex::new(
        r#"(?m)^(?:\$ |> )?(?:cargo|npm|pnpm|yarn|npx|pytest|python|python3|node|git|make|bash|sh|uv|poetry|pip|pip3)\b.*$"#,
    )
    .expect("valid regex");
    let mut values = Vec::new();
    for line in input.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.len() > 200 {
            continue;
        }
        if command_regex.is_match(trimmed) {
            let command = trimmed.to_string();
            if !values.contains(&command) {
                values.push(command);
            }
        }
    }
    values
}

pub fn collapse_blank_lines(lines: &[String]) -> Vec<String> {
    let mut result = Vec::new();
    let mut previous_blank = false;

    for line in lines {
        let blank = line.trim().is_empty();
        if blank && previous_blank {
            continue;
        }
        result.push(line.clone());
        previous_blank = blank;
    }

    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_detects_json() {
        let registry = ReducerRegistry::default();
        let detected = registry.detect_best("{\"ok\":true}").unwrap();
        assert_eq!(detected.0, ReducerKind::Json);
    }

    #[test]
    fn safe_protection_appends_missing_values() {
        let protections = ProtectionRules {
            protected_literals: vec!["alpha".to_string()],
            ..ProtectionRules::safe_defaults()
        };

        let output = append_missing_protected_context(
            "$ cargo test\nversion v1.2.3\nalpha",
            "summary only",
            &protections,
        );

        assert!(output.contains("cargo test"));
        assert!(output.contains("v1.2.3"));
        assert!(output.contains("alpha"));
    }
}
