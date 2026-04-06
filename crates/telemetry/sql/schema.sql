PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  agent TEXT NOT NULL,
  mode TEXT NOT NULL,
  cwd TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS transform_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  direction TEXT NOT NULL,
  reducer_kind TEXT NOT NULL,
  mode TEXT NOT NULL,
  before_tokens INTEGER NOT NULL,
  after_tokens INTEGER NOT NULL,
  latency_ms INTEGER NOT NULL,
  explanation TEXT NOT NULL,
  provenance_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS compaction_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  before_tokens INTEGER NOT NULL,
  after_tokens INTEGER NOT NULL,
  notes TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  benchmark_name TEXT NOT NULL,
  mode TEXT NOT NULL,
  reduction_pct REAL NOT NULL,
  preservation_score REAL NOT NULL,
  quality_score REAL NOT NULL,
  report_path TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repo_memory_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  artifact_kind TEXT NOT NULL,
  freshness_seconds INTEGER,
  hit INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_transform_events_session_created
  ON transform_events(session_id, created_at DESC);
