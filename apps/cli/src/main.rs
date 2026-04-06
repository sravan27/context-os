use std::fs;
use std::io::Read as IoRead;
use std::path::PathBuf;
use std::process::Command;

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
    SessionCompactionPolicy, SessionMemoryDiff, SessionMemoryUpdate, StructuredSessionMemory,
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

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Init(args) => run_init(args),
        Commands::Status(args) => run_status(args),
        Commands::Pipe(args) => run_pipe(args),
        Commands::Handoff(args) => run_handoff(args),
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

    // 1. Build repo memory
    let out_dir = root.join(".context-os").join("repo-memory");
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
                let after = existing
                    .split(marker_end)
                    .nth(1)
                    .unwrap_or("")
                    .to_string();
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

    // 3. Install Claude Code hooks (SessionStart + Stop + UserPromptSubmit)
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

        let handoff_path = root
            .join(".context-os")
            .join("handoff.md")
            .display()
            .to_string();

        // Find the context-os binary
        let bin_path = std::env::current_exe()
            .unwrap_or_else(|_| PathBuf::from("context-os"));
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
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": format!(
                                "cat \"{handoff_path}\" 2>/dev/null || true"
                            ),
                            "timeout": 5
                        }
                    ]
                }
            ],
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": format!(
                                "{bin} status --root \"{}\" 2>/dev/null || true",
                                root.display()
                            ),
                            "timeout": 3
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
        fs::write(
            &settings_path,
            serde_json::to_string_pretty(&settings)?,
        )?;
        eprintln!("installed hooks in .claude/settings.local.json");
    }

    // 4. Ensure .context-os/ is in .gitignore
    let gitignore_path = root.join(".gitignore");
    if gitignore_path.exists() {
        let content = fs::read_to_string(&gitignore_path)?;
        if !content.contains(".context-os/") {
            fs::write(
                &gitignore_path,
                format!("{}\n\n# Context OS local state\n.context-os/\n", content.trim_end()),
            )?;
            eprintln!("added .context-os/ to .gitignore");
        }
    } else {
        fs::write(
            &gitignore_path,
            "# Context OS local state\n.context-os/\n",
        )?;
        eprintln!("created .gitignore with .context-os/");
    }

    eprintln!("done. Claude Code will now start sessions with repo context loaded.");
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
    let context_dir = root.join(".context-os");
    fs::create_dir_all(&context_dir)?;

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
        state.pending_next_actions.push(session_memory::NextAction {
            summary: next,
        });
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

    // Also write a human-readable handoff note
    let handoff_path = context_dir.join("handoff.md");
    let mut note = String::from("# Session Handoff\n\n");
    note.push_str("Read this at the start of a new session to continue where the previous session left off.\n\n");

    // Git state section — always present if in a git repo
    if git.branch.is_some() || !git.uncommitted_files.is_empty() {
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
            for f in git.uncommitted_files.iter().take(15) {
                note.push_str(&format!("  - {f}\n"));
            }
            if git.uncommitted_files.len() > 15 {
                note.push_str(&format!(
                    "  - ...and {} more\n",
                    git.uncommitted_files.len() - 15
                ));
            }
        }
        if let Some(diff_stat) = &git.diff_stat {
            note.push_str(&format!("\n```\n{diff_stat}\n```\n"));
        }
        if let Some(commits) = &git.recent_commits {
            note.push_str("\nRecent commits:\n");
            for line in commits.lines().take(5) {
                note.push_str(&format!("  {line}\n"));
            }
        }
        note.push('\n');
    }

    if let Some(objective) = &state.session_objective {
        note.push_str(&format!("## Objective\n\n{objective}\n\n"));
    }
    if let Some(subtask) = &state.current_subtask {
        note.push_str(&format!("## Current subtask\n\n{subtask}\n\n"));
    }
    if !state.pending_next_actions.is_empty() {
        note.push_str("## Next steps\n\n");
        for action in &state.pending_next_actions {
            note.push_str(&format!("- {}\n", action.summary));
        }
        note.push('\n');
    }
    if !state.modified_files.is_empty() {
        note.push_str("## Modified files\n\n");
        for file in state.modified_files.iter().rev().take(10) {
            note.push_str(&format!("- {file}\n"));
        }
        note.push('\n');
    }
    if !state.decisions_made.is_empty() {
        note.push_str("## Key decisions\n\n");
        for decision in state.decisions_made.iter().rev().take(5) {
            note.push_str(&format!("- {}", decision.summary));
            if let Some(rationale) = &decision.rationale {
                note.push_str(&format!(" ({})", rationale));
            }
            note.push('\n');
        }
        note.push('\n');
    }
    if !state.failing_signatures.is_empty() {
        note.push_str("## Known failures\n\n");
        for sig in &state.failing_signatures {
            note.push_str(&format!("- {sig}\n"));
        }
        note.push('\n');
    }
    if !state.failed_approaches.is_empty() {
        note.push_str("## Failed approaches (don't retry)\n\n");
        for approach in &state.failed_approaches {
            note.push_str(&format!("- {approach}\n"));
        }
        note.push('\n');
    }
    if !state.hard_constraints.is_empty() {
        note.push_str("## Constraints\n\n");
        for constraint in &state.hard_constraints {
            note.push_str(&format!("- {constraint}\n"));
        }
        note.push('\n');
    }
    if !state.pinned_facts.is_empty() {
        note.push_str("## Pinned facts\n\n");
        for fact in &state.pinned_facts {
            note.push_str(&format!("- {}\n", fact.value));
        }
        note.push('\n');
    }

    fs::write(&handoff_path, &note)?;

    // Print the handoff note so user/Claude can see it
    print!("{note}");
    eprintln!("saved to {}", handoff_path.display());
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

