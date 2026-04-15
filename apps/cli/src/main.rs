use std::fs;
use std::io::Read as IoRead;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use clap::{Args, Parser, Subcommand, ValueEnum};
use config::ContextOsConfig;
use prompt_linter::analyze_prompt;
use proxy_core::{intercept_request, ProxyRequest};
use reducer_engine::{ProtectionRules, ReducerKind, ReducerRegistry, ReductionMode};
use repo_memory::{build_and_write, build_repo_memory, render_claude_md};
use serde::Serialize;
use session_memory::{
    compact_session, diff_memory_states, export_session_state, update_structured_memory,
    CommandRecord, DecisionRecord, NextAction, PinnedFact, RecentTurn, SessionCompactionPolicy,
    SessionMemoryDiff, SessionMemoryUpdate, StructuredSessionMemory,
};
use telemetry::TelemetryStore;
use token_estimator::{estimate_text, ModelFamily};

#[derive(Parser)]
#[command(name = "context-os")]
#[command(about = "Typed context reduction and structured memory for AI coding workflows")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Scan repo and generate CLAUDE.md + hooks for Claude Code integration
    Init(InitArgs),
    /// Print compact context for injection into every Claude Code turn
    Status(StatusArgs),
    /// Read stdin, auto-detect content type, reduce, write to stdout
    Pipe(PipeArgs),
    /// Save session state for handoff to a new session when hitting usage limits
    Handoff(HandoffArgs),
    /// Print the deterministic restart packet used for compaction recovery
    Resume(ResumeArgs),
    Estimate(EstimateArgs),
    Reduce(ReduceArgs),
    PromptLint(PromptLintArgs),
    Index(IndexArgs),
    Inspect(InspectArgs),
    Intercept(InterceptCommand),
    Session(SessionCommand),
    Config(ConfigCommand),
    Telemetry(TelemetryCommand),
    /// Validate setup and show what Context OS is doing for you
    Doctor(DoctorArgs),
    /// Handle Claude Code hook events (used internally by hooks)
    Hook(HookCommand),
}

#[derive(Args)]
struct InitArgs {
    #[arg(long, default_value = ".")]
    root: PathBuf,
    /// Skip writing CLAUDE.md
    #[arg(long, default_value_t = false)]
    no_claude_md: bool,
    /// Skip installing Claude Code hooks
    #[arg(long, default_value_t = false)]
    no_hooks: bool,
}

#[derive(Args)]
struct StatusArgs {
    #[arg(long, default_value = ".")]
    root: PathBuf,
}

#[derive(Args)]
struct PipeArgs {
    /// Force a specific reducer kind instead of auto-detecting
    #[arg(long)]
    kind: Option<String>,
    #[arg(long, default_value = "safe")]
    mode: String,
    /// Output raw reduced text only (no JSON wrapper)
    #[arg(long, default_value_t = true)]
    raw: bool,
}

#[derive(Args)]
struct HandoffArgs {
    #[arg(long, default_value = ".")]
    root: PathBuf,
    /// What was being worked on (if not in session state already)
    #[arg(long)]
    objective: Option<String>,
    /// What to do next
    #[arg(long)]
    next: Option<String>,
    /// Pin a critical fact for the next session
    #[arg(long)]
    pin: Vec<String>,
}

#[derive(Args)]
struct ResumeArgs {
    #[arg(long, default_value = ".")]
    root: PathBuf,
    /// Maximum estimated Claude tokens for the restart packet
    #[arg(long, default_value_t = 600)]
    max_tokens: usize,
}

#[derive(Args)]
struct EstimateArgs {
    #[arg(long)]
    input: PathBuf,
    #[arg(long, value_enum, default_value_t = ModelOption::Claude)]
    model: ModelOption,
}

#[derive(Args)]
struct ReduceArgs {
    #[arg(long)]
    kind: String,
    #[arg(long)]
    input: PathBuf,
    #[arg(long, default_value = "safe")]
    mode: String,
}

#[derive(Args)]
struct PromptLintArgs {
    #[arg(long)]
    input: PathBuf,
}

#[derive(Args)]
struct IndexArgs {
    #[arg(long, default_value = ".")]
    root: PathBuf,
    #[arg(long, default_value = ".context-os/repo-memory")]
    out: PathBuf,
}

#[derive(Args)]
struct InspectArgs {
    #[arg(long, default_value = ".")]
    root: PathBuf,
}

#[derive(Subcommand)]
enum InterceptSubcommand {
    Request {
        #[arg(long)]
        session_id: String,
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        reducer_kind: Option<String>,
        #[arg(long, default_value = "safe")]
        mode: String,
        #[arg(long, default_value_t = true)]
        prompt_linter: bool,
        #[arg(long, default_value_t = false)]
        attach_session_memory: bool,
        #[arg(long)]
        session_state: Option<PathBuf>,
        #[arg(long)]
        telemetry_db: Option<PathBuf>,
        #[arg(long)]
        upstream_url: Option<String>,
    },
}

#[derive(Args)]
struct InterceptCommand {
    #[command(subcommand)]
    command: InterceptSubcommand,
}

#[derive(Subcommand)]
enum SessionSubcommand {
    Update {
        #[arg(long)]
        state: PathBuf,
        #[arg(long)]
        update: PathBuf,
    },
    Pin {
        #[arg(long)]
        state: PathBuf,
        #[arg(long)]
        fact: String,
    },
    Export {
        #[arg(long)]
        state: PathBuf,
    },
    Diff {
        #[arg(long)]
        before: PathBuf,
        #[arg(long)]
        after: PathBuf,
    },
    Compact {
        #[arg(long)]
        state: PathBuf,
        #[arg(long, default_value_t = 6)]
        max_recent_turns: usize,
        #[arg(long, default_value_t = 12)]
        max_tests_run: usize,
        #[arg(long, default_value_t = 12)]
        max_failed_approaches: usize,
        #[arg(long, default_value_t = 8)]
        max_pending_next_actions: usize,
    },
}

#[derive(Args)]
struct SessionCommand {
    #[command(subcommand)]
    command: SessionSubcommand,
}

#[derive(Subcommand)]
enum ConfigSubcommand {
    Validate {
        #[arg(long)]
        path: PathBuf,
    },
}

#[derive(Args)]
struct ConfigCommand {
    #[command(subcommand)]
    command: ConfigSubcommand,
}

#[derive(Subcommand)]
enum TelemetrySubcommand {
    Init {
        #[arg(long, default_value = ".context-os.db")]
        db: PathBuf,
    },
}

#[derive(Args)]
struct TelemetryCommand {
    #[command(subcommand)]
    command: TelemetrySubcommand,
}

#[derive(Args)]
struct DoctorArgs {
    #[arg(long, default_value = ".")]
    root: PathBuf,
}

#[derive(Subcommand)]
enum HookSubcommand {
    /// Handle PreToolUse events — wraps Bash commands to reduce output automatically
    PreToolUse,
    /// Handle PostToolUse events — extract decisions from tool output
    PostToolUse,
    /// Handle PreCompact events — inject decisions so they survive compaction
    PreCompact,
}

#[derive(Args)]
struct HookCommand {
    #[command(subcommand)]
    command: HookSubcommand,
}

#[derive(Clone, Copy, ValueEnum)]
enum ModelOption {
    Claude,
    Codex,
    Gemini,
    Generic,
}

impl From<ModelOption> for ModelFamily {
    fn from(value: ModelOption) -> Self {
        match value {
            ModelOption::Claude => ModelFamily::Claude,
            ModelOption::Codex => ModelFamily::Codex,
            ModelOption::Gemini => ModelFamily::Gemini,
            ModelOption::Generic => ModelFamily::Generic,
        }
    }
}

#[derive(Serialize)]
struct ReduceOutput {
    output: String,
    metadata: reducer_engine::ReductionMetadata,
}

#[derive(Serialize)]
struct SessionUpdateOutput {
    state: StructuredSessionMemory,
    diff: SessionMemoryDiff,
}

#[derive(Debug, Clone)]
struct RestartPacketPolicy {
    max_tokens: usize,
    max_recent_turns: usize,
    max_tests_run: usize,
    max_failed_approaches: usize,
    max_decisions: usize,
    max_modified_files: usize,
    max_pending_next_actions: usize,
}

impl Default for RestartPacketPolicy {
    fn default() -> Self {
        Self {
            max_tokens: 600,
            max_recent_turns: 6,
            max_tests_run: 8,
            max_failed_approaches: 8,
            max_decisions: 8,
            max_modified_files: 12,
            max_pending_next_actions: 6,
        }
    }
}

#[derive(Debug, Clone, Default)]
struct RestartPacket {
    session_objective: Option<String>,
    current_subtask: Option<String>,
    decisions_made: Vec<DecisionRecord>,
    failed_approaches: Vec<String>,
    failing_signatures: Vec<String>,
    modified_files: Vec<String>,
    pending_next_actions: Vec<NextAction>,
    pinned_facts: Vec<PinnedFact>,
    hard_constraints: Vec<String>,
    tests_run: Vec<CommandRecord>,
    recent_turns: Vec<RecentTurn>,
}

#[derive(Debug, Serialize)]
struct JournalEvent {
    ts_unix: u64,
    hook: String,
    category: String,
    summary: String,
    metadata: serde_json::Value,
}

#[derive(Debug, Default)]
struct HookProcessingResult {
    changed: bool,
    journal_events: Vec<JournalEvent>,
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Init(args) => run_init(args),
        Commands::Status(args) => run_status(args),
        Commands::Pipe(args) => run_pipe(args),
        Commands::Handoff(args) => run_handoff(args),
        Commands::Resume(args) => run_resume(args),
        Commands::Estimate(args) => run_estimate(args),
        Commands::Reduce(args) => run_reduce(args),
        Commands::PromptLint(args) => run_prompt_lint(args),
        Commands::Index(args) => run_index(args),
        Commands::Inspect(args) => run_inspect(args),
        Commands::Intercept(command) => run_intercept(command),
        Commands::Session(command) => run_session(command),
        Commands::Config(command) => run_config(command),
        Commands::Telemetry(command) => run_telemetry(command),
        Commands::Doctor(args) => run_doctor(args),
        Commands::Hook(command) => run_hook(command),
    }
}

