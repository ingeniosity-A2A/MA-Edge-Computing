use regex::Regex;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Seat {
    Lookup,
    Build,
    Hard,
    Big,
    Other,
}

impl std::fmt::Display for Seat {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Seat::Lookup => write!(f, "lookup"),
            Seat::Build => write!(f, "build"),
            Seat::Hard => write!(f, "hard"),
            Seat::Big => write!(f, "big"),
            Seat::Other => write!(f, "other"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RouteDecision {
    pub seat: Seat,
    pub confidence: f64,
    pub risk_score: u32,
    pub work_items: usize,
    pub file_refs: usize,
    pub failed_attempts: usize,
    pub disguise_signals: usize,
    pub scope_signals: usize,
    pub reasoning: String,
}

pub struct RouteEngine;

impl RouteEngine {
    pub fn route(task: &str) -> RouteDecision {
        let disguise_patterns = [
            r"(?i)quick\s+(?:lookup|question|check|fix|one)",
            r"(?i)nothing\s+(?:major|fancy|complicated|big|serious)",
            r"(?i)just\s+(?:a\s+)?(?:quick|small|simple|tiny|minor)",
            r"(?i)real(?:ly)?\s+quick",
            r"(?i)small\s+(?:stuff|change|fix|thing|tweak|edit)",
            r"(?i)(?:10|5|30)\s*-?\s*(?:second|minute)s?\s+(?:question|lookup|fix|task)",
            r"(?i)(?:hey|hi|hello)[\s,]+(?:quick|small|tiny)",
            r"(?i)nothing\s+to\s+(?:worry|stress|concern)",
            r"(?i)super\s+(?:simple|easy|quick|fast|trivial)",
        ];
        let scope_patterns = [
            r"(?i)refactor",
            r"(?i)migrate",
            r"(?i)backward\s+compatib",
            r"(?i)hot[- _]?reload",
            r"(?i)new\s+dependenc",
            r"(?i)proc\s+macro",
            r"(?i)\d+\s+new\s+(?:fields|methods|types|structs)",
            r"(?i)redesign",
            r"(?i)rewrit",
            r"(?i)architectur",
            r"(?i)wire\s+format",
            r"(?i)atomic\s+memory",
            r"(?i)failed\s+attempts?",
            r"(?i)(?:3|three|4|four|5|five|multiple)\s+(?:failed|previous|prior|past|last)\s+(?:attempts?|tries|versions?|iterations?)",
        ];
        let disguise_hits: usize = disguise_patterns.iter().filter_map(|p| Regex::new(p).ok()).map(|re| re.find_iter(task).count()).sum();
        let scope_hits: usize = scope_patterns.iter().filter_map(|p| Regex::new(p).ok()).map(|re| re.find_iter(task).count()).sum();
        let work_item_re = Regex::new(r"(?m)^\s*\d+\.\s+\S").unwrap();
        let work_items = work_item_re.find_iter(task).count();
        let file_re = Regex::new(r"`([^`]+\.(?:rs|py|ts|js|go|c|h|cpp|sql|sh|toml|yaml|json))`").unwrap();
        let file_refs_backtick = file_re.find_iter(task).count();
        let bare_file_re = Regex::new(r"\b([\w-]+\.(?:rs|py|ts|js|go|c|h|cpp|sql|sh))\b").unwrap();
        let bare_file_refs = bare_file_re.find_iter(task).count();
        let file_refs = file_refs_backtick.max(bare_file_refs);
        let failed_re = Regex::new(r"(?i)(\d+|three|two|multiple|several|last\s+\d+)\s+failed\s+attempts?").unwrap();
        let failed_attempts = failed_re.find_iter(task).map(|m| {
            let s = m.as_str().to_lowercase();
            if s.contains("three") { 3 }
            else if s.contains("two") { 2 }
            else if s.contains("multiple") || s.contains("several") { 3 }
            else { s.chars().take_while(|c| c.is_ascii_digit()).collect::<String>().parse().unwrap_or(1) }
        }).max().unwrap_or(0);
        let risk_score = (work_items as u32) * 2 + (file_refs as u32) * 3 + (scope_hits as u32) * 4 + (failed_attempts as u32) * 5 + (disguise_hits as u32) * 3;
        let (seat, confidence, reasoning) = if file_refs >= 4 || failed_attempts >= 2 || risk_score >= 25 {
            (Seat::Hard, 0.95, format!("High scope: {} files, {} failed attempts, risk={}. Escalate to hard/Ava-007.", file_refs, failed_attempts, risk_score))
        } else if work_items >= 5 || risk_score >= 30 {
            (Seat::Big, 0.90, format!("Multi-part job: {} work items, risk={}. Split into parallel briefs.", work_items, risk_score))
        } else if work_items >= 1 && file_refs <= 3 && risk_score < 15 {
            (Seat::Build, 0.85, format!("Bounded edit: {} work items, <=3 files, risk={}. Route to build.", work_items, risk_score))
        } else if disguise_hits > 0 && scope_hits > 0 {
            (Seat::Hard, 0.80, format!("Disguise detected ({} disguise signals vs {} scope signals). Route up despite low scores.", disguise_hits, scope_hits))
        } else if risk_score < 5 && work_items == 0 && file_refs == 0 {
            (Seat::Lookup, 0.90, format!("Low-risk read-only query. Risk={}. Route to lookup.", risk_score))
        } else {
            (Seat::Other, 0.50, format!("Ambiguous scope: risk={}, {} work items, {} files. Route to other for clarification.", risk_score, work_items, file_refs))
        };
        RouteDecision { seat, confidence, risk_score, work_items, file_refs, failed_attempts, disguise_signals: disguise_hits, scope_signals: scope_hits, reasoning }
    }
}