fn run_pipe(args: PipeArgs) -> Result<()> {
    let mut input = String::new();
    std::io::stdin()
        .read_to_string(&mut input)
        .context("failed to read stdin")?;

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
        Some(kind_str.parse::<ReducerKind>().map_err(anyhow::Error::msg)?)
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
            println!("  \u{2713} git repository detected (branch: {branch})");
            Some(branch)
        }
        _ => {
            println!("  \u{2717} not a git repository");
            println!("    \u{2192} run `git init` first");
            all_ok = false;
            None
        }
    };
    let _ = branch;

    // 2. .context-os/ directory
    let context_dir = root.join(".context-os");
    if context_dir.is_dir() {
        println!("  \u{2713} .context-os/ directory exists");
    } else {
        println!("  \u{2717} .context-os/ directory missing");
        println!("    \u{2192} run `context-os init` to set up");
        all_ok = false;
    }

    // 3. CLAUDE.md with context-os markers
    let claude_md_path = root.join("CLAUDE.md");
    if claude_md_path.exists() {
        let content = fs::read_to_string(&claude_md_path).unwrap_or_default();
        if content.contains("<!-- context-os:start -->") {
            println!("  \u{2713} CLAUDE.md has context-os block");
        } else {
            println!("  \u{2717} CLAUDE.md exists but missing context-os block");
            println!("    \u{2192} run `context-os init` to add the repo map");
            all_ok = false;
        }
    } else {
        println!("  \u{2717} CLAUDE.md not found");
        println!("    \u{2192} run `context-os init` to generate it");
        all_ok = false;
    }

    // 4. .claude/settings.local.json with hooks
    let settings_path = root.join(".claude").join("settings.local.json");
    if settings_path.exists() {
        let content = fs::read_to_string(&settings_path).unwrap_or_default();
        let has_pre_tool = content.contains("PreToolUse");
        let has_session_start = content.contains("SessionStart");
        let has_prompt_submit = content.contains("UserPromptSubmit");
        let has_stop = content.contains("Stop");
        if has_pre_tool && has_session_start && has_prompt_submit && has_stop {
            println!("  \u{2713} Claude Code hooks installed (PreToolUse, SessionStart, UserPromptSubmit, Stop)");
        } else {
            let mut missing = Vec::new();
            if !has_pre_tool {
                missing.push("PreToolUse");
            }
            if !has_session_start {
                missing.push("SessionStart");
            }
            if !has_prompt_submit {
                missing.push("UserPromptSubmit");
            }
            if !has_stop {
                missing.push("Stop");
            }
            println!(
                "  \u{2717} Claude Code hooks incomplete (missing: {})",
                missing.join(", ")
            );
            println!("    \u{2192} run `context-os init` to install hooks");
            all_ok = false;
        }
    } else {
        println!("  \u{2717} .claude/settings.local.json not found");
        println!("    \u{2192} run `context-os init` to install hooks");
        all_ok = false;
    }

    // 5. .context-os/ in .gitignore
    let gitignore_path = root.join(".gitignore");
    if gitignore_path.exists() {
        let content = fs::read_to_string(&gitignore_path).unwrap_or_default();
        if content.contains(".context-os/") || content.contains(".context-os") {
            println!("  \u{2713} .context-os/ in .gitignore");
        } else {
            println!("  \u{2717} .context-os/ not in .gitignore");
            println!("    \u{2192} add `.context-os/` to your .gitignore");
            all_ok = false;
        }
    } else {
        println!("  \u{2717} .gitignore not found (.context-os/ may be tracked)");
        println!("    \u{2192} run `context-os init` to create .gitignore");
        all_ok = false;
    }

    // 6. handoff.md
    let handoff_path = context_dir.join("handoff.md");
    if handoff_path.exists() {
        let age = handoff_path
            .metadata()
            .and_then(|m| m.modified())
            .ok()
            .and_then(|modified| {
                std::time::SystemTime::now()
                    .duration_since(modified)
                    .ok()
            });
        let age_str = match age {
            Some(d) => {
                let secs = d.as_secs();
                if secs < 60 {
                    format!("{secs} seconds ago")
                } else if secs < 3600 {
                    format!("{} minutes ago", secs / 60)
                } else if secs < 86400 {
                    format!("{} hours ago", secs / 3600)
                } else {
                    format!("{} days ago", secs / 86400)
                }
            }
            None => "unknown age".to_string(),
        };
        println!("  \u{2713} handoff.md exists ({age_str})");
    } else {
        println!("  - handoff.md not found (created on first session end)");
    }

    // 7. session.json
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
            println!("  \u{2713} session.json exists{obj_str}");
        } else {
            println!("  \u{2713} session.json exists (could not parse)");
        }
    } else {
        println!("  - session.json not found (created on first handoff)");
    }

    // Quick benchmark
    println!("\n  Quick benchmark:");

    let registry = ReducerRegistry::default();
    let protections = ProtectionRules::safe_defaults();

    let sample_stack = "\
thread 'main' panicked at 'index out of bounds: the len is 3 but the index is 5', src/main.rs:42:10
stack backtrace:
   0: rust_begin_unwind
             at /rustc/abc123/library/std/src/panicking.rs:616:5
   1: core::panicking::panic_fmt
             at /rustc/abc123/library/core/src/panicking.rs:72:14
   2: core::panicking::panic_bounds_check
             at /rustc/abc123/library/core/src/panicking.rs:208:5
   3: <usize as core::slice::index::SliceIndex<[T]>>::index
             at /rustc/abc123/library/core/src/slice/index.rs:255:10
   4: core::slice::index::<impl core::ops::index::Index<I> for [T]>::index
             at /rustc/abc123/library/core/src/slice/index.rs:18:9
   5: alloc::vec::impl$12::index
             at /rustc/abc123/library/alloc/src/vec/mod.rs:2770:9
   6: myapp::process_items
             at ./src/main.rs:42:10
   7: myapp::main
             at ./src/main.rs:15:5
   8: core::ops::function::FnOnce::call_once
             at /rustc/abc123/library/core/src/ops/function.rs:250:5
   9: std::sys::backtrace::__rust_begin_short_backtrace
             at /rustc/abc123/library/std/src/sys/backtrace.rs:152:18
  10: std::rt::lang_start::{{closure}}
             at /rustc/abc123/library/std/src/rt.rs:195:18
  11: std::rt::lang_start_internal
             at /rustc/abc123/library/std/src/rt.rs:174:5
  12: main
  13: __libc_start_main
  14: _start";

    let sample_test_log = "\
running 12 tests
test auth::tests::login_success ... ok
test auth::tests::login_bad_password ... ok
test auth::tests::login_expired_token ... ok
test auth::tests::refresh_token ... ok
test db::tests::connection_pool ... ok
test db::tests::migration_up ... ok
test db::tests::migration_down ... ok
test api::tests::get_users ... ok
test api::tests::create_user ... ok
test api::tests::delete_user ... FAILED
test api::tests::update_user ... ok
test api::tests::list_users ... ok