fn run_init(args: InitArgs) -> Result<()> {
    let root = fs::canonicalize(&args.root)
        .with_context(|| format!("failed to resolve {}", args.root.display()))?;

    let context_dir = root.join(".context-os");
    fs::create_dir_all(&context_dir)?;
    ensure_session_state_files(&root)?;

    // 1. Build repo memory
    let out_dir = context_dir.join("repo-memory");
    let artifacts = build_and_write(&root, &out_dir)?;
    eprintln!(
        "indexed {} source files, {} configs",
        artifacts.architecture.source_file_count, artifacts.architecture.config_file_count
    );

    // 2. Generate / append CLAUDE.md
    if !args.no_claude_md {
        let repo_map = render_claude_md(&artifacts);
        let claude_md_path = root.join("CLAUDE.md");
        let marker_start = "<!-- context-os:start -->";
        let marker_end = "<!-- context-os:end -->";
        let block = format!("{marker_start}\n{repo_map}{marker_end}");

        if claude_md_path.exists() {
            let existing = fs::read_to_string(&claude_md_path)?;
            if existing.contains(marker_start) {
                // Replace existing block
                let before = existing
                    .split(marker_start)
                    .next()
                    .unwrap_or("")
                    .to_string();
                let after = existing.split(marker_end).nth(1).unwrap_or("").to_string();
                fs::write(&claude_md_path, format!("{before}{block}{after}"))?;
                eprintln!("updated context-os block in CLAUDE.md");
            } else {
                // Append
                fs::write(
                    &claude_md_path,
                    format!("{}\n\n{block}\n", existing.trim_end()),
                )?;
                eprintln!("appended repo map to CLAUDE.md");
            }
        } else {
            fs::write(&claude_md_path, format!("{block}\n"))?;
            eprintln!("created CLAUDE.md with repo map");
        }
    }

    // 3. Install Claude Code hooks for resilience and typed tool reduction
    if !args.no_hooks {
        let claude_dir = root.join(".claude");
        fs::create_dir_all(&claude_dir)?;

        let settings_path = claude_dir.join("settings.local.json");
        let mut settings: serde_json::Value = if settings_path.exists() {
            let content = fs::read_to_string(&settings_path)?;
            serde_json::from_str(&content).unwrap_or(serde_json::json!({}))
        } else {
            serde_json::json!({})
        };

        let handoff_path = context_dir.join("handoff.md").display().to_string();

        // Find the context-os binary
        let bin_path = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("context-os"));
        let bin = bin_path.display().to_string();

        let hooks = serde_json::json!({
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": format!("{bin} hook pre-tool-use"),
                            "timeout": 2
                        }
                    ]
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": format!("{bin} hook post-tool-use"),
                            "timeout": 5
                        }
                    ]
                },
                {
                    "matcher": "Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": format!("{bin} hook post-tool-use"),
                            "timeout": 5
                        }
                    ]
                },
                {
                    "matcher": "Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": format!("{bin} hook post-tool-use"),
                            "timeout": 5
                        }
                    ]
                }
            ],
            "PreCompact": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": format!(
                                "{bin} hook pre-compact 2>/dev/null || true"
                            ),
                            "timeout": 5
                        }
                    ]
                }
            ],
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": format!(
                                "{bin} resume --root \"{}\" 2>/dev/null || cat \"{handoff_path}\" 2>/dev/null || true",
                                root.display()
                            ),
                            "timeout": 5
                        }
                    ]
                }
            ],
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": format!(
                                "{bin} handoff --root \"{}\" 2>/dev/null || true",
                                root.display()
                            ),
                            "timeout": 10,
                            "async": true
                        }
                    ]
                }
            ]
        });

        settings["hooks"] = hooks;
        fs::write(&settings_path, serde_json::to_string_pretty(&settings)?)?;
        eprintln!("installed hooks in .claude/settings.local.json");

        // 3b. Install shared settings.json with env tuning
        let shared_settings_path = claude_dir.join("settings.json");
        let mut shared: serde_json::Value = if shared_settings_path.exists() {
            let content = fs::read_to_string(&shared_settings_path)?;
            serde_json::from_str(&content).unwrap_or(serde_json::json!({}))
        } else {
            serde_json::json!({})
        };
        if !shared.get("env").and_then(|e| e.get("MAX_THINKING_TOKENS")).is_some() {
            let env = shared.as_object_mut()
                .and_then(|m| {
                    if !m.contains_key("env") {
                        m.insert("env".to_string(), serde_json::json!({}));
                    }
                    m.get_mut("env")
                })
                .and_then(|e| e.as_object_mut());
            if let Some(env) = env {
                env.insert("MAX_THINKING_TOKENS".to_string(), serde_json::json!("8000"));
                env.insert("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE".to_string(), serde_json::json!("80"));
            }
            fs::write(&shared_settings_path, serde_json::to_string_pretty(&shared)?)?;
            eprintln!("installed env tuning in .claude/settings.json");
        }

        // 3c. Install slash commands
        let commands_dir = claude_dir.join("commands");
        fs::create_dir_all(&commands_dir)?;
        let compact_cmd = "Write a handoff to `.context-os/handoff.md`:\n\n\
            1. **Objective**: What we're building (1 line)\n\
            2. **Done**: What's completed (bullet list, file:line refs)\n\
            3. **Failed**: What didn't work and why (so we don't retry)\n\
            4. **Next**: Exact next step to take\n\
            5. **Modified files**: List every file changed this session\n\n\
            Keep it under 40 lines. No prose. Start with `[context-os handoff]`.\n\
            Then say: \"Handoff saved. Start a new session — I'll pick up from here.\"\n";
        let compact_path = commands_dir.join("compact.md");
        if !compact_path.exists() {
            fs::write(&compact_path, compact_cmd)?;
        }
        let context_cmd = "Estimate your current context usage:\n\
            1. Count files you've read this session\n\
            2. Count tool calls made\n\
            3. List the 3 largest tool outputs you've seen\n\
            4. Suggest what to compact or skip\n\n\
            Table format. Under 10 lines. No explanations.\n";
        let context_path = commands_dir.join("context.md");
        if !context_path.exists() {
            fs::write(&context_path, context_cmd)?;
        }
        let ship_cmd = "Ship the current changes:\n\
            1. Run tests (once). If they fail, show the failure and stop.\n\
            2. Stage only modified files (not untracked).\n\
            3. Commit with a 1-line message describing what changed.\n\
            4. Show the commit hash.\n\n\
            No explanations. No celebration. Just ship or fail.\n";
        let ship_path = commands_dir.join("ship.md");
        if !ship_path.exists() {
            fs::write(&ship_path, ship_cmd)?;
        }
        eprintln!("installed 3 slash commands in .claude/commands/");

        // 3d. Install explorer subagent (Haiku-powered)
        let agents_dir = claude_dir.join("agents");
        fs::create_dir_all(&agents_dir)?;
        let explorer_agent = "---\n\
            name: explorer\n\
            description: Fast file/code exploration agent. Use when searching for symbols, reading multiple files to understand structure, or investigating usage patterns. Returns a summary, not raw files.\n\
            model: haiku\n\
            ---\n\n\
            You are a code exploration agent running on Claude Haiku (fast, cheap).\n\n\
            Your job: answer exploration questions without polluting the main context.\n\n\
            Rules:\n\
            - Read files with Grep/Glob first, Read only when needed\n\
            - Use offset/limit when reading large files\n\
            - Return a summary (≤500 tokens), not raw file content\n\
            - Include file paths and line numbers (file.ts:42 format)\n\
            - If you can't find what was asked, say so in 1 line\n\n\
            Never:\n\
            - Write or edit files (you're read-only)\n\
            - Explain your reasoning\n\
            - Return full file contents unless explicitly asked\n";
        let explorer_path = agents_dir.join("explorer.md");
        if !explorer_path.exists() {
            fs::write(&explorer_path, explorer_agent)?;
        }
        eprintln!("installed explorer subagent (Haiku)");
    }

    // 4. Ensure .context-os/ is in .gitignore
    let gitignore_path = root.join(".gitignore");
    if gitignore_path.exists() {
        let content = fs::read_to_string(&gitignore_path)?;
        if !content.contains(".context-os/") {
            fs::write(
                &gitignore_path,
                format!(
                    "{}\n\n# Context OS local state\n.context-os/\n",
                    content.trim_end()
                ),
            )?;
            eprintln!("added .context-os/ to .gitignore");
        }
    } else {
        fs::write(&gitignore_path, "# Context OS local state\n.context-os/\n")?;
        eprintln!("created .gitignore with .context-os/");
    }

    // 5. Generate .claudeignore to prevent Claude from searching irrelevant dirs
    let claudeignore_path = root.join(".claudeignore");
    if !claudeignore_path.exists() {
        let mut ignores = Vec::new();
        // Auto-detect common noise directories
        let noise_dirs = [
            "node_modules",
            ".next",
            "dist",
            "build",
            "out",
            "target/debug",
            "target/release",
            "__pycache__",
            ".venv",
            "venv",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
            "coverage",
            ".nyc_output",
            ".gradle",
            ".idea",
            ".vs",
            ".vscode",
            "vendor",
            "Pods",
            ".dart_tool",
            ".flutter-plugins",
            ".git/objects",
            ".turbo",
            ".parcel-cache",
            ".cache",
        ];
        // Always include standard noise patterns (cover future-created dirs like
        // node_modules after `npm install`, target/ after `cargo build`, etc.)
        for dir in &noise_dirs {
            ignores.push(format!("{dir}/"));
        }
        // Secrets (security + tokens)
        ignores.push(".env".to_string());
        ignores.push(".env.*".to_string());
        ignores.push("!.env.example".to_string());
        ignores.push("!.env.sample".to_string());
        ignores.push("*.pem".to_string());
        ignores.push("*.key".to_string());
        ignores.push("credentials.json".to_string());
        ignores.push("secrets.json".to_string());
        ignores.push("id_rsa".to_string());
        ignores.push("id_ed25519".to_string());
        // Lock files
        ignores.push("*.lock".to_string());
        ignores.push("package-lock.json".to_string());
        ignores.push("yarn.lock".to_string());
        ignores.push("pnpm-lock.yaml".to_string());
        ignores.push("Cargo.lock".to_string());
        ignores.push("poetry.lock".to_string());
        ignores.push("Gemfile.lock".to_string());
        ignores.push("bun.lockb".to_string());
        // Build artifacts
        ignores.push("*.min.js".to_string());
        ignores.push("*.min.css".to_string());
        ignores.push("*.map".to_string());
        ignores.push("*.chunk.js".to_string());
        ignores.push("*.bundle.js".to_string());
        ignores.push("*.wasm".to_string());
        // Generated code
        ignores.push("*.pb.go".to_string());
        ignores.push("*.generated.*".to_string());
        ignores.push("*.g.dart".to_string());
        ignores.push("*.snap".to_string());
        ignores.push(".context-os/".to_string());

        if !ignores.is_empty() {
            let content = format!(
                "# Generated by context-os — prevents Claude from searching noisy dirs\n{}\n",
                ignores.join("\n")
            );
            fs::write(&claudeignore_path, content)?;
            eprintln!("created .claudeignore ({} patterns)", ignores.len());
        }
    }

    eprintln!("done.");
    Ok(())
}

