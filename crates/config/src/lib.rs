use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ReducerMode {
    Safe,
    Balanced,
    Aggressive,
}

impl Default for ReducerMode {
    fn default() -> Self {
        Self::Safe
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ResponseShaperMode {
    Off,
    Concise,
    ActionFirst,
}

impl Default for ResponseShaperMode {
    fn default() -> Self {
        Self::Off
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ReducerPolicy {
    pub enabled: bool,
    pub mode: ReducerMode,
    pub max_input_tokens: Option<u32>,
}

impl Default for ReducerPolicy {
    fn default() -> Self {
        Self {
            enabled: true,
            mode: ReducerMode::Safe,
            max_input_tokens: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(default)]
pub struct ReducerPolicies {
    pub stack_trace: ReducerPolicy,
    pub test_log: ReducerPolicy,
    pub build_log: ReducerPolicy,
    pub lint_output: ReducerPolicy,
    pub json: ReducerPolicy,
    pub config: ReducerPolicy,
    pub markdown: ReducerPolicy,
    pub csv: ReducerPolicy,
    pub nl_instruction: ReducerPolicy,
    pub conservative_code_context: ReducerPolicy,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ProtectionsConfig {
    pub preserve_code_blocks: bool,
    pub preserve_commands: bool,
    pub preserve_file_paths: bool,
    pub preserve_versions: bool,
    pub preserve_identifiers: bool,
    pub protected_literals: Vec<String>,
}

impl Default for ProtectionsConfig {
    fn default() -> Self {
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct RepoMemoryConfig {
    pub enabled: bool,
    pub artifact_dir: String,
    pub incremental: bool,
}

impl Default for RepoMemoryConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            artifact_dir: ".context-os/repo-memory".to_string(),
            incremental: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ResponseShapingConfig {
    pub enabled: bool,
    pub mode: ResponseShaperMode,
}

impl Default for ResponseShapingConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            mode: ResponseShaperMode::Off,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct TelemetryConfig {
    pub enabled: bool,
    pub database_path: String,
    pub retain_days: u32,
}

impl Default for TelemetryConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            database_path: "~/.context-os/context-os.db".to_string(),
            retain_days: 90,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct DashboardConfig {
    pub host: String,
    pub port: u16,
    pub open_browser: bool,
}

impl Default for DashboardConfig {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            port: 4319,
            open_browser: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ExperimentalFlags {
    pub balanced_json_arrays: bool,
    pub aggressive_response_shaper: bool,
}

impl Default for ExperimentalFlags {
    fn default() -> Self {
        Self {
            balanced_json_arrays: false,
            aggressive_response_shaper: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ContextOsConfig {
    pub mode: ReducerMode,
    pub reducers: ReducerPolicies,
    pub protections: ProtectionsConfig,
    pub pinned_constraints: Vec<String>,
    pub include_paths: Vec<String>,
    pub ignore_paths: Vec<String>,
    pub repo_memory: RepoMemoryConfig,
    pub response_shaping: ResponseShapingConfig,
    pub telemetry: TelemetryConfig,
    pub dashboard: DashboardConfig,
    pub experimental: ExperimentalFlags,
}

impl Default for ContextOsConfig {
    fn default() -> Self {
        Self {
            mode: ReducerMode::Safe,
            reducers: ReducerPolicies::default(),
            protections: ProtectionsConfig::default(),
            pinned_constraints: Vec::new(),
            include_paths: Vec::new(),
            ignore_paths: Vec::new(),
            repo_memory: RepoMemoryConfig::default(),
            response_shaping: ResponseShapingConfig::default(),
            telemetry: TelemetryConfig::default(),
            dashboard: DashboardConfig::default(),
            experimental: ExperimentalFlags::default(),
        }
    }
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("failed to read config at {path}: {source}")]
    Read {
        path: String,
        #[source]
        source: std::io::Error,
    },
    #[error("failed to parse config at {path}: {source}")]
    Parse {
        path: String,
        #[source]
        source: serde_json::Error,
    },
    #[error("invalid config: {0}")]
    Validation(String),
}

impl ContextOsConfig {
    pub fn from_json_str(json: &str) -> Result<Self, ConfigError> {
        let config = serde_json::from_str::<Self>(json).map_err(|source| ConfigError::Parse {
            path: "<inline>".to_string(),
            source,
        })?;
        config.validate()?;
        Ok(config)
    }

    pub fn load_from_path(path: impl AsRef<Path>) -> Result<Self, ConfigError> {
        let path_ref = path.as_ref();
        let content = fs::read_to_string(path_ref).map_err(|source| ConfigError::Read {
            path: path_ref.display().to_string(),
            source,
        })?;

        let config =
            serde_json::from_str::<Self>(&content).map_err(|source| ConfigError::Parse {
                path: path_ref.display().to_string(),
                source,
            })?;

        config.validate()?;
        Ok(config)
    }

    pub fn load_optional(path: impl AsRef<Path>) -> Result<Option<Self>, ConfigError> {
        let path_ref = path.as_ref();
        if !path_ref.exists() {
            return Ok(None);
        }

        Self::load_from_path(path_ref).map(Some)
    }

    pub fn merge(&self, overlay: &Self) -> Self {
        Self {
            mode: overlay.mode.clone(),
            reducers: overlay.reducers.clone(),
            protections: overlay.protections.clone(),
            pinned_constraints: merge_vec(&self.pinned_constraints, &overlay.pinned_constraints),
            include_paths: merge_vec(&self.include_paths, &overlay.include_paths),
            ignore_paths: merge_vec(&self.ignore_paths, &overlay.ignore_paths),
            repo_memory: overlay.repo_memory.clone(),
            response_shaping: overlay.response_shaping.clone(),
            telemetry: overlay.telemetry.clone(),
            dashboard: overlay.dashboard.clone(),
            experimental: overlay.experimental.clone(),
        }
    }

    pub fn load_merged(
        global_path: impl AsRef<Path>,
        project_path: impl AsRef<Path>,
    ) -> Result<Self, ConfigError> {
        let global = Self::load_optional(global_path)?.unwrap_or_default();
        let project = Self::load_optional(project_path)?.unwrap_or_default();
        let merged = global.merge(&project);
        merged.validate()?;
        Ok(merged)
    }

    pub fn validate(&self) -> Result<(), ConfigError> {
        if self.telemetry.retain_days == 0 {
            return Err(ConfigError::Validation(
                "telemetry.retain_days must be at least 1".to_string(),
            ));
        }

        if self.dashboard.port == 0 {
            return Err(ConfigError::Validation(
                "dashboard.port must be between 1 and 65535".to_string(),
            ));
        }

        Ok(())
    }
}

fn merge_vec(base: &[String], overlay: &[String]) -> Vec<String> {
    let mut merged = base.to_vec();
    for item in overlay {
        if !merged.contains(item) {
            merged.push(item.clone());
        }
    }
    merged
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_safe() {
        let config = ContextOsConfig::default();
        assert_eq!(config.mode, ReducerMode::Safe);
        assert!(config.protections.preserve_code_blocks);
        assert!(config.telemetry.enabled);
    }

    #[test]
    fn merge_prefers_overlay_and_keeps_unique_lists() {
        let base = ContextOsConfig {
            pinned_constraints: vec!["preserve API".to_string()],
            include_paths: vec!["src".to_string()],
            ..ContextOsConfig::default()
        };

        let overlay = ContextOsConfig {
            mode: ReducerMode::Balanced,
            pinned_constraints: vec!["preserve API".to_string(), "do not rewrite SQL".to_string()],
            include_paths: vec!["tests".to_string()],
            ..ContextOsConfig::default()
        };

        let merged = base.merge(&overlay);
        assert_eq!(merged.mode, ReducerMode::Balanced);
        assert_eq!(merged.pinned_constraints.len(), 2);
        assert!(merged.include_paths.contains(&"src".to_string()));
        assert!(merged.include_paths.contains(&"tests".to_string()));
    }

    #[test]
    fn rejects_invalid_retain_days() {
        let config = ContextOsConfig {
            telemetry: TelemetryConfig {
                retain_days: 0,
                ..TelemetryConfig::default()
            },
            ..ContextOsConfig::default()
        };

        let error = config.validate().unwrap_err();
        assert!(error
            .to_string()
            .contains("telemetry.retain_days must be at least 1"));
    }
}