failures:

---- api::tests::delete_user stdout ----
thread 'api::tests::delete_user' panicked at 'assertion failed: response.status() == 200'

failures:
    api::tests::delete_user

test result: FAILED. 11 passed; 1 failed; 0 ignored";

    // Stack trace benchmark
    let before_stack = estimate_text(sample_stack, ModelFamily::Claude).estimated_tokens;
    if let Some(result) = registry.reduce(
        ReducerKind::StackTrace,
        sample_stack,
        ReductionMode::Safe,
        &protections,
    ) {
        let after_stack = estimate_text(&result.output, ModelFamily::Claude).estimated_tokens;
        if before_stack > 0 {
            let pct = ((before_stack as f64 - after_stack as f64) / before_stack as f64 * 100.0) as u32;
            println!("    Stack trace: {before_stack} \u{2192} {after_stack} tokens ({pct}% reduction)");
        }
    } else {
        println!("    Stack trace: reducer not available");
    }

    // Test log benchmark
    let before_test = estimate_text(sample_test_log, ModelFamily::Claude).estimated_tokens;
    if let Some(result) = registry.reduce(
        ReducerKind::TestLog,
        sample_test_log,
        ReductionMode::Safe,
        &protections,
    ) {
        let after_test = estimate_text(&result.output, ModelFamily::Claude).estimated_tokens;
        if before_test > 0 {
            let pct = ((before_test as f64 - after_test as f64) / before_test as f64 * 100.0) as u32;
            println!("    Test log:    {before_test} \u{2192} {after_test} tokens ({pct}% reduction)");
        }
    } else {
        println!("    Test log:    reducer not available");
    }

    // Final status
    if all_ok {
        println!("\n  Status: ready\n");
    } else {
        println!("\n  Status: needs setup (run `context-os init`)\n");
    }

    Ok(())
}