/// Gather current git state from the repo for auto-populating handoff context.
fn gather_git_state(root: &std::path::Path) -> GitState {
    let run = |args: &[&str]| -> Option<String> {
        Command::new("git")
            .args(args)
            .current_dir(root)
            .output()
            .ok()
            .filter(|o| o.status.success())
            .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
            .filter(|s| !s.is_empty())
    };

    GitState {
        branch: run(&["branch", "--show-current"]),
        diff_stat: run(&["diff", "--stat", "HEAD"]),
        uncommitted_files: run(&["status", "--porcelain", "--no-renames"])
            .map(|s| {
                s.lines()
                    .filter_map(|line| {
                        let trimmed = line.get(3..)?;
                        Some(trimmed.to_string())
                    })
                    .collect()
            })
            .unwrap_or_default(),
        last_commit: run(&["log", "--oneline", "-1"]),
        recent_commits: run(&["log", "--oneline", "-5"]),
    }
}

struct GitState {
    branch: Option<String>,
    diff_stat: Option<String>,
    uncommitted_files: Vec<String>,
    last_commit: Option<String>,
    recent_commits: Option<String>,
}

fn run_handoff(args: HandoffArgs) -> Result<()> {
    let root = fs::canonicalize(&args.root)
        .with_context(|| format!("failed to resolve {}", args.root.display()))?;
    let context_dir = ensure_session_state_files(&root)?;

    let session_path = context_dir.join("session.json");
    let mut state = StructuredSessionMemory::load_or_default(&session_path)?;

    // Auto-gather git state
    let git = gather_git_state(&root);

    // Merge uncommitted files into modified_files (deduped)
    for file in &git.uncommitted_files {
        if !state.modified_files.contains(file) {
            state.modified_files.push(file.clone());
        }
    }

    // Apply any explicit overrides
    if let Some(objective) = args.objective {
        state.session_objective = Some(objective);
    }
    if let Some(next) = args.next {
        state.pending_next_actions.clear();
        state
            .pending_next_actions
            .push(session_memory::NextAction { summary: next });
    }
    for fact in args.pin {
        state.pin_fact(fact);
    }

    // Compact before saving to keep it small
    state.compact(&SessionCompactionPolicy {
        max_recent_turns: 3,
        max_tests_run: 5,
        max_failed_approaches: 5,
        max_pending_next_actions: 5,
    });

    state.save_to_path(&session_path)?;

    let packet = build_restart_packet(&state, &RestartPacketPolicy::default());

    // Also write a human-readable handoff note
    let handoff_path = context_dir.join("handoff.md");
    let note = render_handoff_markdown(&git, &packet);

    fs::write(&handoff_path, &note)?;

    // Print the handoff note so user/Claude can see it
    print!("{note}");
    eprintln!("saved to {}", handoff_path.display());
    Ok(())
}

fn run_resume(args: ResumeArgs) -> Result<()> {
    let root = fs::canonicalize(&args.root)
        .with_context(|| format!("failed to resolve {}", args.root.display()))?;
    let context_dir = root.join(".context-os");
    let session_path = context_dir.join("session.json");

    if !session_path.exists() {
        return Ok(());
    }

    let state = StructuredSessionMemory::load_from_path(&session_path)?;
    let mut policy = RestartPacketPolicy::default();
    policy.max_tokens = args.max_tokens;
    let packet = build_restart_packet(&state, &policy);
    let rendered = render_restart_packet(&packet);
    if rendered.is_empty() {
        return Ok(());
    }

    // When used as SessionStart hook, Claude Code captures stdout.
    // Plain text output becomes additionalContext for the session.
    print!("{rendered}");
    Ok(())
}

fn run_status(args: StatusArgs) -> Result<()> {
    let root = fs::canonicalize(&args.root)
        .with_context(|| format!("failed to resolve {}", args.root.display()))?;
    let context_dir = root.join(".context-os");

    let git = gather_git_state(&root);

    // Build a compact status block that survives context compaction
    let mut parts: Vec<String> = Vec::new();

    if let Some(branch) = &git.branch {
        parts.push(format!("branch={branch}"));
    }
    if !git.uncommitted_files.is_empty() {
        parts.push(format!("uncommitted={}", git.uncommitted_files.len()));
    }

    // Load session state for objective + last failure
    let session_path = context_dir.join("session.json");
    if let Ok(state) = StructuredSessionMemory::load_from_path(&session_path) {
        if let Some(objective) = &state.session_objective {
            // Truncate long objectives
            let short = if objective.len() > 80 {
                format!("{}...", &objective[..77])
            } else {
                objective.clone()
            };
            parts.push(format!("objective=\"{short}\""));
        }
        if let Some(sig) = state.failing_signatures.last() {
            let short = if sig.len() > 60 {
                format!("{}...", &sig[..57])
            } else {
                sig.clone()
            };
            parts.push(format!("last_failure=\"{short}\""));
        }
    }

    if !parts.is_empty() {
        println!("[context-os] {}", parts.join(" | "));
    }

    Ok(())
}

fn ensure_session_state_files(root: &Path) -> Result<PathBuf> {
    let context_dir = root.join(".context-os");
    fs::create_dir_all(&context_dir)?;

    let session_path = context_dir.join("session.json");
    if !session_path.exists() {
        StructuredSessionMemory::default().save_to_path(&session_path)?;
    }

    let journal_path = context_dir.join("journal.jsonl");
    if !journal_path.exists() {
        fs::write(&journal_path, "")?;
    }

    Ok(context_dir)
}

fn find_context_dir(start: &Path) -> Option<PathBuf> {
    let mut current = Some(start);
    while let Some(path) = current {
        let candidate = path.join(".context-os");
        if candidate.is_dir() {
            return Some(candidate);
        }
        current = path.parent();
    }
    None
}

/// Advisory file lock on session.json to prevent concurrent PostToolUse hooks
/// from clobbering each other. Uses a lockfile with spin-retry.
/// Lock is released when the returned guard is dropped.
struct SessionLock {
    _file: fs::File,
    path: PathBuf,
}

impl Drop for SessionLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn acquire_session_lock(context_dir: &Path) -> Result<SessionLock> {
    let lock_path = context_dir.join("session.lock");
    // Spin with backoff, max ~2 seconds total
    for attempt in 0..20 {
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&lock_path)
        {
            Ok(file) => {
                return Ok(SessionLock {
                    _file: file,
                    path: lock_path,
                });
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                // Check if lock is stale (older than 10 seconds — hook timeout is 5s)
                if let Ok(meta) = fs::metadata(&lock_path) {
                    if let Ok(modified) = meta.modified() {
                        if let Ok(age) = modified.elapsed() {
                            if age.as_secs() > 10 {
                                let _ = fs::remove_file(&lock_path);
                                continue;
                            }
                        }
                    }
                }
                std::thread::sleep(std::time::Duration::from_millis(50 * (attempt + 1)));
            }
            Err(e) => return Err(e).context("failed to create session lock"),
        }
    }
    // Give up after ~2 seconds — proceed without lock rather than blocking forever
    anyhow::bail!("could not acquire session lock after retries")
}

fn build_restart_packet(
    state: &StructuredSessionMemory,
    policy: &RestartPacketPolicy,
) -> RestartPacket {
    let mut packet = RestartPacket {
        session_objective: state.session_objective.clone(),
        current_subtask: state.current_subtask.clone(),
        decisions_made: take_recent(&state.decisions_made, policy.max_decisions),
        failed_approaches: take_recent(&state.failed_approaches, policy.max_failed_approaches),
        failing_signatures: state.failing_signatures.clone(),
        modified_files: take_recent(&state.modified_files, policy.max_modified_files),
        pending_next_actions: take_recent(
            &state.pending_next_actions,
            policy.max_pending_next_actions,
        ),
        pinned_facts: state.pinned_facts.clone(),
        hard_constraints: state.hard_constraints.clone(),
        tests_run: take_recent(&state.tests_run, policy.max_tests_run),
        recent_turns: take_recent(&state.recent_turns, policy.max_recent_turns),
    };

    while estimate_text(&render_restart_packet(&packet), ModelFamily::Claude).estimated_tokens
        > policy.max_tokens as u32
    {
        if !packet.recent_turns.is_empty() {
            packet.recent_turns.remove(0);
            continue;
        }
        if !packet.tests_run.is_empty() {
            packet.tests_run.remove(0);
            continue;
        }
        if !packet.failed_approaches.is_empty() {
            drop_low_value_failed_approach(&mut packet.failed_approaches);
            continue;
        }
        if packet.decisions_made.len() > 1 {
            packet.decisions_made.remove(0);
            continue;
        }
        break;
    }

    packet
}

