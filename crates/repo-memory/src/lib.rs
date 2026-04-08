use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactKind {
    Routes,
    Modules,
    Schema,
    Components,
    Configs,
    Architecture,
    DependencyMap,
    RecentHotspots,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ArtifactManifestEntry {
    pub kind: ArtifactKind,
    pub json_path: PathBuf,
    pub markdown_path: PathBuf,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RouteEntry {
    pub route: String,
    pub file: String,
    pub kind: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ModuleEntry {
    pub path: String,
    pub language: String,
    pub category: String,
    pub size_bytes: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ConfigEntry {
    pub path: String,
    pub format: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ComponentEntry {
    pub path: String,
    pub component_name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub struct DependencyEntry {
    pub name: String,
    pub version: String,
    pub source: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ArchitectureSummary {
    pub framework: Option<String>,
    pub top_level_dirs: Vec<String>,
    pub source_file_count: usize,
    pub config_file_count: usize,
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RepoMemoryArtifacts {
    pub root: String,
    pub routes: Vec<RouteEntry>,
    pub modules: Vec<ModuleEntry>,
    pub schema: Vec<String>,
    pub components: Vec<ComponentEntry>,
    pub configs: Vec<ConfigEntry>,
    pub architecture: ArchitectureSummary,
    pub dependency_map: Vec<DependencyEntry>,
    pub recent_hotspots: Vec<String>,
}

#[derive(Debug, Error)]
pub enum RepoMemoryError {
    #[error("failed to read repository path {path}: {source}")]
    Read {
        path: String,
        #[source]
        source: std::io::Error,
    },
    #[error("failed to write artifact path {path}: {source}")]
    Write {
        path: String,
        #[source]
        source: std::io::Error,
    },
    #[error("failed to parse package.json at {path}: {source}")]
    PackageJson {
        path: String,
        #[source]
        source: serde_json::Error,
    },
    #[error("failed to parse Cargo.toml at {path}: {source}")]
    CargoToml {
        path: String,
        #[source]
        source: toml::de::Error,
    },
}

pub fn default_manifest(root: impl AsRef<Path>) -> Vec<ArtifactManifestEntry> {
    let root = root.as_ref();
    vec![
        manifest_entry(root, ArtifactKind::Routes, "routes"),
        manifest_entry(root, ArtifactKind::Modules, "modules"),
        manifest_entry(root, ArtifactKind::Schema, "schema"),
        manifest_entry(root, ArtifactKind::Components, "components"),
        manifest_entry(root, ArtifactKind::Configs, "configs"),
        manifest_entry(root, ArtifactKind::Architecture, "architecture"),
        manifest_entry(root, ArtifactKind::DependencyMap, "dependency-map"),
        manifest_entry(root, ArtifactKind::RecentHotspots, "recent-hotspots"),
    ]
}

pub fn build_repo_memory(root: impl AsRef<Path>) -> Result<RepoMemoryArtifacts, RepoMemoryError> {
    let root = root.as_ref();
    let mut files = Vec::new();
    collect_files(root, root, &mut files)?;
    files.sort();

    let framework = detect_framework(root, &files)?;
    let routes = extract_routes(&files);
    let modules = extract_modules(root, &files)?;
    let configs = extract_configs(&files);
    let components = extract_components(&files);
    let dependency_map = extract_dependencies(root)?;
    let top_level_dirs = top_level_dirs(root)?;

    let architecture = ArchitectureSummary {
        framework: framework.clone(),
        top_level_dirs,
        source_file_count: modules.len(),
        config_file_count: configs.len(),
        notes: architecture_notes(framework.as_deref(), routes.len(), components.len()),
    };

    Ok(RepoMemoryArtifacts {
        root: root.display().to_string(),
        routes,
        modules,
        schema: Vec::new(),
        components,
        configs,
        architecture,
        dependency_map,
        recent_hotspots: Vec::new(),
    })
}

pub fn write_artifacts(
    artifacts: &RepoMemoryArtifacts,
    out_dir: impl AsRef<Path>,
) -> Result<Vec<ArtifactManifestEntry>, RepoMemoryError> {
    let out_dir = out_dir.as_ref();
    fs::create_dir_all(out_dir).map_err(|source| RepoMemoryError::Write {
        path: out_dir.display().to_string(),
        source,
    })?;

    let manifest = default_manifest(out_dir);
    for entry in &manifest {
        match entry.kind {
            ArtifactKind::Routes => write_pair(
                entry,
                &artifacts.routes,
                render_routes_md(&artifacts.routes),
            )?,
            ArtifactKind::Modules => write_pair(
                entry,
                &artifacts.modules,
                render_modules_md(&artifacts.modules),
            )?,
            ArtifactKind::Schema => write_pair(
                entry,
                &artifacts.schema,
                "# Schema\n\nNo schema artifacts detected in this scan.\n".to_string(),
            )?,
            ArtifactKind::Components => write_pair(
                entry,
                &artifacts.components,
                render_components_md(&artifacts.components),
            )?,
            ArtifactKind::Configs => write_pair(
                entry,
                &artifacts.configs,
                render_configs_md(&artifacts.configs),
            )?,
            ArtifactKind::Architecture => write_pair(
                entry,
                &artifacts.architecture,
                render_architecture_md(&artifacts.architecture),
            )?,
            ArtifactKind::DependencyMap => write_pair(
                entry,
                &artifacts.dependency_map,
                render_dependencies_md(&artifacts.dependency_map),
            )?,
            ArtifactKind::RecentHotspots => write_pair(
                entry,
                &artifacts.recent_hotspots,
                "# Recent Hotspots\n\nNo hotspot data captured yet.\n".to_string(),
            )?,
        }
    }

    Ok(manifest)
}

pub fn build_and_write(
    root: impl AsRef<Path>,
    out_dir: impl AsRef<Path>,
) -> Result<RepoMemoryArtifacts, RepoMemoryError> {
    let artifacts = build_repo_memory(root)?;
    write_artifacts(&artifacts, out_dir)?;
    Ok(artifacts)
}

fn manifest_entry(root: &Path, kind: ArtifactKind, name: &str) -> ArtifactManifestEntry {
    ArtifactManifestEntry {
        kind,
        json_path: root.join(format!("{name}.json")),
        markdown_path: root.join(format!("{name}.md")),
    }
}

fn collect_files(
    root: &Path,
    current: &Path,
    files: &mut Vec<String>,
) -> Result<(), RepoMemoryError> {
    let entries = fs::read_dir(current).map_err(|source| RepoMemoryError::Read {
        path: current.display().to_string(),
        source,
    })?;

    for entry in entries {
        let entry = entry.map_err(|source| RepoMemoryError::Read {
            path: current.display().to_string(),
            source,
        })?;
        let path = entry.path();
        let file_name = entry.file_name();
        let file_name = file_name.to_string_lossy();

        if should_ignore(&file_name) {
            continue;
        }

        if path.is_dir() {
            collect_files(root, &path, files)?;
        } else if path.is_file() {
            let relative = path
                .strip_prefix(root)
                .unwrap_or(&path)
                .to_string_lossy()
                .replace('\\', "/");
            files.push(relative);
        }
    }

    Ok(())
}

fn should_ignore(file_name: &str) -> bool {
    matches!(
        file_name,
        ".git" | "node_modules" | "target" | "dist" | "build" | "coverage" | ".next"
    )
}

fn detect_framework(root: &Path, files: &[String]) -> Result<Option<String>, RepoMemoryError> {
    // Count source files by language to determine the dominant one
    let rs_count = files.iter().filter(|f| f.ends_with(".rs")).count();
    let go_count = files.iter().filter(|f| f.ends_with(".go")).count();
    let py_count = files.iter().filter(|f| f.ends_with(".py")).count();
    let ts_count = files
        .iter()
        .filter(|f| f.ends_with(".ts") || f.ends_with(".tsx"))
        .count();
    let js_count = files
        .iter()
        .filter(|f| f.ends_with(".js") || f.ends_with(".jsx"))
        .count();
    let java_count = files.iter().filter(|f| f.ends_with(".java")).count();

    // Rust workspace (Cargo.toml at root with [workspace])
    let cargo_toml = root.join("Cargo.toml");
    if cargo_toml.exists() && rs_count > 0 {
        let content = fs::read_to_string(&cargo_toml).unwrap_or_default();
        if content.contains("[workspace]") {
            return Ok(Some("rust-workspace".to_string()));
        }
        if rs_count >= go_count && rs_count >= py_count && rs_count >= ts_count {
            return Ok(Some("rust".to_string()));
        }
    }

    // Go module
    if root.join("go.mod").exists() && go_count > 0 {
        return Ok(Some("go".to_string()));
    }

    // JS/TS frameworks — check package.json
    let package_json = root.join("package.json");
    if package_json.exists() {
        let content =
            fs::read_to_string(&package_json).map_err(|source| RepoMemoryError::Read {
                path: package_json.display().to_string(),
                source,
            })?;
        let parsed = serde_json::from_str::<serde_json::Value>(&content).map_err(|source| {
            RepoMemoryError::PackageJson {
                path: package_json.display().to_string(),
                source,
            }
        })?;

        if parsed
            .get("dependencies")
            .and_then(|deps| deps.get("next"))
            .is_some()
        {
            return Ok(Some("nextjs".to_string()));
        }
        if parsed
            .get("dependencies")
            .and_then(|deps| deps.get("react"))
            .is_some()
        {
            return Ok(Some("react".to_string()));
        }
        if ts_count + js_count > 0 {
            return Ok(Some("node".to_string()));
        }
    }

    // Java
    if root.join("pom.xml").exists() || root.join("build.gradle").exists() {
        return Ok(Some("java".to_string()));
    }

    // Python — only if it's actually a Python-primary project
    if root.join("pyproject.toml").exists()
        || root.join("setup.py").exists()
        || root.join("setup.cfg").exists()
    {
        if py_count >= rs_count && py_count >= go_count && py_count >= ts_count {
            return Ok(Some("python".to_string()));
        }
    }

    // Fallback: dominant language by file count
    let max_count = *[
        rs_count,
        go_count,
        py_count,
        ts_count + js_count,
        java_count,
    ]
    .iter()
    .max()
    .unwrap_or(&0);
    if max_count > 0 {
        if rs_count == max_count {
            return Ok(Some("rust".to_string()));
        }
        if go_count == max_count {
            return Ok(Some("go".to_string()));
        }
        if ts_count + js_count == max_count {
            return Ok(Some("node".to_string()));
        }
        if py_count == max_count {
            return Ok(Some("python".to_string()));
        }
        if java_count == max_count {
            return Ok(Some("java".to_string()));
        }
    }

    Ok(None)
}

fn extract_routes(files: &[String]) -> Vec<RouteEntry> {
    let mut routes = Vec::new();

    for file in files {
        if let Some(route) = next_app_route(file) {
            routes.push(RouteEntry {
                route,
                file: file.clone(),
                kind: "next_app".to_string(),
            });
            continue;
        }

        if let Some(route) = next_pages_route(file) {
            routes.push(RouteEntry {
                route,
                file: file.clone(),
                kind: "next_pages".to_string(),
            });
            continue;
        }

        if let Some(route) = src_routes_path(file) {
            routes.push(RouteEntry {
                route,
                file: file.clone(),
                kind: "src_routes".to_string(),
            });
        }
    }

    routes.sort_by(|a, b| a.route.cmp(&b.route).then(a.file.cmp(&b.file)));
    routes
}

fn next_app_route(file: &str) -> Option<String> {
    if !file.starts_with("app/") {
        return None;
    }
    if !(file.ends_with("/page.tsx")
        || file.ends_with("/page.ts")
        || file.ends_with("/page.jsx")
        || file.ends_with("/page.js"))
    {
        return None;
    }
    let route = file
        .trim_start_matches("app/")
        .trim_end_matches("page.tsx")
        .trim_end_matches("page.ts")
        .trim_end_matches("page.jsx")
        .trim_end_matches("page.js")
        .trim_end_matches('/');
    if route.is_empty() {
        Some("/".to_string())
    } else {
        Some(format!("/{}", route))
    }
}

fn next_pages_route(file: &str) -> Option<String> {
    if !file.starts_with("pages/") {
        return None;
    }
    if !(file.ends_with(".tsx")
        || file.ends_with(".ts")
        || file.ends_with(".jsx")
        || file.ends_with(".js"))
    {
        return None;
    }
    if file.contains("/api/") {
        return Some(format!(
            "/api/{}",
            file.trim_start_matches("pages/api/")
                .trim_end_matches(".tsx")
                .trim_end_matches(".ts")
                .trim_end_matches(".jsx")
                .trim_end_matches(".js")
        ));
    }
    let route = file
        .trim_start_matches("pages/")
        .trim_end_matches(".tsx")
        .trim_end_matches(".ts")
        .trim_end_matches(".jsx")
        .trim_end_matches(".js");
    let route = if route == "index" {
        "/".to_string()
    } else {
        format!("/{route}")
    };
    Some(route)
}

fn src_routes_path(file: &str) -> Option<String> {
    if file.starts_with("src/routes/")
        && (file.ends_with(".ts") || file.ends_with(".tsx") || file.ends_with(".js"))
    {
        let route = file
            .trim_start_matches("src/routes/")
            .trim_end_matches(".tsx")
            .trim_end_matches(".ts")
            .trim_end_matches(".js");
        Some(format!("/{}", route.trim_end_matches("/index")))
    } else {
        None
    }
}

fn extract_modules(root: &Path, files: &[String]) -> Result<Vec<ModuleEntry>, RepoMemoryError> {
    let mut modules = Vec::new();
    for file in files {
        if !is_source_file(file) {
            continue;
        }
        if is_config_file(file) {
            continue;
        }
        let path = root.join(file);
        let metadata = fs::metadata(&path).map_err(|source| RepoMemoryError::Read {
            path: path.display().to_string(),
            source,
        })?;
        modules.push(ModuleEntry {
            path: file.clone(),
            language: detect_language(file),
            category: classify_module(file),
            size_bytes: metadata.len(),
        });
    }
    modules.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(modules)
}

fn is_source_file(file: &str) -> bool {
    matches!(
        file.rsplit('.').next(),
        Some(
            "ts" | "tsx"
                | "js"
                | "jsx"
                | "py"
                | "rs"
                | "go"
                | "java"
                | "kt"
                | "swift"
                | "rb"
                | "ex"
                | "exs"
        )
    )
}

fn detect_language(file: &str) -> String {
    match file.rsplit('.').next() {
        Some("ts") => "typescript".to_string(),
        Some("tsx") => "typescript-react".to_string(),
        Some("js") => "javascript".to_string(),
        Some("jsx") => "javascript-react".to_string(),
        Some("py") => "python".to_string(),
        Some("rs") => "rust".to_string(),
        Some("go") => "go".to_string(),
        Some("java") => "java".to_string(),
        Some("kt") => "kotlin".to_string(),
        Some("swift") => "swift".to_string(),
        Some("rb") => "ruby".to_string(),
        Some("ex" | "exs") => "elixir".to_string(),
        _ => "unknown".to_string(),
    }
}

fn classify_module(file: &str) -> String {
    // Tests
    if file.contains("/test")
        || file.contains("/tests/")
        || file.contains(".spec.")
        || file.contains(".test.")
        || file.contains("_test.go")
        || file.contains("_test.rs")
        || file.ends_with("_test.py")
        || file.starts_with("test_")
    {
        return "test".to_string();
    }
    // Rust: lib.rs = library root, main.rs = binary entry
    if file.ends_with("/lib.rs") {
        return "lib".to_string();
    }
    if file.ends_with("/main.rs") {
        return "bin".to_string();
    }
    // Rust: mod.rs
    if file.ends_with("/mod.rs") {
        return "module".to_string();
    }
    // Frontend components
    if file.contains("/components/") {
        return "component".to_string();
    }
    // Routes / pages
    if file.contains("/routes/") || file.starts_with("app/") || file.starts_with("pages/") {
        return "route".to_string();
    }
    // Go: cmd/ = entrypoints, internal/ = private packages, pkg/ = public packages
    if file.starts_with("cmd/") || file.contains("/cmd/") {
        return "bin".to_string();
    }
    if file.contains("/internal/") || file.starts_with("internal/") {
        return "internal".to_string();
    }
    if file.contains("/pkg/") || file.starts_with("pkg/") {
        return "lib".to_string();
    }
    // Python: __init__.py, __main__.py
    if file.ends_with("__init__.py") {
        return "package".to_string();
    }
    if file.ends_with("__main__.py") {
        return "bin".to_string();
    }
    "module".to_string()
}

fn extract_configs(files: &[String]) -> Vec<ConfigEntry> {
    let mut configs = Vec::new();
    for file in files {
        if is_config_file(file) {
            configs.push(ConfigEntry {
                path: file.clone(),
                format: detect_config_format(file),
            });
        }
    }
    configs.sort_by(|a, b| a.path.cmp(&b.path));
    configs
}

fn is_config_file(file: &str) -> bool {
    matches!(
        file,
        "package.json"
            | "tsconfig.json"
            | "next.config.js"
            | "next.config.mjs"
            | "Cargo.toml"
            | "pyproject.toml"
            | ".context-os.json"
    ) || file.ends_with(".toml")
        || file.ends_with(".yaml")
        || file.ends_with(".yml")
        || file.ends_with(".ini")
        || file.ends_with(".json")
}

fn detect_config_format(file: &str) -> String {
    if file.ends_with(".toml") {
        "toml".to_string()
    } else if file.ends_with(".yaml") || file.ends_with(".yml") {
        "yaml".to_string()
    } else if file.ends_with(".ini") {
        "ini".to_string()
    } else if file.ends_with(".json") {
        "json".to_string()
    } else if file.ends_with(".js") || file.ends_with(".mjs") {
        "javascript".to_string()
    } else {
        "unknown".to_string()
    }
}

fn extract_components(files: &[String]) -> Vec<ComponentEntry> {
    let mut components = Vec::new();
    for file in files {
        if !(file.ends_with(".tsx") || file.ends_with(".jsx")) {
            continue;
        }
        let Some(name) = Path::new(file).file_stem().and_then(|stem| stem.to_str()) else {
            continue;
        };
        if name
            .chars()
            .next()
            .map(|ch| ch.is_uppercase())
            .unwrap_or(false)
        {
            components.push(ComponentEntry {
                path: file.clone(),
                component_name: name.to_string(),
            });
        }
    }
    components.sort_by(|a, b| a.path.cmp(&b.path));
    components
}

fn extract_dependencies(root: &Path) -> Result<Vec<DependencyEntry>, RepoMemoryError> {
    let mut dependencies = BTreeSet::new();

    let package_json = root.join("package.json");
    if package_json.exists() {
        let content =
            fs::read_to_string(&package_json).map_err(|source| RepoMemoryError::Read {
                path: package_json.display().to_string(),
                source,
            })?;
        let parsed = serde_json::from_str::<serde_json::Value>(&content).map_err(|source| {
            RepoMemoryError::PackageJson {
                path: package_json.display().to_string(),
                source,
            }
        })?;
        for source in ["dependencies", "devDependencies"] {
            if let Some(map) = parsed.get(source).and_then(|value| value.as_object()) {
                for (name, version) in map {
                    dependencies.insert(DependencyEntry {
                        name: name.clone(),
                        version: version.as_str().unwrap_or("*").to_string(),
                        source: source.to_string(),
                    });
                }
            }
        }
    }

    let cargo_toml = root.join("Cargo.toml");
    if cargo_toml.exists() {
        let content = fs::read_to_string(&cargo_toml).map_err(|source| RepoMemoryError::Read {
            path: cargo_toml.display().to_string(),
            source,
        })?;
        let parsed = toml::from_str::<toml::Value>(&content).map_err(|source| {
            RepoMemoryError::CargoToml {
                path: cargo_toml.display().to_string(),
                source,
            }
        })?;
        for table_name in ["dependencies", "workspace.dependencies"] {
            let table = match table_name {
                "dependencies" => parsed.get("dependencies"),
                "workspace.dependencies" => parsed
                    .get("workspace")
                    .and_then(|workspace| workspace.get("dependencies")),
                _ => None,
            };
            if let Some(map) = table.and_then(|value| value.as_table()) {
                for (name, version) in map {
                    dependencies.insert(DependencyEntry {
                        name: name.clone(),
                        version: version.to_string().replace('"', ""),
                        source: table_name.to_string(),
                    });
                }
            }
        }
    }

    Ok(dependencies.into_iter().collect())
}

fn top_level_dirs(root: &Path) -> Result<Vec<String>, RepoMemoryError> {
    let entries = fs::read_dir(root).map_err(|source| RepoMemoryError::Read {
        path: root.display().to_string(),
        source,
    })?;
    let mut dirs = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|source| RepoMemoryError::Read {
            path: root.display().to_string(),
            source,
        })?;
        let path = entry.path();
        if path.is_dir() {
            let name = entry.file_name().to_string_lossy().to_string();
            if !should_ignore(&name) {
                dirs.push(name);
            }
        }
    }
    dirs.sort();
    Ok(dirs)
}

fn architecture_notes(
    framework: Option<&str>,
    route_count: usize,
    component_count: usize,
) -> Vec<String> {
    let mut notes = Vec::new();
    if let Some(framework) = framework {
        notes.push(format!("Detected framework: {framework}"));
    }
    notes.push(format!("Detected {route_count} route entries"));
    notes.push(format!("Detected {component_count} component entries"));
    notes
}

fn write_pair<T: Serialize>(
    entry: &ArtifactManifestEntry,
    json_value: &T,
    markdown_value: String,
) -> Result<(), RepoMemoryError> {
    let json = serde_json::to_string_pretty(json_value).expect("serializable artifacts");
    fs::write(&entry.json_path, json).map_err(|source| RepoMemoryError::Write {
        path: entry.json_path.display().to_string(),
        source,
    })?;
    fs::write(&entry.markdown_path, markdown_value).map_err(|source| RepoMemoryError::Write {
        path: entry.markdown_path.display().to_string(),
        source,
    })?;
    Ok(())
}

fn render_routes_md(routes: &[RouteEntry]) -> String {
    let mut out = String::from("# Routes\n\n");
    if routes.is_empty() {
        out.push_str("No routes detected.\n");
        return out;
    }
    for route in routes {
        out.push_str(&format!(
            "- `{}` -> `{}` ({})\n",
            route.route, route.file, route.kind
        ));
    }
    out
}

fn render_modules_md(modules: &[ModuleEntry]) -> String {
    let mut out = String::from("# Modules\n\n");
    if modules.is_empty() {
        out.push_str("No source modules detected.\n");
        return out;
    }
    for module in modules {
        out.push_str(&format!(
            "- `{}` [{} | {} | {} bytes]\n",
            module.path, module.language, module.category, module.size_bytes
        ));
    }
    out
}

fn render_components_md(components: &[ComponentEntry]) -> String {
    let mut out = String::from("# Components\n\n");
    if components.is_empty() {
        out.push_str("No React-style components detected.\n");
        return out;
    }
    for component in components {
        out.push_str(&format!(
            "- `{}` -> `{}`\n",
            component.component_name, component.path
        ));
    }
    out
}

fn render_configs_md(configs: &[ConfigEntry]) -> String {
    let mut out = String::from("# Configs\n\n");
    if configs.is_empty() {
        out.push_str("No config files detected.\n");
        return out;
    }
    for config in configs {
        out.push_str(&format!("- `{}` ({})\n", config.path, config.format));
    }
    out
}

fn render_architecture_md(summary: &ArchitectureSummary) -> String {
    let mut out = String::from("# Architecture\n\n");
    out.push_str(&format!(
        "- Framework: {}\n",
        summary.framework.as_deref().unwrap_or("unknown")
    ));
    out.push_str(&format!("- Source files: {}\n", summary.source_file_count));
    out.push_str(&format!("- Config files: {}\n", summary.config_file_count));
    out.push_str(&format!(
        "- Top-level directories: {}\n",
        if summary.top_level_dirs.is_empty() {
            "none".to_string()
        } else {
            summary.top_level_dirs.join(", ")
        }
    ));
    if !summary.notes.is_empty() {
        out.push_str("\n## Notes\n\n");
        for note in &summary.notes {
            out.push_str(&format!("- {note}\n"));
        }
    }
    out
}

fn render_dependencies_md(dependencies: &[DependencyEntry]) -> String {
    let mut out = String::from("# Dependency Map\n\n");
    if dependencies.is_empty() {
        out.push_str("No dependencies detected.\n");
        return out;
    }
    for dependency in dependencies {
        out.push_str(&format!(
            "- `{}` = `{}` ({})\n",
            dependency.name, dependency.version, dependency.source
        ));
    }
    out
}

/// Render a compact CLAUDE.md from repo memory artifacts.
/// This is the repo-facing companion to Context OS's resilience layer:
/// reduce rediscovery waste and keep Claude focused when limits are tight.
pub fn render_claude_md(artifacts: &RepoMemoryArtifacts) -> String {
    let mut out = String::new();

    // --- BEHAVIOR RULES ---
    // These directly reduce message waste. Every line here saves real usage.
    out.push_str("# How to work in this repo\n\n");
    out.push_str("- DO NOT explore or scan the repo. The map below has what you need.\n");
    out.push_str("- Read only files you will change. Use the map to find them.\n");
    out.push_str("- State your plan in 1-2 sentences, then execute. Do not explain what you are about to do at length.\n");
    out.push_str("- After making changes, show only what changed and why. Skip the recap.\n");
    out.push_str("- When running commands, if output is long, focus on errors/failures only.\n");
    out.push_str("- Batch related file edits into one response instead of one-file-at-a-time.\n");

    // --- SESSION CONTINUITY ---
    out.push_str("\n# Session continuity\n\n");
    out.push_str("If Context OS injects a restart packet or `.context-os/handoff.md` exists, read it first. ");
    out.push_str("Use it to recover the objective, current subtask, validated decisions, failed approaches, and modified files before doing new exploration. ");
    out.push_str("Do not re-attempt anything listed under failed approaches.\n");

    // --- REPO MAP ---
    out.push_str("\n# Repo map\n\n");
    if let Some(framework) = &artifacts.architecture.framework {
        out.push_str(&format!("**{}**", framework));
    }
    out.push_str(&format!(
        " | {} source files | {} configs",
        artifacts.architecture.source_file_count, artifacts.architecture.config_file_count
    ));
    if !artifacts.architecture.top_level_dirs.is_empty() {
        out.push_str(&format!(
            " | dirs: {}",
            artifacts.architecture.top_level_dirs.join(", ")
        ));
    }
    out.push('\n');

    // Routes (web frameworks)
    if !artifacts.routes.is_empty() {
        out.push_str("\n## Routes\n\n");
        for route in &artifacts.routes {
            out.push_str(&format!("- `{}` -> `{}`\n", route.route, route.file));
        }
    }

    // Source modules — grouped by top-level directory for large projects,
    // by category for small ones
    if !artifacts.modules.is_empty() {
        out.push_str("\n## Source\n\n");
        if artifacts.modules.len() > 30 {
            // Large project: group by top-level directory, show counts + key files
            render_modules_grouped(&artifacts.modules, &mut out);
        } else {
            // Small project: show by category
            let mut by_category: std::collections::BTreeMap<&str, Vec<&ModuleEntry>> =
                std::collections::BTreeMap::new();
            for module in &artifacts.modules {
                // Skip test files in the map — they're findable by convention
                if module.category == "test" || module.category == "package" {
                    continue;
                }
                by_category
                    .entry(&module.category)
                    .or_default()
                    .push(module);
            }
            for (category, modules) in &by_category {
                if modules.len() <= 5 {
                    let paths: Vec<&str> = modules.iter().map(|m| m.path.as_str()).collect();
                    out.push_str(&format!("**{category}**: {}\n", paths.join(", ")));
                } else {
                    out.push_str(&format!("**{category}** ({} files): ", modules.len()));
                    let paths: Vec<&str> =
                        modules.iter().take(5).map(|m| m.path.as_str()).collect();
                    out.push_str(&paths.join(", "));
                    out.push_str(&format!(", ...+{} more\n", modules.len() - 5));
                }
            }
        }
        // Show test count without listing paths
        let test_count = artifacts
            .modules
            .iter()
            .filter(|m| m.category == "test")
            .count();
        if test_count > 0 {
            out.push_str(&format!(
                "**tests**: {test_count} test files (not listed, find by convention)\n"
            ));
        }
    }

    // Components (React/frontend)
    if !artifacts.components.is_empty() {
        out.push_str("\n## Components\n\n");
        let names: Vec<&str> = artifacts
            .components
            .iter()
            .map(|c| c.component_name.as_str())
            .collect();
        out.push_str(&names.join(", "));
        out.push('\n');
    }

    // Dependencies — only show key ones for large dep lists
    if !artifacts.dependency_map.is_empty() {
        out.push_str("\n## Key dependencies\n\n");
        if artifacts.dependency_map.len() <= 15 {
            let deps: Vec<String> = artifacts
                .dependency_map
                .iter()
                .map(|d| format!("{}@{}", d.name, d.version))
                .collect();
            out.push_str(&deps.join(", "));
        } else {
            // Large dep list: show first 10 + count
            let deps: Vec<String> = artifacts
                .dependency_map
                .iter()
                .take(10)
                .map(|d| format!("{}@{}", d.name, d.version))
                .collect();
            out.push_str(&deps.join(", "));
            out.push_str(&format!(
                ", ...+{} more",
                artifacts.dependency_map.len() - 10
            ));
        }
        out.push('\n');
    }

    out
}

/// For large projects, group modules by their top-level directory
/// and show counts + key entry points.
fn render_modules_grouped(modules: &[ModuleEntry], out: &mut String) {
    let mut by_dir: std::collections::BTreeMap<String, Vec<&ModuleEntry>> =
        std::collections::BTreeMap::new();

    for module in modules {
        // Skip tests and __init__.py in the grouped view
        if module.category == "test" || module.category == "package" {
            continue;
        }
        let dir = module.path.split('/').next().unwrap_or(".").to_string();
        by_dir.entry(dir).or_default().push(module);
    }

    for (dir, dir_modules) in &by_dir {
        // Show entry points (lib, bin) first, then count the rest
        let entry_points: Vec<&str> = dir_modules
            .iter()
            .filter(|m| m.category == "lib" || m.category == "bin")
            .map(|m| m.path.as_str())
            .collect();
        if !entry_points.is_empty() {
            out.push_str(&format!(
                "**{dir}/**: {} files, entry: {}\n",
                dir_modules.len(),
                entry_points.join(", ")
            ));
        } else if dir_modules.len() <= 3 {
            let paths: Vec<&str> = dir_modules.iter().map(|m| m.path.as_str()).collect();
            out.push_str(&format!("**{dir}/**: {}\n", paths.join(", ")));
        } else {
            out.push_str(&format!("**{dir}/**: {} files\n", dir_modules.len()));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn builds_deterministic_manifest() {
        let manifest = default_manifest(".context-os/repo-memory");
        assert_eq!(manifest.len(), 8);
        assert!(manifest[0].json_path.ends_with("routes.json"));
        assert!(manifest[3].markdown_path.ends_with("components.md"));
    }

    #[test]
    fn indexes_sample_next_repo_and_writes_artifacts() {
        let root =
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../examples/sample-repos/mini-next");
        let artifacts = build_repo_memory(&root).unwrap();
        assert_eq!(artifacts.architecture.framework.as_deref(), Some("nextjs"));
        assert!(artifacts.routes.iter().any(|route| route.route == "/"));
        assert!(artifacts
            .routes
            .iter()
            .any(|route| route.route == "/users/[id]"));
        assert!(artifacts
            .components
            .iter()
            .any(|component| component.component_name == "NavBar"));
        assert!(artifacts
            .dependency_map
            .iter()
            .any(|dependency| dependency.name == "next"));

        let out_dir = tempdir().unwrap();
        let manifest = write_artifacts(&artifacts, out_dir.path()).unwrap();
        assert!(manifest[0].json_path.exists());
        assert!(manifest[5].markdown_path.exists());
    }
}
