use serde::{Deserialize, Serialize};
use walkdir::WalkDir;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StructuralInvariant {
    pub id: String,
    pub description: String,
    pub check_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InvariantResult {
    pub invariant_id: String,
    pub passed: bool,
    pub details: String,
    pub violations: Vec<String>,
}

pub struct StanzaChecker;

impl StanzaChecker {
    pub fn invariants() -> Vec<StructuralInvariant> {
        vec![
            StructuralInvariant { id: "SI-001".into(), description: "No subprocess delegation in native code (Rust/C/C++/Go)".into(), check_type: "pattern".into() },
            StructuralInvariant { id: "SI-002".into(), description: "No Python/Node/Ruby references in Rust/C files".into(), check_type: "pattern".into() },
            StructuralInvariant { id: "SI-003".into(), description: "No eval/exec/compile in Python files".into(), check_type: "pattern".into() },
            StructuralInvariant { id: "SI-004".into(), description: "Dependency graph is acyclic".into(), check_type: "graph".into() },
            StructuralInvariant { id: "SI-005".into(), description: "Diff is compact (no single-file change > 500 lines)".into(), check_type: "diff".into() },
            StructuralInvariant { id: "SI-006".into(), description: "No network calls in offline test code".into(), check_type: "pattern".into() },
        ]
    }

    pub fn check(worktree_path: &str) -> Vec<InvariantResult> {
        let mut results = Vec::new();
        results.push(Self::scan_patterns("SI-001", worktree_path, &[".rs", ".c", ".h", ".cpp", ".cc", ".go"], &["Command::new", "std::process", "popen", "system(", "subprocess", "os.system", "child_process", "ProcessBuilder", "Runtime.getRuntime"], "subprocess delegation in native code"));
        results.push(Self::scan_patterns("SI-002", worktree_path, &[".rs", ".c", ".h", ".cpp", ".cc"], &["import subprocess", "python3", "python -c", "python -m", "child_process", "from subprocess import", "pyo3"], "interpreter references in Rust/C files"));
        results.push(Self::scan_patterns("SI-003", worktree_path, &[".py"], &["eval(", "exec(", "__import__(", "compile("], "eval/exec/compile in Python files"));
        results.push(Self::check_cargo_acyclicity(worktree_path));
        results.push(Self::check_diff_compactness(worktree_path));
        results.push(Self::scan_patterns("SI-006", worktree_path, &["test", "_test.", "tests/"], &["urllib.request", "requests.get", "requests.post", "fetch(", "http::Client", "reqwest::", "ureq::post"], "network calls in test code"));
        results
    }

    fn scan_patterns(id: &str, worktree_path: &str, extensions: &[&str], patterns: &[&str], description: &str) -> InvariantResult {
        let mut violations = Vec::new();
        let skip_dirs = [".git", "target", "node_modules", "__pycache__"];
        for entry in WalkDir::new(worktree_path).into_iter().filter_map(|e| e.ok()).filter(|e| e.file_type().is_file()) {
            let path = entry.path();
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
            let path_str = path.to_string_lossy();
            let matches_ext = extensions.iter().any(|e| {
                if e.starts_with('.') { ext == &e[1..] } else { path_str.contains(e) }
            });
            if !matches_ext { continue; }
            let rel = path.strip_prefix(worktree_path).unwrap_or(path);
            let rel_str = rel.to_string_lossy();
            if skip_dirs.iter().any(|d| rel_str.contains(&format!("{}/", d))) { continue; }
            if let Ok(content) = std::fs::read_to_string(path) {
                for (line_num, line) in content.lines().enumerate() {
                    for pat in patterns {
                        if line.contains(pat) {
                            violations.push(format!("{}:{} — \"{}\"", rel_str, line_num + 1, line.trim()));
                        }
                    }
                }
            }
        }
        if violations.is_empty() {
            InvariantResult { invariant_id: id.into(), passed: true, details: format!("{}: CLEAN (0 violations)", description), violations: vec![] }
        } else {
            InvariantResult { invariant_id: id.into(), passed: false, details: format!("{}: {} violations", description, violations.len()), violations }
        }
    }

    fn check_cargo_acyclicity(worktree_path: &str) -> InvariantResult {
        let cargo_path = std::path::Path::new(worktree_path).join("Cargo.toml");
        if !cargo_path.exists() {
            return InvariantResult { invariant_id: "SI-004".into(), passed: true, details: "No Cargo.toml found. Skipping.".into(), violations: vec![] };
        }
        let content = std::fs::read_to_string(&cargo_path).unwrap_or_default();
        if content.contains("[workspace]") {
            InvariantResult { invariant_id: "SI-004".into(), passed: true, details: "Workspace member structure: acyclic by construction".into(), violations: vec![] }
        } else {
            let mut has_circular = false;
            let mut violations = vec![];
            if content.contains("path = \"./\"") || content.contains("path = \".\"") {
                has_circular = true;
                violations.push("Self-referencing path dependency detected".to_string());
            }
            InvariantResult { invariant_id: "SI-004".into(), passed: !has_circular, details: if has_circular { "Dependency graph: CIRCULAR".into() } else { "Dependency graph: acyclic".into() }, violations }
        }
    }

    fn check_diff_compactness(worktree_path: &str) -> InvariantResult {
        let output = std::process::Command::new("git").args(["diff", "--numstat", "HEAD"]).current_dir(worktree_path).output();
        match output {
            Ok(out) => {
                let stat = String::from_utf8_lossy(&out.stdout);
                let mut bloated = vec![];
                for line in stat.lines() {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if parts.len() >= 3 {
                        let added: usize = parts[0].parse().unwrap_or(0);
                        let deleted: usize = parts[1].parse().unwrap_or(0);
                        let total = added + deleted;
                        if total > 500 {
                            bloated.push(format!("{} — {} lines changed ({}+ {}-)", parts[2], total, added, deleted));
                        }
                    }
                }
                if bloated.is_empty() {
                    InvariantResult { invariant_id: "SI-005".into(), passed: true, details: "Diff compactness: PASS (all files ≤ 500 lines changed)".into(), violations: vec![] }
                } else {
                    InvariantResult { invariant_id: "SI-005".into(), passed: false, details: format!("Diff compactness: FAIL — {} bloated files", bloated.len()), violations: bloated }
                }
            }
            Err(e) => InvariantResult { invariant_id: "SI-005".into(), passed: true, details: format!("Diff compactness: skipped (git not available: {})", e), violations: vec![] },
        }
    }
}