fn render_restart_packet(packet: &RestartPacket) -> String {
    let mut out = String::new();
    let mut sections = 0usize;

    if let Some(objective) = &packet.session_objective {
        out.push_str("[context-os restart packet]\n");
        out.push_str("OBJECTIVE\n");
        out.push_str(objective.trim());
        out.push_str("\n\n");
        sections += 1;
    }

    if let Some(subtask) = &packet.current_subtask {
        if sections == 0 {
            out.push_str("[context-os restart packet]\n");
        }
        out.push_str("CURRENT SUBTASK\n");
        out.push_str(subtask.trim());
        out.push_str("\n\n");
        sections += 1;
    }

    if !packet.decisions_made.is_empty() {
        if sections == 0 {
            out.push_str("[context-os restart packet]\n");
        }
        out.push_str("DECISIONS MADE\n");
        for decision in &packet.decisions_made {
            out.push_str("- ");
            out.push_str(decision.summary.trim());
            out.push('\n');
            if let Some(rationale) = &decision.rationale {
                out.push_str("  why: ");
                out.push_str(rationale.trim());
                out.push('\n');
            }
        }
        out.push('\n');
        sections += 1;
    }

    if !packet.failed_approaches.is_empty() {
        if sections == 0 {
            out.push_str("[context-os restart packet]\n");
        }
        out.push_str("FAILED APPROACHES TO AVOID\n");
        for item in &packet.failed_approaches {
            out.push_str("- ");
            out.push_str(item.trim());
            out.push('\n');
        }
        out.push('\n');
        sections += 1;
    }

    if !packet.failing_signatures.is_empty() {
        if sections == 0 {
            out.push_str("[context-os restart packet]\n");
        }
        out.push_str("CURRENT FAILING SIGNATURES\n");
        for item in &packet.failing_signatures {
            out.push_str("- ");
            out.push_str(item.trim());
            out.push('\n');
        }
        out.push('\n');
        sections += 1;
    }

    if !packet.modified_files.is_empty() {
        if sections == 0 {
            out.push_str("[context-os restart packet]\n");
        }
        out.push_str("MODIFIED FILES\n");
        for item in &packet.modified_files {
            out.push_str("- ");
            out.push_str(item.trim());
            out.push('\n');
        }
        out.push('\n');
        sections += 1;
    }

    if !packet.pending_next_actions.is_empty() {
        if sections == 0 {
            out.push_str("[context-os restart packet]\n");
        }
        out.push_str("NEXT ACTIONS\n");
        for action in &packet.pending_next_actions {
            out.push_str("- ");
            out.push_str(action.summary.trim());
            out.push('\n');
        }
        out.push('\n');
        sections += 1;
    }

    if !packet.pinned_facts.is_empty() {
        if sections == 0 {
            out.push_str("[context-os restart packet]\n");
        }
        out.push_str("PINNED FACTS\n");
        for fact in &packet.pinned_facts {
            out.push_str("- ");
            out.push_str(fact.value.trim());
            out.push('\n');
        }
        out.push('\n');
        sections += 1;
    }

    if !packet.hard_constraints.is_empty() {
        if sections == 0 {
            out.push_str("[context-os restart packet]\n");
        }
        out.push_str("CONSTRAINTS\n");
        for item in &packet.hard_constraints {
            out.push_str("- ");
            out.push_str(item.trim());
            out.push('\n');
        }
        out.push('\n');
        sections += 1;
    }

    if !packet.tests_run.is_empty() {
        if sections == 0 {
            out.push_str("[context-os restart packet]\n");
        }
        out.push_str("RECENT TESTS AND BUILDS\n");
        for record in &packet.tests_run {
            out.push_str("- ");
            out.push_str(record.command.trim());
            if let Some(outcome) = &record.outcome {
                out.push_str(" (");
                out.push_str(outcome.trim());
                out.push(')');
            }
            out.push('\n');
        }
        out.push('\n');
        sections += 1;
    }

    if !packet.recent_turns.is_empty() {
        if sections == 0 {
            out.push_str("[context-os restart packet]\n");
        }
        out.push_str("RECENT TURN SNAPSHOT\n");
        for turn in &packet.recent_turns {
            out.push_str("- ");
            out.push_str(turn.role.trim());
            out.push_str(": ");
            out.push_str(turn.content.trim());
            out.push('\n');
        }
        out.push('\n');
        sections += 1;
    }

    if sections > 0 {
        out.push_str("[/context-os]\n");
    }

    out
}

fn render_handoff_markdown(git: &GitState, packet: &RestartPacket) -> String {
    let mut note = String::from("# Session Handoff\n\n");
    note.push_str(
        "Read this at the start of a new session to continue without losing decisions, failures, or file state.\n\n",
    );

    if git.branch.is_some() || !git.uncommitted_files.is_empty() || git.last_commit.is_some() {
        note.push_str("## Git state\n\n");
        if let Some(branch) = &git.branch {
            note.push_str(&format!("Branch: `{branch}`\n"));
        }
        if let Some(last) = &git.last_commit {
            note.push_str(&format!("Last commit: `{last}`\n"));
        }
        if !git.uncommitted_files.is_empty() {
            note.push_str(&format!(
                "Uncommitted changes: {} files\n",
                git.uncommitted_files.len()
            ));
            for file in git.uncommitted_files.iter().take(15) {
                note.push_str(&format!("- {file}\n"));
            }
        }
        if let Some(diff_stat) = &git.diff_stat {
            note.push_str("\n```text\n");
            note.push_str(diff_stat.trim());
            note.push_str("\n```\n");
        }
        if let Some(commits) = &git.recent_commits {
            note.push_str("\nRecent commits:\n");
            for line in commits.lines().take(5) {
                note.push_str(&format!("- {line}\n"));
            }
        }
        note.push('\n');
    }

    push_markdown_text_section(&mut note, "Objective", packet.session_objective.as_deref());
    push_markdown_text_section(
        &mut note,
        "Current subtask",
        packet.current_subtask.as_deref(),
    );
    push_markdown_bullet_section(
        &mut note,
        "Next actions",
        &packet
            .pending_next_actions
            .iter()
            .map(|item| item.summary.clone())
            .collect::<Vec<_>>(),
    );
    push_markdown_bullet_section(&mut note, "Modified files", &packet.modified_files);

    if !packet.decisions_made.is_empty() {
        note.push_str("## Decisions made\n\n");
        for decision in &packet.decisions_made {
            note.push_str(&format!("- {}", decision.summary));
            if let Some(rationale) = &decision.rationale {
                note.push_str(&format!(" ({})", rationale));
            }
            note.push('\n');
        }
        note.push('\n');
    }

    push_markdown_bullet_section(
        &mut note,
        "Failed approaches (do not retry)",
        &packet.failed_approaches,
    );
    push_markdown_bullet_section(
        &mut note,
        "Currently failing signatures",
        &packet.failing_signatures,
    );
    push_markdown_bullet_section(
        &mut note,
        "Pinned facts",
        &packet
            .pinned_facts
            .iter()
            .map(|item| item.value.clone())
            .collect::<Vec<_>>(),
    );
    push_markdown_bullet_section(&mut note, "Constraints", &packet.hard_constraints);

    note
}

fn push_markdown_text_section(out: &mut String, title: &str, value: Option<&str>) {
    if let Some(value) = value {
        out.push_str(&format!("## {title}\n\n{}\n\n", value.trim()));
    }
}

fn push_markdown_bullet_section(out: &mut String, title: &str, items: &[String]) {
    if items.is_empty() {
        return;
    }
    out.push_str(&format!("## {title}\n\n"));
    for item in items {
        out.push_str(&format!("- {}\n", item.trim()));
    }
    out.push('\n');
}

fn take_recent<T: Clone>(items: &[T], max: usize) -> Vec<T> {
    if items.len() <= max {
        items.to_vec()
    } else {
        items[items.len() - max..].to_vec()
    }
}

fn failed_approach_value(item: &str) -> usize {
    let lower = item.to_ascii_lowercase();
    let mut score = 0usize;
    if lower.contains("error") || lower.contains("failed") || lower.contains("panic") {
        score += 2;
    }
    if lower.contains('/') || lower.contains("::") || lower.contains(".rs") || lower.contains(".ts")
    {
        score += 2;
    }
    if lower.contains("test") || lower.contains("build") || lower.contains("compiler") {
        score += 1;
    }
    score
}

fn drop_low_value_failed_approach(items: &mut Vec<String>) {
    if items.is_empty() {
        return;
    }

    let mut index_to_remove = 0usize;
    let mut lowest_score = usize::MAX;
    for (idx, item) in items.iter().enumerate() {
        let score = failed_approach_value(item);
        if score < lowest_score {
            lowest_score = score;
            index_to_remove = idx;
        }
    }
    items.remove(index_to_remove);
}

fn now_unix() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
}

fn append_journal_events(context_dir: &Path, events: &[JournalEvent]) -> Result<()> {
    if events.is_empty() {
        return Ok(());
    }
    let journal_path = context_dir.join("journal.jsonl");
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&journal_path)
        .with_context(|| format!("failed to open {}", journal_path.display()))?;

    for event in events {
        use std::io::Write;
        writeln!(file, "{}", serde_json::to_string(event)?)
            .with_context(|| format!("failed to append {}", journal_path.display()))?;
    }
    Ok(())
}

fn looks_like_failure(output: &str) -> bool {
    for line in output.lines() {
        let trimmed = line.trim();
        let lower = trimmed.to_ascii_lowercase();
        // Definitive failure markers (line-level to avoid false positives on "0 failed")
        if lower.contains("test result: failed")
            || lower.starts_with("error:")
            || lower.starts_with("error[")
            || lower.contains("compilation failed")
            || lower.contains("build failed")
            || lower.contains("panicked at")
            || (trimmed.starts_with("test ") && trimmed.ends_with("... FAILED"))
            || trimmed.starts_with("FAIL ")
            || trimmed.starts_with("FAILED ")
            || trimmed.starts_with("✗ ")
            || trimmed.starts_with("✘ ")
            || trimmed.starts_with("× ")
        {
            return true;
        }
        // "N failed" where N > 0 (catches "1 failed", "Tests: 3 failed")
        if let Some(pos) = lower.find("failed") {
            let before = lower[..pos].trim();
            if let Some(last_word) = before.rsplit_once(|c: char| !c.is_ascii_digit()).map(|(_, n)| n) {
                if let Ok(n) = last_word.parse::<u32>() {
                    if n > 0 {
                        return true;
                    }
                }
            }
        }
    }
    false
}

fn looks_like_success(output: &str) -> bool {
    let lower = output.to_ascii_lowercase();
    // Explicit success markers
    if lower.contains("test result: ok")
        || lower.contains("build succeeded")
        || lower.contains("finished `")
        || lower.contains("finished dev")
        || lower.contains("compiled successfully")
        || lower.contains("all tests passed")
    {
        return true;
    }
    // "N passed" without any failure indicators
    // Catches Jest "Tests: 3 passed, 3 total", Vitest "Tests 15 passed (15)", pytest "3 passed"
    if lower.contains("passed") && !looks_like_failure(output) {
        return true;
    }
    // "0 failed" (but only if no actual failures detected)
    if lower.contains("0 failed") && !looks_like_failure(output) {
        return true;
    }
    false
}