fn run_hook(command: HookCommand) -> Result<()> {
    match command.command {
        HookSubcommand::PreToolUse => run_hook_pre_tool_use(),
    }
}

/// Patterns that produce output worth reducing.
const REDUCIBLE_PREFIXES: &[&str] = &[
    "cargo test",
    "cargo build",
    "cargo clippy",
    "cargo check",
    "npm test",
    "npm run test",
    "npm run build",
    "pnpm test",
    "pnpm run test",
    "pnpm run build",
    "yarn test",
    "yarn build",
    "pytest",
    "python -m pytest",
    "python3 -m pytest",
    "go test",
    "go build",
    "make test",
    "make build",
    "make check",
    "npx tsc",
    "npx eslint",
    "eslint",
    "gradle build",
    "gradle test",
    "mvn test",
    "mvn compile",
];

fn should_wrap_command(cmd: &str) -> bool {
    let trimmed = cmd.trim();
    // Skip if already piped through context-os
    if trimmed.contains("context-os") {
        return false;
    }
    // Match against known reducible command patterns
    for prefix in REDUCIBLE_PREFIXES {
        if trimmed.starts_with(prefix) {
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
    let event: serde_json::Value =
        serde_json::from_str(&input).unwrap_or(serde_json::json!({}));

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
    let bin_path = std::env::current_exe()
        .unwrap_or_else(|_| PathBuf::from("context-os"));
    let bin = bin_path.display().to_string();

    // Wrap the command to pipe output through context-os pipe.
    // Preserve the original exit code so Claude sees test failures correctly.
    // Use $() to capture output, then pipe through reducer.
    let wrapped = format!(
        r#"_co_rc=0; _co_out=$({command} 2>&1) || _co_rc=$?; printf '%s\n' "$_co_out" | "{bin}" pipe; exit "$_co_rc""#
    );

    // Output the PreToolUse response
    let response = serde_json::json!({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {
                "command": wrapped
            }
        }
    });
    println!("{}", serde_json::to_string(&response)?);
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
