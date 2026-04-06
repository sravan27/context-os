use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct DecisionRecord {
    pub summary: String,
    pub rationale: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CommandRecord {
    pub command: String,
    pub outcome: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct NextAction {
    pub summary: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PinnedFact {
    pub value: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RecentTurn {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct StructuredSessionMemory {
    pub schema_version: u32,
    pub session_objective: Option<String>,
    pub current_subtask: Option<String>,
    pub hard_constraints: Vec<String>,
    pub accepted_assumptions: Vec<String>,
    pub decisions_made: Vec<DecisionRecord>,
    pub modified_files: Vec<String>,
    pub tests_run: Vec<CommandRecord>,
    pub failing_signatures: Vec<String>,
    pub failed_approaches: Vec<String>,
    pub pending_next_actions: Vec<NextAction>,
    pub pinned_facts: Vec<PinnedFact>,
    pub recent_turns: Vec<RecentTurn>,
    pub compaction_count: u32,
}

impl Default for StructuredSessionMemory {
    fn default() -> Self {
        Self {
            schema_version: 1,
            session_objective: None,
            current_subtask: None,
            hard_constraints: Vec::new(),
            accepted_assumptions: Vec::new(),
            decisions_made: Vec::new(),
            modified_files: Vec::new(),
            tests_run: Vec::new(),
            failing_signatures: Vec::new(),
            failed_approaches: Vec::new(),
            pending_next_actions: Vec::new(),
            pinned_facts: Vec::new(),
            recent_turns: Vec::new(),
            compaction_count: 0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(default)]
pub struct SessionMemoryUpdate {
    pub session_objective: Option<String>,
    pub current_subtask: Option<String>,
    pub hard_constraints: Vec<String>,
    pub accepted_assumptions: Vec<String>,
    pub decisions_made: Vec<DecisionRecord>,
    pub modified_files: Vec<String>,
    pub tests_run: Vec<CommandRecord>,
    pub failing_signatures: Vec<String>,
    pub failed_approaches: Vec<String>,
    pub pending_next_actions: Vec<NextAction>,
    pub pinned_facts: Vec<PinnedFact>,
    pub recent_turns: Vec<RecentTurn>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SessionCompactionPolicy {
    pub max_recent_turns: usize,
    pub max_tests_run: usize,
    pub max_failed_approaches: usize,
    pub max_pending_next_actions: usize,
}

impl Default for SessionCompactionPolicy {
    fn default() -> Self {
        Self {
            max_recent_turns: 6,
            max_tests_run: 12,
            max_failed_approaches: 12,
            max_pending_next_actions: 8,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct SessionCompactionResult {
    pub removed_recent_turns: usize,
    pub removed_tests_run: usize,
    pub removed_failed_approaches: usize,
    pub removed_pending_next_actions: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct SessionMemoryDiff {
    pub session_objective_before: Option<String>,
    pub session_objective_after: Option<String>,
    pub current_subtask_before: Option<String>,
    pub current_subtask_after: Option<String>,
    pub added_hard_constraints: Vec<String>,
    pub added_assumptions: Vec<String>,
    pub added_decisions: Vec<DecisionRecord>,
    pub added_modified_files: Vec<String>,
    pub added_tests_run: Vec<CommandRecord>,
    pub added_failing_signatures: Vec<String>,
    pub added_failed_approaches: Vec<String>,
    pub added_pending_next_actions: Vec<NextAction>,
    pub added_pinned_facts: Vec<PinnedFact>,
    pub added_recent_turns: Vec<RecentTurn>,
    pub compaction_delta: i64,
}

#[derive(Debug, Error)]
pub enum SessionMemoryError {
    #[error("failed to read session memory at {path}: {source}")]
    Read {
        path: String,
        #[source]
        source: std::io::Error,
    },
    #[error("failed to write session memory at {path}: {source}")]
    Write {
        path: String,
        #[source]
        source: std::io::Error,
    },
    #[error("failed to serialize session memory: {0}")]
    Serialize(#[from] serde_json::Error),
}

impl StructuredSessionMemory {
    pub fn merge_update(&mut self, update: SessionMemoryUpdate) {
        if update.session_objective.is_some() {
            self.session_objective = update.session_objective;
        }
        if update.current_subtask.is_some() {
            self.current_subtask = update.current_subtask;
        }

        extend_unique(&mut self.hard_constraints, update.hard_constraints);
        extend_unique(&mut self.accepted_assumptions, update.accepted_assumptions);
        extend_unique_decisions(&mut self.decisions_made, update.decisions_made);
        extend_unique(&mut self.modified_files, update.modified_files);
        extend_unique_commands(&mut self.tests_run, update.tests_run);
        extend_unique(&mut self.failing_signatures, update.failing_signatures);
        extend_unique(&mut self.failed_approaches, update.failed_approaches);
        extend_unique_actions(&mut self.pending_next_actions, update.pending_next_actions);
        extend_unique_facts(&mut self.pinned_facts, update.pinned_facts);
        extend_unique_turns(&mut self.recent_turns, update.recent_turns);
    }

    pub fn pin_fact(&mut self, fact: impl Into<String>) {
        let fact = PinnedFact { value: fact.into() };
        if !self.pinned_facts.contains(&fact) {
            self.pinned_facts.push(fact);
        }
    }

    pub fn compact(&mut self, policy: &SessionCompactionPolicy) -> SessionCompactionResult {
        let removed_recent_turns =
            truncate_to_recent(&mut self.recent_turns, policy.max_recent_turns);
        let removed_tests_run = truncate_to_recent(&mut self.tests_run, policy.max_tests_run);
        let removed_failed_approaches =
            truncate_to_recent(&mut self.failed_approaches, policy.max_failed_approaches);
        let removed_pending_next_actions = truncate_to_recent(
            &mut self.pending_next_actions,
            policy.max_pending_next_actions,
        );

        let result = SessionCompactionResult {
            removed_recent_turns,
            removed_tests_run,
            removed_failed_approaches,
            removed_pending_next_actions,
        };

        if result != SessionCompactionResult::default() {
            self.compaction_count += 1;
        }

        result
    }

    pub fn export_json(&self) -> Result<String, SessionMemoryError> {
        serde_json::to_string_pretty(self).map_err(SessionMemoryError::Serialize)
    }

    pub fn import_json(input: &str) -> Result<Self, SessionMemoryError> {
        serde_json::from_str(input).map_err(SessionMemoryError::Serialize)
    }

    pub fn save_to_path(&self, path: impl AsRef<Path>) -> Result<(), SessionMemoryError> {
        let path_ref = path.as_ref();
        let json = self.export_json()?;
        if let Some(parent) = path_ref.parent() {
            fs::create_dir_all(parent).map_err(|source| SessionMemoryError::Write {
                path: parent.display().to_string(),
                source,
            })?;
        }
        fs::write(path_ref, json).map_err(|source| SessionMemoryError::Write {
            path: path_ref.display().to_string(),
            source,
        })?;
        Ok(())
    }

    pub fn load_from_path(path: impl AsRef<Path>) -> Result<Self, SessionMemoryError> {
        let path_ref = path.as_ref();
        let content = fs::read_to_string(path_ref).map_err(|source| SessionMemoryError::Read {
            path: path_ref.display().to_string(),
            source,
        })?;
        Self::import_json(&content)
    }

    pub fn load_or_default(path: impl AsRef<Path>) -> Result<Self, SessionMemoryError> {
        let path_ref = path.as_ref();
        if !path_ref.exists() {
            return Ok(Self::default());
        }
        Self::load_from_path(path_ref)
    }
}

pub fn export_session_state(
    memory: &StructuredSessionMemory,
) -> Result<String, SessionMemoryError> {
    memory.export_json()
}

pub fn import_session_state(input: &str) -> Result<StructuredSessionMemory, SessionMemoryError> {
    StructuredSessionMemory::import_json(input)
}

pub fn update_structured_memory(memory: &mut StructuredSessionMemory, update: SessionMemoryUpdate) {
    memory.merge_update(update);
}

pub fn compact_session(
    memory: &mut StructuredSessionMemory,
    policy: &SessionCompactionPolicy,
) -> SessionCompactionResult {
    memory.compact(policy)
}

pub fn diff_memory_states(
    before: &StructuredSessionMemory,
    after: &StructuredSessionMemory,
) -> SessionMemoryDiff {
    SessionMemoryDiff {
        session_objective_before: before.session_objective.clone(),
        session_objective_after: after.session_objective.clone(),
        current_subtask_before: before.current_subtask.clone(),
        current_subtask_after: after.current_subtask.clone(),
        added_hard_constraints: difference(&before.hard_constraints, &after.hard_constraints),
        added_assumptions: difference(&before.accepted_assumptions, &after.accepted_assumptions),
        added_decisions: difference_structured(&before.decisions_made, &after.decisions_made),
        added_modified_files: difference(&before.modified_files, &after.modified_files),
        added_tests_run: difference_structured(&before.tests_run, &after.tests_run),
        added_failing_signatures: difference(&before.failing_signatures, &after.failing_signatures),
        added_failed_approaches: difference(&before.failed_approaches, &after.failed_approaches),
        added_pending_next_actions: difference_structured(
            &before.pending_next_actions,
            &after.pending_next_actions,
        ),
        added_pinned_facts: difference_structured(&before.pinned_facts, &after.pinned_facts),
        added_recent_turns: difference_structured(&before.recent_turns, &after.recent_turns),
        compaction_delta: after.compaction_count as i64 - before.compaction_count as i64,
    }
}

fn truncate_to_recent<T>(items: &mut Vec<T>, max_items: usize) -> usize {
    if items.len() <= max_items {
        return 0;
    }
    let removed = items.len() - max_items;
    items.drain(0..removed);
    removed
}

fn extend_unique(target: &mut Vec<String>, items: Vec<String>) {
    for item in items {
        if !target.contains(&item) {
            target.push(item);
        }
    }
}

fn extend_unique_decisions(target: &mut Vec<DecisionRecord>, items: Vec<DecisionRecord>) {
    for item in items {
        if !target.contains(&item) {
            target.push(item);
        }
    }
}

fn extend_unique_commands(target: &mut Vec<CommandRecord>, items: Vec<CommandRecord>) {
    for item in items {
        if !target.contains(&item) {
            target.push(item);
        }
    }
}

fn extend_unique_actions(target: &mut Vec<NextAction>, items: Vec<NextAction>) {
    for item in items {
        if !target.contains(&item) {
            target.push(item);
        }
    }
}

fn extend_unique_facts(target: &mut Vec<PinnedFact>, items: Vec<PinnedFact>) {
    for item in items {
        if !target.contains(&item) {
            target.push(item);
        }
    }
}

fn extend_unique_turns(target: &mut Vec<RecentTurn>, items: Vec<RecentTurn>) {
    for item in items {
        if !target.contains(&item) {
            target.push(item);
        }
    }
}

fn difference<T>(before: &[T], after: &[T]) -> Vec<T>
where
    T: Clone + PartialEq,
{
    after
        .iter()
        .filter(|item| !before.contains(item))
        .cloned()
        .collect()
}

fn difference_structured<T>(before: &[T], after: &[T]) -> Vec<T>
where
    T: Clone + PartialEq,
{
    difference(before, after)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn merges_without_duplicate_facts() {
        let mut memory = StructuredSessionMemory::default();
        memory.pin_fact("never rewrite migrations");
        memory.merge_update(SessionMemoryUpdate {
            pinned_facts: vec![PinnedFact {
                value: "never rewrite migrations".to_string(),
            }],
            modified_files: vec!["src/main.rs".to_string()],
            ..SessionMemoryUpdate::default()
        });

        assert_eq!(memory.pinned_facts.len(), 1);
        assert_eq!(memory.modified_files, vec!["src/main.rs".to_string()]);
    }

    #[test]
    fn exports_and_imports_json() {
        let memory = StructuredSessionMemory {
            session_objective: Some("reduce noisy test logs".to_string()),
            ..StructuredSessionMemory::default()
        };

        let json = memory.export_json().unwrap();
        let round_trip = StructuredSessionMemory::import_json(&json).unwrap();
        assert_eq!(
            round_trip.session_objective.as_deref(),
            Some("reduce noisy test logs")
        );
    }

    #[test]
    fn compacts_recent_entries_without_touching_structured_state() {
        let mut memory = StructuredSessionMemory::default();
        for idx in 0..10 {
            memory.recent_turns.push(RecentTurn {
                role: "user".to_string(),
                content: format!("turn-{idx}"),
            });
            memory.tests_run.push(CommandRecord {
                command: format!("cargo test --case {idx}"),
                outcome: Some("ok".to_string()),
            });
        }

        let result = memory.compact(&SessionCompactionPolicy {
            max_recent_turns: 4,
            max_tests_run: 3,
            max_failed_approaches: 12,
            max_pending_next_actions: 8,
        });

        assert_eq!(result.removed_recent_turns, 6);
        assert_eq!(result.removed_tests_run, 7);
        assert_eq!(memory.recent_turns.first().unwrap().content, "turn-6");
        assert_eq!(memory.tests_run.len(), 3);
        assert_eq!(memory.compaction_count, 1);
    }

    #[test]
    fn diffs_added_entries() {
        let before = StructuredSessionMemory::default();
        let mut after = StructuredSessionMemory::default();
        after.merge_update(SessionMemoryUpdate {
            hard_constraints: vec!["safe mode by default".to_string()],
            pending_next_actions: vec![NextAction {
                summary: "wire proxy telemetry".to_string(),
            }],
            ..SessionMemoryUpdate::default()
        });

        let diff = diff_memory_states(&before, &after);
        assert_eq!(diff.added_hard_constraints, vec!["safe mode by default"]);
        assert_eq!(diff.added_pending_next_actions.len(), 1);
    }

    #[test]
    fn saves_and_loads_from_disk() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("state.json");
        let mut memory = StructuredSessionMemory::default();
        memory.pin_fact("keep shell commands exact");
        memory.save_to_path(&path).unwrap();

        let loaded = StructuredSessionMemory::load_from_path(&path).unwrap();
        assert_eq!(loaded.pinned_facts.len(), 1);
    }
}