fn extract_failing_signatures(output: &str) -> Vec<String> {
    let mut signatures = Vec::new();
    for line in output.lines() {
        let trimmed = line.trim();
        // Rust: "test foo::bar ... FAILED"
        if trimmed.starts_with("test ") && trimmed.ends_with("... FAILED") {
            signatures.push(
                trimmed
                    .trim_start_matches("test ")
                    .trim_end_matches(" ... FAILED")
                    .to_string(),
            );
        // Jest: "FAIL src/tests/foo.test.ts"
        } else if trimmed.starts_with("FAIL ") {
            signatures.push(trimmed.trim_start_matches("FAIL ").trim().to_string());
        // Vitest: "✗ src/services/api.test.ts" or "× ..."
        } else if trimmed.starts_with("✗ ") || trimmed.starts_with("× ") || trimmed.starts_with("✘ ") {
            let sig = trimmed[trimmed.char_indices().nth(1).map_or(0, |(i, _)| i)..].trim();
            if !sig.is_empty() {
                signatures.push(sig.to_string());
            }
        // Rust panic
        } else if trimmed.contains("panicked at") && trimmed.contains("::") {
            signatures.push(trimmed.to_string());
        // pytest: "FAILED tests/test_foo.py::test_bar"
        } else if trimmed.starts_with("FAILED ") {
            signatures.push(trimmed.trim_start_matches("FAILED ").trim().to_string());
        }
    }
    signatures
}

fn extract_failed_approach(output: &str) -> Option<String> {
    for line in output.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("error[") || trimmed.starts_with("error:") {
            return Some(if trimmed.len() > 140 {
                format!("{}...", &trimmed[..137])
            } else {
                trimmed.to_string()
            });
        }
    }
    None
}

fn extract_pinned_fact(output: &str) -> Option<String> {
    for line in output.lines() {
        let trimmed = line.trim();
        let lower = trimmed.to_ascii_lowercase();
        if lower.contains("do not retry")
            || lower.contains("don't retry")
            || lower.contains("never retry")
            || lower.contains("do not use")
            || lower.contains("must keep")
        {
            return Some(trimmed.to_string());
        }
    }
    None
}

fn summarize_command(command: &str) -> String {
    let trimmed = command.trim();
    if trimmed.is_empty() {
        "a Claude Code tool action".to_string()
    } else if trimmed.len() > 120 {
        format!("{}...", &trimmed[..117])
    } else {
        trimmed.to_string()
    }
}

fn relative_path_display(cwd: &Path, path: &str) -> String {
    let path_buf = PathBuf::from(path);
    path_buf
        .strip_prefix(cwd)
        .ok()
        .map(|value| value.display().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| path.trim_start_matches('/').to_string())
}

fn process_post_tool_use_event(
    state: &mut StructuredSessionMemory,
    tool_name: &str,
    tool_input: &serde_json::Value,
    tool_output: &str,
    cwd: &Path,
) -> HookProcessingResult {
    let mut result = HookProcessingResult::default();
    let tool_name = tool_name.trim();

    if tool_name == "Bash" {
        let command = tool_input
            .get("command")
            .and_then(|value| value.as_str())
            .unwrap_or("");
        let outcome = if looks_like_failure(tool_output) {
            "failed"
        } else if looks_like_success(tool_output) {
            "passed"
        } else {
            "observed"
        };

        let command_record = CommandRecord {
            command: summarize_command(command),
            outcome: Some(outcome.to_string()),
        };
        if !state.tests_run.contains(&command_record) {
            state.tests_run.push(command_record.clone());
            result.changed = true;
            result.journal_events.push(JournalEvent {
                ts_unix: now_unix(),
                hook: "PostToolUse".to_string(),
                category: "command_recorded".to_string(),
                summary: format!("Recorded `{}` as {}", command_record.command, outcome),
                metadata: serde_json::json!({
                    "command": command_record.command,
                    "outcome": outcome,
                }),
            });
        }

        if looks_like_failure(tool_output) {
            for signature in extract_failing_signatures(tool_output) {
                if !state.failing_signatures.contains(&signature) {
                    state.failing_signatures.push(signature.clone());
                    result.changed = true;
                    result.journal_events.push(JournalEvent {
                        ts_unix: now_unix(),
                        hook: "PostToolUse".to_string(),
                        category: "failing_signature".to_string(),
                        summary: format!("Captured failing signature `{signature}`"),
                        metadata: serde_json::json!({ "signature": signature }),
                    });
                }
            }

            if let Some(approach) = extract_failed_approach(tool_output) {
                if !state.failed_approaches.contains(&approach) {
                    state.failed_approaches.push(approach.clone());
                    result.changed = true;
                    result.journal_events.push(JournalEvent {
                        ts_unix: now_unix(),
                        hook: "PostToolUse".to_string(),
                        category: "failed_approach".to_string(),
                        summary: format!("Recorded failed approach `{approach}`"),
                        metadata: serde_json::json!({ "approach": approach }),
                    });
                }
            }
        }

        if let Some(fact) = extract_pinned_fact(tool_output) {
            let pinned_fact = PinnedFact {
                value: fact.clone(),
            };
            if !state.pinned_facts.contains(&pinned_fact) {
                state.pinned_facts.push(pinned_fact);
                result.changed = true;
                result.journal_events.push(JournalEvent {
                    ts_unix: now_unix(),
                    hook: "PostToolUse".to_string(),
                    category: "pinned_fact".to_string(),
                    summary: format!("Pinned `{fact}`"),
                    metadata: serde_json::json!({ "fact": fact }),
                });
            }
        }

        if looks_like_success(tool_output)
            && (!state.failing_signatures.is_empty() || !state.failed_approaches.is_empty())
        {
            let cleared_failures = state.failing_signatures.len();
            state.failing_signatures.clear();
            let decision = DecisionRecord {
                summary: format!(
                    "Validated current approach with `{}`",
                    summarize_command(command)
                ),
                rationale: Some(format!(
                    "successful rerun after {} prior failing signature(s)",
                    cleared_failures
                )),
            };
            if !state.decisions_made.contains(&decision) {
                state.decisions_made.push(decision.clone());
                result.changed = true;
                result.journal_events.push(JournalEvent {
                    ts_unix: now_unix(),
                    hook: "PostToolUse".to_string(),
                    category: "decision".to_string(),
                    summary: decision.summary.clone(),
                    metadata: serde_json::json!({
                        "rationale": decision.rationale,
                    }),
                });
            }
        }
    }

    if tool_name == "Edit" || tool_name == "Write" {
        if let Some(path) = tool_input
            .get("file_path")
            .and_then(|value| value.as_str())
            .or_else(|| tool_input.get("path").and_then(|value| value.as_str()))
        {
            let short = relative_path_display(cwd, path);
            if !state.modified_files.contains(&short) {
                state.modified_files.push(short.clone());
                result.changed = true;
                result.journal_events.push(JournalEvent {
                    ts_unix: now_unix(),
                    hook: "PostToolUse".to_string(),
                    category: "modified_file".to_string(),
                    summary: format!("Recorded modified file `{short}`"),
                    metadata: serde_json::json!({ "file": short }),
                });
            }
        }
    }

    if state.tests_run.len() > 20 {
        state.tests_run = take_recent(&state.tests_run, 20);
    }
    if state.failing_signatures.len() > 12 {
        state.failing_signatures = take_recent(&state.failing_signatures, 12);
    }
    if state.failed_approaches.len() > 12 {
        state.failed_approaches = take_recent(&state.failed_approaches, 12);
    }
    if state.modified_files.len() > 24 {
        state.modified_files = take_recent(&state.modified_files, 24);
    }
    if state.decisions_made.len() > 12 {
        state.decisions_made = take_recent(&state.decisions_made, 12);
    }

    result
}

fn run_pipe(args: PipeArgs) -> Result<()> {
    let mut raw = Vec::new();
    std::io::stdin()
        .read_to_end(&mut raw)
        .context("failed to read stdin")?;

    // If input is not valid UTF-8 (binary output), pass through unchanged
    let input = match String::from_utf8(raw) {
        Ok(s) => s,
        Err(e) => {
            // Binary data — pass through and exit successfully
            use std::io::Write;
            std::io::stdout().write_all(e.as_bytes())?;
            return Ok(());
        }
    };

    if input.trim().is_empty() {
        return Ok(());
    }

    let mode = args
        .mode
        .parse::<ReductionMode>()
        .map_err(anyhow::Error::msg)?;
    let registry = ReducerRegistry::default();
    let protections = ProtectionRules::safe_defaults();

    // Auto-detect or use forced kind
    let kind = if let Some(kind_str) = args.kind {
        Some(
            kind_str
                .parse::<ReducerKind>()
                .map_err(anyhow::Error::msg)?,
        )
    } else {
        registry
            .detect_best(&input)
            .filter(|(_, confidence)| *confidence >= 0.4)
            .map(|(kind, _)| kind)
    };

    if let Some(kind) = kind {
        if let Some(result) = registry.reduce(kind, &input, mode, &protections) {
            if result.metadata.transformed
                && result.metadata.after_tokens < result.metadata.before_tokens
            {
                if args.raw {
                    print!("{}", result.output);
                } else {
                    println!(
                        "{}",
                        serde_json::to_string_pretty(&ReduceOutput {
                            output: result.output,
                            metadata: result.metadata,
                        })?
                    );
                }
                return Ok(());
            }
        }
    }

    // Pass through if no reduction possible
    print!("{input}");
    Ok(())
}

fn run_estimate(args: EstimateArgs) -> Result<()> {
    let content = read_file(&args.input)?;
    let estimate = estimate_text(&content, args.model.into());
    println!("{}", serde_json::to_string_pretty(&estimate)?);
    Ok(())
}

fn run_reduce(args: ReduceArgs) -> Result<()> {
    let content = read_file(&args.input)?;
    let kind = args
        .kind
        .parse::<ReducerKind>()
        .map_err(anyhow::Error::msg)?;
    let mode = args
        .mode
        .parse::<ReductionMode>()
        .map_err(anyhow::Error::msg)?;
    let registry = ReducerRegistry::default();
    let result = registry
        .reduce(kind, &content, mode, &ProtectionRules::safe_defaults())
        .context("requested reducer is not registered")?;

    println!(
        "{}",
        serde_json::to_string_pretty(&ReduceOutput {
            output: result.output,
            metadata: result.metadata,
        })?
    );
    Ok(())
}

