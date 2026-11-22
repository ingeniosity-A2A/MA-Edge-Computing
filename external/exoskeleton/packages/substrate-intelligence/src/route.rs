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
    pub escalate: bool,
}

pub struct RouteEngine;

impl RouteEngine {
    /// JevOut routing: classify a task string into a seat.
    pub fn route(task: &str) -> RouteDecision {
        let lower = task.to_lowercase();
        let (seat, conf) = if lower.contains("find") || lower.contains("list") || lower.contains("summarize") || lower.contains("explain") {
            (Seat::Lookup, 0.95)
        } else if lower.contains("edit") || lower.contains("fix") || lower.contains("add") {
            (Seat::Build, 0.90)
        } else if lower.contains("unknown") || lower.contains("bug") || lower.contains("design") {
            (Seat::Hard, 0.70)
        } else if lower.contains("multi") || lower.contains("parallel") || lower.contains("split") {
            (Seat::Big, 0.80)
        } else {
            (Seat::Other, 0.50)
        };
        let escalate = conf < 0.90 || matches!(seat, Seat::Hard | Seat::Big | Seat::Other);
        RouteDecision { seat, confidence: conf, escalate }
    }
}
