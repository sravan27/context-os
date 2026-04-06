use std::path::Path;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use thiserror::Error;

const SCHEMA_SQL: &str = include_str!("../sql/schema.sql");

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SessionRecord {
    pub id: String,
    pub started_at: String,
    pub agent: String,
    pub mode: String,
    pub cwd: Option<String>,
    pub metadata_json: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TransformEvent {
    pub session_id: String,
    pub direction: String,
    pub reducer_kind: String,
    pub mode: String,
    pub before_tokens: u32,
    pub after_tokens: u32,
    pub latency_ms: u64,
    pub explanation: String,
    pub provenance_json: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RecentTransform {
    pub session_id: String,
    pub reducer_kind: String,
    pub before_tokens: u32,
    pub after_tokens: u32,
    pub explanation: String,
    pub created_at: String,
}

#[derive(Debug, Error)]
pub enum TelemetryError {
    #[error("sqlite error: {0}")]
    Sqlite(#[from] rusqlite::Error),
}

pub struct TelemetryStore {
    connection: Connection,
}

impl TelemetryStore {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, TelemetryError> {
        let connection = Connection::open(path)?;
        Ok(Self { connection })
    }

    pub fn open_in_memory() -> Result<Self, TelemetryError> {
        let connection = Connection::open_in_memory()?;
        Ok(Self { connection })
    }

    pub fn init(&self) -> Result<(), TelemetryError> {
        self.connection.execute_batch(SCHEMA_SQL)?;
        Ok(())
    }

    pub fn insert_session(&self, session: &SessionRecord) -> Result<(), TelemetryError> {
        self.connection.execute(
            "INSERT OR REPLACE INTO sessions (id, started_at, agent, mode, cwd, metadata_json)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                session.id,
                session.started_at,
                session.agent,
                session.mode,
                session.cwd,
                session.metadata_json
            ],
        )?;
        Ok(())
    }

    pub fn record_transform(&self, event: &TransformEvent) -> Result<(), TelemetryError> {
        self.connection.execute(
            "INSERT INTO transform_events
              (session_id, direction, reducer_kind, mode, before_tokens, after_tokens, latency_ms, explanation, provenance_json, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
            params![
                event.session_id,
                event.direction,
                event.reducer_kind,
                event.mode,
                event.before_tokens,
                event.after_tokens,
                event.latency_ms,
                event.explanation,
                event.provenance_json,
                event.created_at
            ],
        )?;
        Ok(())
    }

    pub fn list_recent_transforms(
        &self,
        limit: usize,
    ) -> Result<Vec<RecentTransform>, TelemetryError> {
        let mut statement = self.connection.prepare(
            "SELECT session_id, reducer_kind, before_tokens, after_tokens, explanation, created_at
             FROM transform_events
             ORDER BY created_at DESC
             LIMIT ?1",
        )?;

        let rows = statement.query_map([limit as u32], |row| {
            Ok(RecentTransform {
                session_id: row.get(0)?,
                reducer_kind: row.get(1)?,
                before_tokens: row.get(2)?,
                after_tokens: row.get(3)?,
                explanation: row.get(4)?,
                created_at: row.get(5)?,
            })
        })?;

        let mut transforms = Vec::new();
        for row in rows {
            transforms.push(row?);
        }

        Ok(transforms)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn initializes_schema_and_persists_transform() {
        let store = TelemetryStore::open_in_memory().unwrap();
        store.init().unwrap();

        store
            .insert_session(&SessionRecord {
                id: "session-1".to_string(),
                started_at: "2026-04-05T10:00:00Z".to_string(),
                agent: "claude-code".to_string(),
                mode: "safe".to_string(),
                cwd: Some("/tmp/context-os".to_string()),
                metadata_json: "{}".to_string(),
            })
            .unwrap();

        store
            .record_transform(&TransformEvent {
                session_id: "session-1".to_string(),
                direction: "request".to_string(),
                reducer_kind: "test_log".to_string(),
                mode: "safe".to_string(),
                before_tokens: 120,
                after_tokens: 80,
                latency_ms: 4,
                explanation: "Collapsed passing test lines".to_string(),
                provenance_json: "[]".to_string(),
                created_at: "2026-04-05T10:00:01Z".to_string(),
            })
            .unwrap();

        let items = store.list_recent_transforms(10).unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].after_tokens, 80);
        assert_eq!(items[0].reducer_kind, "test_log");
    }
}