fn run_prompt_lint(args: PromptLintArgs) -> Result<()> {
    let content = read_file(&args.input)?;
    let report = analyze_prompt(&content);
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(())
}

fn run_index(args: IndexArgs) -> Result<()> {
    let artifacts = build_and_write(&args.root, &args.out)?;
    println!("{}", serde_json::to_string_pretty(&artifacts)?);
    Ok(())
}

fn run_inspect(args: InspectArgs) -> Result<()> {
    let artifacts = build_repo_memory(&args.root)?;
    println!("{}", serde_json::to_string_pretty(&artifacts.architecture)?);
    Ok(())
}

fn run_intercept(command: InterceptCommand) -> Result<()> {
    match command.command {
        InterceptSubcommand::Request {
            session_id,
            input,
            reducer_kind,
            mode,
            prompt_linter,
            attach_session_memory,
            session_state,
            telemetry_db,
            upstream_url,
        } => {
            let content = read_file(&input)?;
            let reducer_hint = reducer_kind
                .map(|value| value.parse::<ReducerKind>())
                .transpose()
                .map_err(anyhow::Error::msg)?;
            let reducer_mode = mode.parse::<ReductionMode>().map_err(anyhow::Error::msg)?;
            let response = intercept_request(ProxyRequest {
                session_id,
                content,
                upstream_url,
                cwd: Some(std::env::current_dir()?.display().to_string()),
                reducer_hint,
                reducer_mode,
                enable_prompt_linter: prompt_linter,
                attach_session_memory,
                session_state_path: session_state.map(|path| path.display().to_string()),
                telemetry_db_path: telemetry_db.map(|path| path.display().to_string()),
                protected_literals: Vec::new(),
            })?;
            println!("{}", serde_json::to_string_pretty(&response)?);
        }
    }
    Ok(())
}

fn run_session(command: SessionCommand) -> Result<()> {
    match command.command {
        SessionSubcommand::Update { state, update } => {
            let mut memory = StructuredSessionMemory::load_or_default(&state)?;
            let before = memory.clone();
            let update = read_session_update(&update)?;
            update_structured_memory(&mut memory, update);
            memory.save_to_path(&state)?;
            let diff = diff_memory_states(&before, &memory);
            println!(
                "{}",
                serde_json::to_string_pretty(&SessionUpdateOutput {
                    state: memory,
                    diff,
                })?
            );
        }
        SessionSubcommand::Pin { state, fact } => {
            let mut memory = StructuredSessionMemory::load_or_default(&state)?;
            let before = memory.clone();
            memory.pin_fact(fact);
            memory.save_to_path(&state)?;
            let diff = diff_memory_states(&before, &memory);
            println!(
                "{}",
                serde_json::to_string_pretty(&SessionUpdateOutput {
                    state: memory,
                    diff,
                })?
            );
        }
        SessionSubcommand::Export { state } => {
            let memory = StructuredSessionMemory::load_from_path(&state)?;
            println!("{}", export_session_state(&memory)?);
        }
        SessionSubcommand::Diff { before, after } => {
            let before = StructuredSessionMemory::load_from_path(&before)?;
            let after = StructuredSessionMemory::load_from_path(&after)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&diff_memory_states(&before, &after))?
            );
        }
        SessionSubcommand::Compact {
            state,
            max_recent_turns,
            max_tests_run,
            max_failed_approaches,
            max_pending_next_actions,
        } => {
            let mut memory = StructuredSessionMemory::load_from_path(&state)?;
            let result = compact_session(
                &mut memory,
                &SessionCompactionPolicy {
                    max_recent_turns,
                    max_tests_run,
                    max_failed_approaches,
                    max_pending_next_actions,
                },
            );
            memory.save_to_path(&state)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&serde_json::json!({
                    "compaction": result,
                    "state": memory
                }))?
            );
        }
    }
    Ok(())
}

fn run_config(command: ConfigCommand) -> Result<()> {
    match command.command {
        ConfigSubcommand::Validate { path } => {
            let config = ContextOsConfig::load_from_path(&path)?;
            println!("{}", serde_json::to_string_pretty(&config)?);
        }
    }
    Ok(())
}

fn run_telemetry(command: TelemetryCommand) -> Result<()> {
    match command.command {
        TelemetrySubcommand::Init { db } => {
            let store = TelemetryStore::open(&db)?;
            store.init()?;
            println!(
                "{}",
                serde_json::json!({
                    "status": "ok",
                    "database": db.display().to_string(),
                    "message": "telemetry schema initialized"
                })
            );
        }
    }
    Ok(())
}

fn run_doctor(args: DoctorArgs) -> Result<()> {
    let root = fs::canonicalize(&args.root)
        .with_context(|| format!("failed to resolve {}", args.root.display()))?;

    println!("\ncontext-os doctor\n");

    let mut all_ok = true;
    let bin_path = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("context-os"));
    if bin_path.exists() {
        println!("  ✓ context-os binary available at {}", bin_path.display());
    } else {
        println!("  ✗ could not resolve the running context-os binary");
        all_ok = false;
    }

    // 1. Git repo check
    let git_check = Command::new("git")
        .args(["rev-parse", "--git-dir"])
        .current_dir(&root)
        .output();

    let branch = match git_check {
        Ok(output) if output.status.success() => {
            let branch = Command::new("git")
                .args(["branch", "--show-current"])
                .current_dir(&root)
                .output()
                .ok()
                .filter(|o| o.status.success())
                .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
                .unwrap_or_else(|| "unknown".to_string());
            println!("  ✓ git repository detected (branch: {branch})");
            Some(branch)
        }
        _ => {
            println!("  ✗ not a git repository");
            println!("    → run `git init` first");
            all_ok = false;
            None
        }
    };
    let _ = branch;

    // 2. .context-os/ directory
    let context_dir = root.join(".context-os");
    if context_dir.is_dir() {
        println!("  ✓ .context-os/ directory exists");
    } else {
        println!("  ✗ .context-os/ directory missing");
        println!("    → run `context-os init` to set up");
        all_ok = false;
    }

    // 3. CLAUDE.md with context-os markers
    let claude_md_path = root.join("CLAUDE.md");
    if claude_md_path.exists() {
        let content = fs::read_to_string(&claude_md_path).unwrap_or_default();
        if content.contains("<!-- context-os:start -->") {
            println!("  ✓ CLAUDE.md has context-os block");
        } else {
            println!("  ✗ CLAUDE.md exists but missing context-os block");
            println!("    → run `context-os init` to add the repo map");
            all_ok = false;
        }
    } else {
        println!("  ✗ CLAUDE.md not found");
        println!("    → run `context-os init` to generate it");
        all_ok = false;
    }

    // 4. .claude/settings.local.json with hooks
    let settings_path = root.join(".claude").join("settings.local.json");
    if settings_path.exists() {
        let content = fs::read_to_string(&settings_path).unwrap_or_default();
        let has_pre_tool = content.contains("PreToolUse");
        let has_post_tool = content.contains("PostToolUse");
        let has_pre_compact = content.contains("PreCompact");
        let has_session_start = content.contains("SessionStart");
        let has_stop = content.contains("Stop");
        if has_pre_tool && has_post_tool && has_pre_compact && has_session_start && has_stop {
            println!(
                "  ✓ Claude Code hooks installed (PreToolUse, PostToolUse, PreCompact, SessionStart, Stop)"
            );
        } else {
            let mut missing = Vec::new();
            if !has_pre_tool {
                missing.push("PreToolUse");
            }
            if !has_post_tool {
                missing.push("PostToolUse");
            }
            if !has_pre_compact {
                missing.push("PreCompact");
            }
            if !has_session_start {
                missing.push("SessionStart");
            }
            if !has_stop {
                missing.push("Stop");
            }
            println!(
                "  ✗ Claude Code hooks incomplete (missing: {})",
                missing.join(", ")
            );
            println!("    → run `context-os init` to install hooks");
            all_ok = false;
        }
    } else {
        println!("  ✗ .claude/settings.local.json not found");
        println!("    → run `context-os init` to install hooks");
        all_ok = false;
    }

    // 5. .context-os/ in .gitignore
    let gitignore_path = root.join(".gitignore");
    if gitignore_path.exists() {
        let content = fs::read_to_string(&gitignore_path).unwrap_or_default();
        if content.contains(".context-os/") || content.contains(".context-os") {
            println!("  ✓ .context-os/ in .gitignore");
        } else {
            println!("  ✗ .context-os/ not in .gitignore");
            println!("    → add `.context-os/` to your .gitignore");
            all_ok = false;
        }
    } else {
        println!("  ✗ .gitignore not found (.context-os/ may be tracked)");
        println!("    → run `context-os init` to create .gitignore");
        all_ok = false;
    }

    // 6. session.json
    let session_path = context_dir.join("session.json");
    if session_path.exists() {
        if let Ok(state) = StructuredSessionMemory::load_from_path(&session_path) {
            let obj_str = state
                .session_objective
                .as_deref()
                .map(|o| {
                    let truncated = if o.len() > 60 {
                        format!("{}...", &o[..57])
                    } else {
                        o.to_string()
                    };
                    format!(" (objective: \"{truncated}\")")
                })
                .unwrap_or_default();
            println!("  ✓ session.json exists{obj_str}");
        } else {
            println!("  ✗ session.json exists but could not be parsed");
            all_ok = false;
        }
    } else {
        println!("  ✗ session.json not found");
        println!("    → run `context-os init` to create canonical state files");
        all_ok = false;
    }

    // 7. journal.jsonl
    let journal_path = context_dir.join("journal.jsonl");
    if journal_path.exists() {
        println!("  ✓ journal.jsonl exists");
    } else {
        println!("  ✗ journal.jsonl not found");
        println!("    → run `context-os init` to create append-only hook journal");
        all_ok = false;
    }

    // 8. handoff.md
    let handoff_path = context_dir.join("handoff.md");
    if handoff_path.exists() {
        println!("  ✓ handoff.md exists");
    } else {
        println!("  - handoff.md not found yet (created after the first stop/handoff)");
    }

    // 9. restart packet generation
    if session_path.exists() {
        match StructuredSessionMemory::load_from_path(&session_path) {
            Ok(state) => {
                let packet = build_restart_packet(&state, &RestartPacketPolicy::default());
                let rendered = render_restart_packet(&packet);
                if rendered.is_empty() {
                    println!("  - restart packet currently empty (session state has no captured facts yet)");
                } else {
                    let estimate = estimate_text(&rendered, ModelFamily::Claude).estimated_tokens;
                    println!("  ✓ restart packet renders ({estimate} estimated Claude tokens)");
                }
            }
            Err(err) => {
                println!("  ✗ failed to render restart packet: {err}");
                all_ok = false;
            }
        }
    }

    // Benchmark reports only apply inside the context-os development repo
    let evals_dir = root.join("python").join("evals").join("reports");
    if evals_dir.is_dir() {
        println!("\n  Benchmark reports:");
        if benchmark_report_passed(&root, "python/evals/reports/safe-mode-report.json")? {
            println!("    ✓ safe-mode report present and passing");
        } else {
            println!("    ✗ safe-mode report missing or failing");
            println!("      → run `python3 python/evals/runners/safe_mode_runner.py`");
            all_ok = false;
        }
        if benchmark_report_passed(
            &root,
            "python/evals/reports/compaction-survival-report.json",
        )? {
            println!("    ✓ compaction-survival report present and passing");
        } else {
            println!("    ✗ compaction-survival report missing or failing");
            println!("      → run `python3 python/evals/runners/compaction_survival_runner.py`");
            all_ok = false;
        }
    }

    if all_ok {
        println!("\n  Status: ready\n");
    } else {
        println!("\n  Status: needs attention\n");
    }

    Ok(())
}

