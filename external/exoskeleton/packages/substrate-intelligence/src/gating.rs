use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use walkdir::WalkDir;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Severity { Critical, High, Medium, Low }

impl std::fmt::Display for Severity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Severity::Critical => write!(f, "CRITICAL"),
            Severity::High => write!(f, "HIGH"),
            Severity::Medium => write!(f, "MEDIUM"),
            Severity::Low => write!(f, "LOW"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VetoRule {
    pub id: String,
    pub description: String,
    pub patterns: Vec<String>,
    pub severity: Severity,
    pub hard_veto: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VetoViolation {
    pub rule_id: String,
    pub description: String,
    pub severity: Severity,
    pub hard_veto: bool,
    pub file: String,
    pub line: usize,
    pub matched: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Verdict { Pass, HardVeto, SoftDisagreement }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GateResult {
    pub verdict: Verdict,
    pub violations: Vec<VetoViolation>,
    pub hard_veto_count: usize,
    pub soft_flag_count: usize,
    pub checked_files: usize,
    pub checked_lines: usize,
    pub content_hash: String,
}

pub struct GatingEngine { rules: Vec<VetoRule> }

impl Default for GatingEngine { fn default() -> Self { Self::new() } }

impl GatingEngine {
    pub fn new() -> Self {
        let rules = vec![
            VetoRule { id: "VETO-001".into(), description: "Reject subprocess delegation".into(),
                patterns: vec![r"std::process::Command".into(), r"Command::new\s*\(".into(), r"subprocess".into(), r"pyo3".into()],
                severity: Severity::Critical, hard_veto: true },
            VetoRule { id: "VETO-002".into(), description: "Reject INFERRED->OBSERVED promotion".into(),
                patterns: vec![r"(?i)OBSERVED\s*:\s*PASS".into(), r"(?i)promote.*observed".into()],
                severity: Severity::Critical, hard_veto: true },
            VetoRule { id: "VETO-003".into(), description: "Reject forbidden commands".into(),
                patterns: vec![r"git\s+push\s+--force".into(), r"rm\s+-rf".into()],
                severity: Severity::Critical, hard_veto: true },
            VetoRule { id: "VETO-004".into(), description: "Reject self-confirmation".into(),
                patterns: vec![r"(?i)as\s+(?:I|we)\s+(?:said|confirmed)".into(), r"(?i)my\s+analysis\s+confirms".into()],
                severity: Severity::Critical, hard_veto: true },
            VetoRule { id: "VETO-005".into(), description: "Reject structural shortcuts".into(),
                patterns: vec![r"python3?\s+-c".into(), r"import\s+subprocess".into()],
                severity: Severity::Critical, hard_veto: true },
            VetoRule { id: "VETO-006".into(), description: "Reject authority bypass".into(),
                patterns: vec![r"(?i)skip\s+(?:the\s+)?(?:gate|check)".into(), r"(?i)bypass\s+(?:the\s+)?(?:gate|check)".into()],
                severity: Severity::Critical, hard_veto: true },
            VetoRule { id: "SOFT-001".into(), description: "Flag superlative claims".into(),
                patterns: vec![r"(?i)\bbest\b".into(), r"(?i)\bunprecedented\b".into()],
                severity: Severity::Medium, hard_veto: false },
        ];
        Self { rules }
    }

    pub fn verify_text(&self, text: &str, file_label: &str) -> GateResult {
        let mut violations = Vec::new();
        let mut line_count = 0;
        for (line_num, line) in text.lines().enumerate() {
            line_count += 1;
            for rule in &self.rules {
                for pattern in &rule.patterns {
                    if let Ok(re) = Regex::new(pattern) {
                        if re.is_match(line) {
                            violations.push(VetoViolation {
                                rule_id: rule.id.clone(),
                                description: rule.description.clone(),
                                severity: rule.severity,
                                hard_veto: rule.hard_veto,
                                file: file_label.to_string(),
                                line: line_num + 1,
                                matched: line.trim().to_string(),
                            });
                        }
                    }
                }
            }
        }
        let hard_count = violations.iter().filter(|v| v.hard_veto).count();
        let soft_count = violations.iter().filter(|v| !v.hard_veto).count();
        let verdict = if hard_count > 0 { Verdict::HardVeto }
            else if soft_count > 0 { Verdict::SoftDisagreement }
            else { Verdict::Pass };
        let content_hash = blake2_hex(&format!("{}:{}", violations.len(), line_count));
        GateResult { verdict, violations, hard_veto_count: hard_count, soft_flag_count: soft_count, checked_files: 1, checked_lines: line_count, content_hash }
    }

    pub fn verify_diff(&self, worktree_path: &str) -> GateResult {
        let mut violations = Vec::new();
        let mut checked_files = 0usize;
        let mut checked_lines = 0usize;
        let code_exts: HashSet<&str> = [".rs",".py",".c",".h",".cpp",".go",".ts",".js",".sh",".toml",".yaml",".yml",".json"].iter().cloned().collect();
        let skip_dirs = [".git","target","node_modules","__pycache__","dist","build",".venv"];
        for entry in WalkDir::new(worktree_path).into_iter().filter_map(|e| e.ok()).filter(|e| e.file_type().is_file()) {
            let path = entry.path();
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
            if !code_exts.contains(ext) { continue; }
            let rel = path.strip_prefix(worktree_path).unwrap_or(path).to_string_lossy().to_string();
            if skip_dirs.iter().any(|d| rel.contains(&format!("{}/", d))) { continue; }
            let content = match std::fs::read_to_string(path) { Ok(c) => c, Err(_) => continue };
            checked_files += 1;
            for (line_num, line) in content.lines().enumerate() {
                checked_lines += 1;
                for rule in &self.rules {
                    for pattern in &rule.patterns {
                        if let Ok(re) = Regex::new(pattern) {
                            if re.is_match(line) {
                                violations.push(VetoViolation {
                                    rule_id: rule.id.clone(),
                                    description: rule.description.clone(),
                                    severity: rule.severity,
                                    hard_veto: rule.hard_veto,
                                    file: rel.clone(),
                                    line: line_num + 1,
                                    matched: line.trim().to_string(),
                                });
                            }
                        }
                    }
                }
            }
        }
        let hard_count = violations.iter().filter(|v| v.hard_veto).count();
        let soft_count = violations.iter().filter(|v| !v.hard_veto).count();
        let verdict = if hard_count > 0 { Verdict::HardVeto }
            else if soft_count > 0 { Verdict::SoftDisagreement }
            else { Verdict::Pass };
        let content_hash = blake2_hex(&format!("{}:{}:{}", violations.len(), checked_files, checked_lines));
        GateResult { verdict, violations, hard_veto_count: hard_count, soft_flag_count: soft_count, checked_files, checked_lines, content_hash }
    }
}

fn blake2_hex(data: &str) -> String {
    use blake2::{Blake2b512, Digest};
    let mut h = Blake2b512::new();
    h.update(data.as_bytes());
    let out = h.finalize();
    let hex: String = out.iter().map(|b| format!("{:02x}", b)).collect();
    hex[..32].to_string()
}
