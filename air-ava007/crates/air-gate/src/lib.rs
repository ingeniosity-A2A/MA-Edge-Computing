//! Rev.ike candidate-verification and promotion policy boundary.
//! Production BM25/RRF/SPR implementations require real corpus fixtures and
//! recorded recall tests; no candidate is promoted solely by a confidence label.

use air_core::verdict::Verdict;
use air_index::Candidate;

#[derive(Debug, Clone, PartialEq)]
pub struct PromotionDecision {
    pub accepted: bool,
    pub reason: &'static str,
}

pub fn decide(verdict: &Verdict, candidate: &Candidate) -> PromotionDecision {
    if verdict.is_failure() {
        return PromotionDecision { accepted: false, reason: "verification_gate_failed" };
    }
    if !candidate.score.is_finite() {
        return PromotionDecision { accepted: false, reason: "candidate_score_invalid" };
    }
    PromotionDecision { accepted: true, reason: "verification_gate_passed" }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_candidate_when_verdict_fails() {
        let verdict = Verdict { strict_success: false, partial_credit: 0.5, failed_share: 0.1, quantization_distortion: 0.2 };
        let candidate = Candidate { id: 1, score: 0.9 };
        assert!(!decide(&verdict, &candidate).accepted);
    }
}