fn benchmark_report_passed(root: &Path, relative_path: &str) -> Result<bool> {
    let path = root.join(relative_path);
    if !path.exists() {
        return Ok(false);
    }
    let content =
        fs::read_to_string(&path).with_context(|| format!("failed to read {}", path.display()))?;
    let value: serde_json::Value = serde_json::from_str(&content)
        .with_context(|| format!("failed to parse {}", path.display()))?;
    let total = value
        .get("summary")
        .and_then(|summary| summary.get("total_cases"))
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let passed = value
        .get("summary")
        .and_then(|summary| summary.get("passed_cases"))
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    Ok(total > 0 && total == passed)
}

fn run_hook(command: HookCommand) -> Result<()> {
    match command.command {
        HookSubcommand::PreToolUse => run_hook_pre_tool_use(),
        HookSubcommand::PostToolUse => run_hook_post_tool_use(),
        HookSubcommand::PreCompact => run_hook_pre_compact(),
    }
}

/// Patterns that produce output worth reducing.
const REDUCIBLE_PREFIXES: &[&str] = &[
    // Rust
    "cargo test",
    "cargo build",
    "cargo clippy",
    "cargo check",
    // Node / npm
    "npm test",
    "npm run test",
    "npm run build",
    "npm install",
    "npm ci",
    // pnpm
    "pnpm test",
    "pnpm run test",
    "pnpm run build",
    "pnpm install",
    // yarn
    "yarn test",
    "yarn build",
    "yarn install",
    // npx runners
    "npx jest",
    "npx vitest",
    "npx tsc",
    "npx eslint",
    // bun
    "bun test",
    "bun run test",
    "bun run build",
    "bun install",
    // deno
    "deno test",
    // Python
    "pytest",
    "python -m pytest",
    "python3 -m pytest",
    "pip install",
    "pip3 install",
    // Go
    "go test",
    "go build",
    // Make
    "make test",
    "make build",
    "make check",
    // Linters
    "eslint",
    // JVM
    "gradle build",
    "gradle test",
    "mvn test",
    "mvn compile",
    // .NET
    "dotnet test",
    "dotnet build",
    // Swift
    "swift test",
    "swift build",
    // Flutter/Dart
    "flutter test",
    "dart test",
];

/// Extract the "real" command from a shell line, stripping common prefixes:
///   cd /path &&, source ... &&, env VAR=val, VAR=val, timeout N
fn extract_core_command(cmd: &str) -> &str {
    let mut s = cmd.trim();

    // Strip chained prefixes: "cd /foo && source bar && cargo test" → "cargo test"
    loop {
        let before = s;

        // Strip "cd ... &&" or "pushd ... &&"
        if s.starts_with("cd ") || s.starts_with("pushd ") {
            if let Some(pos) = s.find("&&") {
                s = s[pos + 2..].trim();
                continue;
            }
        }

        // Strip "source ... &&" or ". ... &&"
        if s.starts_with("source ") || s.starts_with(". ") {
            if let Some(pos) = s.find("&&") {
                s = s[pos + 2..].trim();
                continue;
            }
        }

        // Strip "env " prefix
        if let Some(rest) = s.strip_prefix("env ") {
            s = rest.trim();
            continue;
        }

        // Strip "timeout N " prefix
        if s.starts_with("timeout ") {
            let parts: Vec<&str> = s.splitn(3, ' ').collect();
            if parts.len() >= 3 {
                // parts[1] should be a number
                if parts[1].parse::<u64>().is_ok() {
                    s = parts[2].trim();
                    continue;
                }
            }
        }

        // Strip leading VAR=val (e.g., RUST_BACKTRACE=1, CI=true, NODE_ENV=test)
        if let Some(eq_pos) = s.find('=') {
            let before_eq = &s[..eq_pos];
            // Env var names: uppercase letters, digits, underscores, must start with letter/_
            if !before_eq.is_empty()
                && before_eq
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '_')
                && before_eq
                    .chars()
                    .next()
                    .map_or(false, |c| c.is_ascii_alphabetic() || c == '_')
            {
                // Find the end of the value (next unquoted space)
                let after_eq = &s[eq_pos + 1..];
                if let Some(space_pos) = find_unquoted_space(after_eq) {
                    s = after_eq[space_pos..].trim();
                    continue;
                }
            }
        }

        if std::ptr::eq(s, before) {
            break;
        }
    }

    s
}

/// Find the first space not inside quotes.
fn find_unquoted_space(s: &str) -> Option<usize> {
    let mut in_single = false;
    let mut in_double = false;
    let mut escaped = false;
    for (i, c) in s.char_indices() {
        if escaped {
            escaped = false;
            continue;
        }
        if c == '\\' {
            escaped = true;
            continue;
        }
        if c == '\'' && !in_double {
            in_single = !in_single;
        } else if c == '"' && !in_single {
            in_double = !in_double;
        } else if c == ' ' && !in_single && !in_double {
            return Some(i);
        }
    }
    None
}

fn should_wrap_command(cmd: &str) -> bool {
    let trimmed = cmd.trim();
    // Skip if already piped through context-os
    if trimmed.contains("context-os") {
        return false;
    }

    let core = extract_core_command(trimmed);

    for prefix in REDUCIBLE_PREFIXES {
        if core.starts_with(prefix) {
            return true;
        }
    }
    false
}

fn run_hook_pre_tool_use() -> Result<()> {
    // Read the hook event from stdin
    let mut input = String::new();
    std::io::stdin()
        .read_to_string(&mut input)
        .context("failed to read hook event from stdin")?;

    // Parse the hook event
    let event: serde_json::Value = serde_json::from_str(&input).unwrap_or(serde_json::json!({}));

    // Extract the tool input command
    let tool_input = event.get("tool_input").unwrap_or(&serde_json::Value::Null);
    let command = tool_input
        .get("command")
        .and_then(|v| v.as_str())
        .unwrap_or("");

    if command.is_empty() || !should_wrap_command(command) {
        // Don't modify — output nothing so the hook is a no-op
        return Ok(());
    }

    // Find our own binary path
    let bin_path = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("context-os"));
    let bin = bin_path.display().to_string();

    // Wrap the command to pipe output through context-os pipe.
    // Preserve the original exit code so Claude sees test failures correctly.
    // FAIL-OPEN: if context-os pipe crashes, fall back to printing raw output.
    let wrapped = format!(
        r#"_co_rc=0; _co_out=$({command} 2>&1) || _co_rc=$?; printf '%s\n' "$_co_out" | "{bin}" pipe 2>/dev/null || printf '%s\n' "$_co_out"; exit "$_co_rc""#
    );

    // Output the PreToolUse response — must include updatedInput to replace the command.
    // Preserve any other tool_input fields (description, timeout, etc.)
    let mut updated_input = tool_input.clone();
    if let Some(obj) = updated_input.as_object_mut() {
        obj.insert(
            "command".to_string(),
            serde_json::Value::String(wrapped),
        );
    }

    let response = serde_json::json!({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": updated_input
        }
    });
    println!("{}", serde_json::to_string(&response)?);
    Ok(())
}

/// PostToolUse: extract decision signals from tool output and save to session memory.
/// Detects: test pass/fail, errors that indicate a failed approach, file modifications.
///
/// Claude Code sends tool_response (not tool_output) with structure:
///   Bash: { "stdout": "...", "stderr": "...", "exitCode": 0 }
///   Edit/Write: { "filePath": "...", "success": true }
fn run_hook_post_tool_use() -> Result<()> {
    let mut input = String::new();
    std::io::stdin()
        .read_to_string(&mut input)
        .context("failed to read hook event from stdin")?;

    let event: serde_json::Value = serde_json::from_str(&input).unwrap_or(serde_json::json!({}));

    let tool_name = event
        .get("tool_name")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let tool_input = event
        .get("tool_input")
        .cloned()
        .unwrap_or_else(|| serde_json::json!({}));

    // Claude Code sends tool_response (structured), not tool_output (flat string).
    // For Bash: { stdout, stderr, exitCode }
    // For Edit/Write: { filePath, success }
    // Fall back to tool_output for backwards compat / testing.
    let tool_response = event.get("tool_response");
    let tool_output: String = if let Some(resp) = tool_response {
        // Bash tool: combine stdout + stderr
        let stdout = resp.get("stdout").and_then(|v| v.as_str()).unwrap_or("");
        let stderr = resp.get("stderr").and_then(|v| v.as_str()).unwrap_or("");
        if !stderr.is_empty() {
            format!("{stdout}\n{stderr}")
        } else {
            stdout.to_string()
        }
    } else {
        // Fallback: flat tool_output string (testing / older versions)
        event
            .get("tool_output")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string()
    };

    if tool_output.is_empty() && tool_name != "Edit" && tool_name != "Write" {
        return Ok(());
    }

    let cwd = event
        .get("cwd")
        .and_then(|v| v.as_str())
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    let Some(context_dir) = find_context_dir(&cwd) else {
        return Ok(());
    };

    let session_path = context_dir.join("session.json");

    // Lock session.json for atomic read-modify-write.
    // Claude Code fires PostToolUse hooks concurrently for parallel tool calls.
    // Without locking, concurrent reads get the same state and one write overwrites the other.
    let _lock = acquire_session_lock(&context_dir).ok();

    let mut state = StructuredSessionMemory::load_or_default(&session_path)?;
    let outcome =
        process_post_tool_use_event(&mut state, tool_name, &tool_input, &tool_output, &cwd);

    if outcome.changed {
        state.save_to_path(&session_path)?;
        append_journal_events(&context_dir, &outcome.journal_events)?;
    }

    // Lock released when _lock is dropped
    Ok(())
}

