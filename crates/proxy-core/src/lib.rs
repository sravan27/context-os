use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use prompt_linter::{analyze_prompt, LintFinding, PromptLintReport};
use reducer_engine::{
    extract_command_lines, extract_matches, ProtectionRules, ReducerKind, ReducerRegistry,
    ReductionMetadata, ReductionMode,
};
use serde::{Deserialize, Serialize};
use session_memory::{
    diff_memory_states, update_structured_memory, CommandRecord, NextAction, PinnedFact,
    RecentTurn, SessionMemoryDiff, SessionMemoryUpdate, StructuredSessionMemory,
};
use telemetry::{SessionRecord, TelemetryStore, TransformEvent};
use thiserror::Error;
use token_estimator::{estimate_text, ModelFamily};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PayloadClass {
    StackTrace,
    TestLog,
    Json,
    Config,
    Prompt,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PayloadClassification {
    pub class: PayloadClass,
    pub reducer_kind: Option<ReducerKind>,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProxyRequest {
    pub session_id: String,
    pub content: String,
    pub upstream_url: Option<String>,
    pub cwd: Option<String>,
    pub reducer_hint: Option<ReducerKind>,
    pub reducer_mode: ReductionMode,
    pub enable_prompt_linter: bool,
    pub attach_session_memory: bool,
    pub session_state_path: Option<String>,
    pub telemetry_db_path: Option<String>,
    pub protected_literals: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProxyResponse {
    pub content: String,
    pub transformed: bool,
    pub before_tokens: u32,
    pub after_tokens: u32,
    pub classification: PayloadClassification,
    pub reduction: Option<ReductionMetadata>,
    pub prompt_lint: Option<PromptLintReport>,
    pub notes: Vec<String>,
    pub provenance: Vec<TransformProvenance>,
    pub session_memory_diff: Option<SessionMemoryDiff>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TransformProvenance {
    pub stage: String,
    pub reason: String,
    pub before_tokens: Option<u32>,
    pub after_tokens: Option<u32>,
}

#[derive(Debug, Error)]
pub enum ProxyError {
    #[error("failed to load session state: {0}")]
    SessionMemory(#[from] session_memory::SessionMemoryError),
    #[error("failed to write telemetry: {0}")]
    Telemetry(#[from] telemetry::TelemetryError),
}

pub fn intercept_request(request: ProxyRequest) -> Result<ProxyResponse, ProxyError> {
    let registry = ReducerRegistry::default();
    let protections = ProtectionRules {
        protected_literals: request.protected_literals.clone(),
        ..ProtectionRules::safe_defaults()
    };

    let classification = classify_payload(&registry, &request.content, request.reducer_hint);
    let before_tokens = estimate_text(&request.content, ModelFamily::Claude).estimated_tokens;
    let mut notes = Vec::new();
    let mut provenance = Vec::new();
    let mut reduction = None;
    let mut transformed_content = request.content.clone();

    if let Some(kind) = classification.reducer_kind {
        if let Some(result) =
            registry.reduce(kind, &request.content, request.reducer_mode, &protections)
        {
            if result.metadata.transformed {
                provenance.push(TransformProvenance {
                    stage: "reducer".to_string(),
                    reason: result.metadata.explanation.clone(),
                    before_tokens: Some(result.metadata.before_tokens),
                    after_tokens: Some(result.metadata.after_tokens),
                });
                notes.push(format!(
                    "Applied {} reducer in {} mode",
                    kind, request.reducer_mode
                ));
                transformed_content = result.output.clone();
            } else {
                notes.push(format!("{} reducer evaluated input but failed open", kind));
            }
            reduction = Some(result.metadata);
        }
    } else {
        notes.push("No typed reducer matched the input with sufficient confidence".to_string());
    }

    let prompt_lint = if request.enable_prompt_linter
        && matches!(
            classification.class,
            PayloadClass::Prompt | PayloadClass::Unknown
        ) {
        let report = analyze_prompt(&request.content);
        if !report.findings.is_empty() {
            provenance.push(TransformProvenance {
                stage: "prompt_linter".to_string(),
                reason: format!(
                    "Prompt linter produced {} finding(s)",
                    report.findings.len()
                ),
                before_tokens: None,
                after_tokens: None,
            });
            notes.push(format!(
                "Prompt linter found: {}",
                render_lint_summary(&report.findings)
            ));
        }
        Some(report)
    } else {
        None
    };

    let mut session_memory_diff = None;
    if let Some(path) = &request.session_state_path {
        let path_ref = Path::new(path);
        let mut session_state = StructuredSessionMemory::load_or_default(path_ref)?;
        let attachment_state = session_state.clone();
        let before_state = session_state.clone();

        if request.attach_session_memory {
            let attachment = render_session_memory_attachment(&attachment_state);
            if !attachment.is_empty() {
                transformed_content = format!("{attachment}\n\n{}", transformed_content);
                notes.push("Attached structured session memory block".to_string());
                provenance.push(TransformProvenance {
                    stage: "session_memory_attach".to_string(),
                    reason: "Attached pinned context and recent structured state".to_string(),
                    before_tokens: None,
                    after_tokens: None,
                });
            }
        }

        update_structured_memory(
            &mut session_state,
            derive_session_update(&request.content, &classification, prompt_lint.as_ref()),
        );
        session_state.save_to_path(path_ref)?;
        session_memory_diff = Some(diff_memory_states(&before_state, &session_state));
    }

    let after_tokens = estimate_text(&transformed_content, ModelFamily::Claude).estimated_tokens;
    let transformed = transformed_content != request.content;

    if let Some(db_path) = &request.telemetry_db_path {
        emit_telemetry(
            db_path,
            &request,
            &classification,
            before_tokens,
            after_tokens,
            reduction
                .as_ref()
                .map(|metadata| metadata.explanation.clone())
                .unwrap_or_else(|| "No reducer transformation applied".to_string()),
            &provenance,
        )?;
    }

    Ok(ProxyResponse {
        content: transformed_content,
        transformed,
        before_tokens,
        after_tokens,
        classification,
        reduction,
        prompt_lint,
        notes,
        provenance,
        session_memory_diff,
    })
}

pub fn classify_payload(
    registry: &ReducerRegistry,
    input: &str,
    hint: Option<ReducerKind>,
) -> PayloadClassification {
    if let Some(kind) = hint {
        return PayloadClassification {
            class: map_kind_to_class(kind),
            reducer_kind: Some(kind),
            confidence: 1.0,
        };
    }

    if let Some((kind, confidence)) = registry.detect_best(input) {
        if confidence >= 0.55 {
            return PayloadClassification {
                class: map_kind_to_class(kind),
                reducer_kind: Some(kind),
                confidence,
            };
        }
    }

    if is_prompt_like(input) {
        return PayloadClassification {
            class: PayloadClass::Prompt,
            reducer_kind: None,
            confidence: 0.6,
        };
    }

    PayloadClassification {
        class: PayloadClass::Unknown,
        reducer_kind: None,
        confidence: 0.0,
    }
}

fn map_kind_to_class(kind: ReducerKind) -> PayloadClass {
    match kind {
        ReducerKind::StackTrace => PayloadClass::StackTrace,
        ReducerKind::TestLog | ReducerKind::BuildLog | ReducerKind::LintOutput => {
            PayloadClass::TestLog
        }
        ReducerKind::Json => PayloadClass::Json,
        ReducerKind::Config => PayloadClass::Config,
        _ => PayloadClass::Unknown,
    }
}

fn is_prompt_like(input: &str) -> bool {
    let lower = input.to_lowercase();
    let action_markers = [
        "build",
        "implement",
        "fix",
        "update",
        "document",
        "review",
        "scaffold",
        "reduce",
        "write",
        "investigate",
        "proceed",
    ];
    input.lines().count() >= 2 && action_markers.iter().any(|marker| lower.contains(marker))
}

fn render_lint_summary(findings: &[LintFinding]) -> String {
    findings
        .iter()
        .take(3)
        .map(|finding| finding.code.as_str())
        .collect::<Vec<_>>()
        .join(", ")
}

fn render_session_memory_attachment(state: &StructuredSessionMemory) -> String {
    let mut lines = Vec::new();
    if let Some(objective) = &state.session_objective {
        lines.push(format!("objective: {objective}"));
    }
    if let Some(subtask) = &state.current_subtask {
        lines.push(format!("current_subtask: {subtask}"));
    }
    if !state.hard_constraints.is_empty() {
        lines.push(format!(
            "hard_constraints: {}",
            state.hard_constraints.join(" | ")
        ));
    }
    if !state.pinned_facts.is_empty() {
        lines.push(format!(
            "pinned_facts: {}",
            state
                .pinned_facts
                .iter()
                .map(|fact| fact.value.as_str())
                .take(6)
                .collect::<Vec<_>>()
                .join(" | ")
        ));
    }
    if !state.modified_files.is_empty() {
        lines.push(format!(
            "modified_files: {}",
            state
                .modified_files
                .iter()
                .rev()
                .take(6)
                .cloned()
                .collect::<Vec<_>>()
                .join(", ")
        ));
    }
    if !state.pending_next_actions.is_empty() {
        lines.push(format!(
            "next_actions: {}",
            state
                .pending_next_actions
                .iter()
                .take(5)
                .map(|item| item.summary.as_str())
                .collect::<Vec<_>>()
                .join(" | ")
        ));
    }

    if lines.is_empty() {
        return String::new();
    }

    format!(
        "[context-os session-memory]\n{}\n[/context-os session-memory]",
        lines.join("\n")
    )
}

fn derive_session_update(
    content: &str,
    classification: &PayloadClassification,
    prompt_lint: Option<&PromptLintReport>,
) -> SessionMemoryUpdate {
    let commands = extract_command_lines(content)
        .into_iter()
        .map(|command| CommandRecord {
            command,
            outcome: None,
        })
        .collect::<Vec<_>>();
    let file_paths = extract_file_paths(content);
    let failing_signatures = extract_matches(
        content,
        r"\b(?:[A-Za-z]+Error|[A-Za-z]+Exception|ERR_[A-Z_]+|E\d{3,})\b",
    );
    let hard_constraints = content
        .lines()
        .map(str::trim)
        .filter(|line| {
            line.contains("must")
                || line.contains("do not")
                || line.contains("never")
                || line.contains("safe mode")
        })
        .map(str::to_string)
        .collect::<Vec<_>>();
    let objective = if matches!(classification.class, PayloadClass::Prompt) {
        prompt_lint
            .map(|report| report.suggestion.objective.clone())
            .or_else(|| first_action_line(content))
    } else {
        None
    };
    let current_subtask = prompt_lint
        .map(|report| report.suggestion.deliverable.clone())
        .or_else(|| first_action_line(content));

    let mut pinned_facts = Vec::new();
    if content.contains("never silently rewrite") {
        pinned_facts.push(PinnedFact {
            value: "never silently rewrite".to_string(),
        });
    }

    SessionMemoryUpdate {
        session_objective: objective,
        current_subtask,
        hard_constraints,
        accepted_assumptions: Vec::new(),
        decisions_made: Vec::new(),
        modified_files: file_paths,
        tests_run: commands,
        failing_signatures,
        failed_approaches: extract_failed_approaches(content),
        pending_next_actions: extract_next_actions(prompt_lint, content),
        pinned_facts,
        recent_turns: vec![RecentTurn {
            role: "user".to_string(),
            content: truncate_for_turn(content),
        }],
    }
}

fn extract_failed_approaches(content: &str) -> Vec<String> {
    content
        .lines()
        .map(str::trim)
        .filter(|line| {
            line.starts_with("tried ")
                || line.starts_with("attempted ")
                || line.contains("didn't work")
                || line.contains("failed approach")
        })
        .map(str::to_string)
        .collect()
}

fn extract_next_actions(prompt_lint: Option<&PromptLintReport>, content: &str) -> Vec<NextAction> {
    if let Some(report) = prompt_lint {
        return report
            .suggestion
            .acceptance_criteria
            .iter()
            .map(|item| NextAction {
                summary: item.clone(),
            })
            .collect();
    }

    first_action_line(content)
        .map(|summary| vec![NextAction { summary }])
        .unwrap_or_default()
}

fn first_action_line(content: &str) -> Option<String> {
    content
        .lines()
        .map(str::trim)
        .find(|line| {
            !line.is_empty()
                && [
                    "build",
                    "implement",
                    "fix",
                    "update",
                    "document",
                    "review",
                    "scaffold",
                    "reduce",
                    "write",
                    "investigate",
                    "proceed",
                ]
                .iter()
                .any(|marker| line.to_lowercase().contains(marker))
        })
        .map(str::to_string)
}

fn extract_file_paths(content: &str) -> Vec<String> {
    let mut paths = extract_matches(
        content,
        r"(?x)
        (?:
          (?:\./|\.\./|/)[A-Za-z0-9_\-./]+
          |
          (?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+
        )",
    );
    paths.sort();
    paths.dedup();
    paths
}

fn truncate_for_turn(content: &str) -> String {
    let max_chars = 320usize;
    let trimmed = content.trim();
    if trimmed.chars().count() <= max_chars {
        trimmed.to_string()
    } else {
        let preview = trimmed.chars().take(max_chars).collect::<String>();
        format!("{preview}...")
    }
}

fn emit_telemetry(
    db_path: &str,
    request: &ProxyRequest,
    classification: &PayloadClassification,
    before_tokens: u32,
    after_tokens: u32,
    explanation: String,
    provenance: &[TransformProvenance],
) -> Result<(), telemetry::TelemetryError> {
    let store = TelemetryStore::open(db_path)?;
    store.init()?;
    store.insert_session(&SessionRecord {
        id: request.session_id.clone(),
        started_at: now_unix_string(),
        agent: "claude-code".to_string(),
        mode: request.reducer_mode.to_string(),
        cwd: request.cwd.clone(),
        metadata_json: serde_json::json!({
            "upstream_url": request.upstream_url,
            "classification": classification.class,
        })
        .to_string(),
    })?;
    store.record_transform(&TransformEvent {
        session_id: request.session_id.clone(),
        direction: "request".to_string(),
        reducer_kind: classification
            .reducer_kind
            .map(|kind| kind.to_string())
            .unwrap_or_else(|| "none".to_string()),
        mode: request.reducer_mode.to_string(),
        before_tokens,
        after_tokens,
        latency_ms: 0,
        explanation,
        provenance_json: serde_json::to_string(provenance).unwrap_or_else(|_| "[]".to_string()),
        created_at: now_unix_string(),
    })?;
    Ok(())
}

fn now_unix_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs().to_string())
        .unwrap_or_else(|_| "0".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    const STACK_TRACE: &str = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/stack-trace-node.txt"
    ));
    const TEST_LOG: &str = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/test-log-jest.txt"
    ));
    const LONG_PROMPT: &str = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/long-prompt.txt"
    ));

    #[test]
    fn classifies_stack_trace_not_config() {
        let registry = ReducerRegistry::default();
        let classification = classify_payload(&registry, STACK_TRACE, None);
        assert_eq!(
            classification.class,
            PayloadClass::StackTrace,
            "Stack trace was misclassified as {:?} with confidence {}",
            classification.class,
            classification.confidence
        );
    }

    #[test]
    fn intercepts_test_logs_and_updates_state() {
        let dir = tempdir().unwrap();
        let db_path = dir.path().join("telemetry.db");
        let state_path = dir.path().join("session.json");

        let response = intercept_request(ProxyRequest {
            session_id: "session-1".to_string(),
            content: TEST_LOG.to_string(),
            upstream_url: None,
            cwd: Some("/workspace".to_string()),
            reducer_hint: None,
            reducer_mode: ReductionMode::Safe,
            enable_prompt_linter: true,
            attach_session_memory: false,
            session_state_path: Some(state_path.display().to_string()),
            telemetry_db_path: Some(db_path.display().to_string()),
            protected_literals: Vec::new(),
        })
        .unwrap();

        assert!(response.transformed);
        assert!(response.content.contains("[context-os] 13 tests passed"));
        assert_eq!(response.classification.class, PayloadClass::TestLog);

        let saved = StructuredSessionMemory::load_from_path(&state_path).unwrap();
        assert!(!saved.tests_run.is_empty());
        assert!(saved.recent_turns.len() == 1);

        let store = TelemetryStore::open(&db_path).unwrap();
        let items = store.list_recent_transforms(10).unwrap();
        assert_eq!(items.len(), 1);
    }

    #[test]
    fn attaches_existing_session_memory_and_lints_prompt() {
        let dir = tempdir().unwrap();
        let state_path = dir.path().join("session.json");
        let mut state = StructuredSessionMemory::default();
        state.session_objective = Some("Ship Context OS".to_string());
        state.pin_fact("never silently rewrite code blocks");
        state.save_to_path(&state_path).unwrap();

        let response = intercept_request(ProxyRequest {
            session_id: "session-2".to_string(),
            content: LONG_PROMPT.to_string(),
            upstream_url: None,
            cwd: None,
            reducer_hint: None,
            reducer_mode: ReductionMode::Safe,
            enable_prompt_linter: true,
            attach_session_memory: true,
            session_state_path: Some(state_path.display().to_string()),
            telemetry_db_path: None,
            protected_literals: Vec::new(),
        })
        .unwrap();

        assert!(response.content.contains("[context-os session-memory]"));
        assert!(response.prompt_lint.is_some());
        assert!(response
            .notes
            .iter()
            .any(|note| note.contains("Prompt linter found")));
    }
}