/// PreCompact: inject structured decisions into context so they survive compaction.
/// This is the key differentiator — Claude remembers WHY decisions were made.
///
/// Claude Code PreCompact hooks receive: { session_id, cwd, hook_event_name, matcher_value }
/// Output is plain text to stdout — Claude Code captures it as additionalContext.
fn run_hook_pre_compact() -> Result<()> {
    // Read stdin (Claude Code sends event JSON, but we only need cwd)
    let mut input = String::new();
    let _ = std::io::stdin().read_to_string(&mut input);
    let event: serde_json::Value = serde_json::from_str(&input).unwrap_or(serde_json::json!({}));

    let cwd = event
        .get("cwd")
        .and_then(|v| v.as_str())
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));

    let Some(context_dir) = find_context_dir(&cwd) else {
        return Ok(());
    };

    let session_path = context_dir.join("session.json");
    if !session_path.exists() {
        return Ok(());
    }

    let state = match StructuredSessionMemory::load_from_path(&session_path) {
        Ok(s) => s,
        Err(_) => return Ok(()),
    };

    let packet = build_restart_packet(&state, &RestartPacketPolicy::default());
    let rendered = render_restart_packet(&packet);
    if rendered.is_empty() {
        return Ok(());
    }

    append_journal_events(
        &context_dir,
        &[JournalEvent {
            ts_unix: now_unix(),
            hook: "PreCompact".to_string(),
            category: "restart_packet_emitted".to_string(),
            summary: "Rendered restart packet for compaction survival".to_string(),
            metadata: serde_json::json!({
                "estimated_tokens": estimate_text(&rendered, ModelFamily::Claude).estimated_tokens,
            }),
        }],
    )?;
    print!("{rendered}");

    Ok(())
}

fn read_file(path: &PathBuf) -> Result<String> {
    fs::read_to_string(path).with_context(|| format!("failed to read {}", path.display()))
}

fn read_session_update(path: &PathBuf) -> Result<SessionMemoryUpdate> {
    let content = read_file(path)?;
    let update = import_session_state_update(&content)?;
    Ok(update)
}

fn import_session_state_update(input: &str) -> Result<SessionMemoryUpdate> {
    serde_json::from_str(input).context("failed to parse session memory update json")
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn post_tool_use_records_failing_signatures() {
        let mut state = StructuredSessionMemory::default();
        let outcome = process_post_tool_use_event(
            &mut state,
            "Bash",
            &json!({ "command": "cargo test auth::tests::delete_user" }),
            "test auth::tests::delete_user ... FAILED\n\ntest result: FAILED. 0 passed; 1 failed;",
            Path::new("/tmp/context-os"),
        );

        assert!(outcome.changed);
        assert!(state
            .failing_signatures
            .contains(&"auth::tests::delete_user".to_string()));
        assert_eq!(state.tests_run.len(), 1);
        assert!(outcome
            .journal_events
            .iter()
            .any(|event| event.category == "failing_signature"));
    }

    #[test]
    fn post_tool_use_records_modified_file() {
        let mut state = StructuredSessionMemory::default();
        let outcome = process_post_tool_use_event(
            &mut state,
            "Edit",
            &json!({ "file_path": "/tmp/context-os/src/lib.rs" }),
            "",
            Path::new("/tmp/context-os"),
        );

        assert!(outcome.changed);
        assert_eq!(state.modified_files, vec!["src/lib.rs".to_string()]);
        assert!(outcome
            .journal_events
            .iter()
            .any(|event| event.category == "modified_file"));
    }

    #[test]
    fn post_tool_use_records_decision_after_success() {
        let mut state = StructuredSessionMemory::default();
        state
            .failing_signatures
            .push("auth::tests::delete_user".to_string());
        state
            .failed_approaches
            .push("error[E0308]: mismatched types".to_string());

        let outcome = process_post_tool_use_event(
            &mut state,
            "Bash",
            &json!({ "command": "cargo test auth::tests::delete_user" }),
            "test result: ok. 1 passed; 0 failed;",
            Path::new("/tmp/context-os"),
        );

        assert!(outcome.changed);
        assert!(state.failing_signatures.is_empty());
        assert_eq!(state.decisions_made.len(), 1);
        assert!(state.decisions_made[0]
            .summary
            .contains("Validated current approach"));
        assert!(outcome
            .journal_events
            .iter()
            .any(|event| event.category == "decision"));
    }

    #[test]
    fn restart_packet_preserves_critical_state_under_budget() {
        let mut state = StructuredSessionMemory::default();
        state.session_objective = Some("Ship compaction-aware decision replay".to_string());
        state.current_subtask = Some("Wire PreCompact to shared restart packet".to_string());
        state.pinned_facts.push(PinnedFact {
            value: "Never drop the latest accepted decision".to_string(),
        });
        state.modified_files = vec![
            "apps/cli/src/main.rs".to_string(),
            "hooks/hooks.json".to_string(),
        ];
        state.pending_next_actions = vec![NextAction {
            summary: "Run compaction-survival benchmarks".to_string(),
        }];
        state.decisions_made = vec![
            DecisionRecord {
                summary: "Initial idea".to_string(),
                rationale: Some("older rationale".to_string()),
            },
            DecisionRecord {
                summary: "Latest accepted decision".to_string(),
                rationale: Some("must survive compaction".to_string()),
            },
        ];
        state.failed_approaches = vec![
            "low-signal note".to_string(),
            "error[E0308] from apps/cli/src/main.rs".to_string(),
        ];
        state.tests_run = (0..10)
            .map(|idx| CommandRecord {
                command: format!("cargo test case_{idx}"),
                outcome: Some("passed".to_string()),
            })
            .collect();
        state.recent_turns = (0..10)
            .map(|idx| RecentTurn {
                role: "assistant".to_string(),
                content: format!("Long recap {idx} {}", "x".repeat(50)),
            })
            .collect();

        let packet = build_restart_packet(
            &state,
            &RestartPacketPolicy {
                max_tokens: 120,
                ..RestartPacketPolicy::default()
            },
        );
        let rendered = render_restart_packet(&packet);
        let estimate = estimate_text(&rendered, ModelFamily::Claude).estimated_tokens;

        assert!(estimate <= 120);
        assert_eq!(
            packet.current_subtask.as_deref(),
            Some("Wire PreCompact to shared restart packet")
        );
        assert!(packet
            .pinned_facts
            .iter()
            .any(|fact| fact.value == "Never drop the latest accepted decision"));
        assert_eq!(
            packet
                .decisions_made
                .last()
                .map(|item| item.summary.as_str()),
            Some("Latest accepted decision")
        );
        assert!(packet.recent_turns.is_empty());
        assert!(packet.tests_run.is_empty());
    }

    #[test]
    fn end_to_end_resilience_packet_keeps_decision_file_and_next_step() {
        let mut state = StructuredSessionMemory::default();
        state.session_objective = Some("Fix delete_user test".to_string());
        state.current_subtask = Some("Stabilize failing API test".to_string());
        state.pending_next_actions = vec![NextAction {
            summary: "Run the full auth test suite".to_string(),
        }];

        process_post_tool_use_event(
            &mut state,
            "Bash",
            &json!({ "command": "cargo test api::tests::delete_user" }),
            "test api::tests::delete_user ... FAILED\nerror[E0308]: mismatched types\ntest result: FAILED. 0 passed; 1 failed;",
            Path::new("/tmp/context-os"),
        );
        process_post_tool_use_event(
            &mut state,
            "Edit",
            &json!({ "file_path": "/tmp/context-os/src/api.rs" }),
            "",
            Path::new("/tmp/context-os"),
        );
        process_post_tool_use_event(
            &mut state,
            "Bash",
            &json!({ "command": "cargo test api::tests::delete_user" }),
            "test result: ok. 1 passed; 0 failed;",
            Path::new("/tmp/context-os"),
        );

        let packet = build_restart_packet(&state, &RestartPacketPolicy::default());
        let rendered = render_restart_packet(&packet);

        assert!(rendered.contains("DECISIONS MADE"));
        assert!(rendered.contains("FAILED APPROACHES TO AVOID"));
        assert!(rendered.contains("src/api.rs"));
        assert!(rendered.contains("Run the full auth test suite"));
        assert!(rendered.contains("Validated current approach"));
    }

    #[test]
    fn should_wrap_handles_cd_and_env_prefixes() {
        // Bare commands
        assert!(should_wrap_command("cargo test"));
        assert!(should_wrap_command("npm run build"));
        assert!(should_wrap_command("pytest -v"));

        // cd && prefixes (how Claude actually runs commands)
        assert!(should_wrap_command("cd /tmp && cargo test"));
        assert!(should_wrap_command("cd src && npm test"));
        assert!(should_wrap_command("cd /app && python -m pytest tests/"));

        // Environment variable prefixes
        assert!(should_wrap_command("RUST_BACKTRACE=1 cargo test"));
        assert!(should_wrap_command("CI=true npm run build"));
        assert!(should_wrap_command("NODE_ENV=test npm test"));

        // Combined: cd + env
        assert!(should_wrap_command("cd /foo && RUST_LOG=debug cargo clippy"));

        // source/env/timeout prefixes
        assert!(should_wrap_command("source ~/.cargo/env && cargo build"));
        assert!(should_wrap_command("env NODE_ENV=test npm test"));
        assert!(should_wrap_command("timeout 120 cargo test"));

        // Should NOT wrap
        assert!(!should_wrap_command("ls -la"));
        assert!(!should_wrap_command("git status"));
        assert!(!should_wrap_command("echo hello"));
        assert!(!should_wrap_command("cat file.txt"));

        // Already wrapped
        assert!(!should_wrap_command("context-os pipe"));
        assert!(!should_wrap_command(
            "cd /foo && cargo test 2>&1 | context-os pipe"
        ));
    }
}
