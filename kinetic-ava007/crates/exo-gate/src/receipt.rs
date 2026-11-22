//! Epistemic promotion legality rules.
//!
//! A `Receipt` records the observed state of a claim together with the evidence
//! that supports it. Promotion between epistemic states is governed by
//! legality rules that prevent unwarranted upgrades:
//!
//!   * `HYPOTHESIZED -> OBSERVED` is always forbidden.
//!   * `INFERRED -> OBSERVED` requires measured evidence with at least 1000 samples.
//!   * All other transitions are permitted.

use serde::{Deserialize, Serialize};

/// Epistemic state of a claim.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum EpistemicState {
    Hypothesized,
    Inferred,
    Observed,
}

/// Evidence attached to a receipt.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Evidence {
    /// Whether the evidence was actually measured (not inferred/assumed).
    pub measured: bool,
    /// Number of samples backing the measurement.
    pub samples: u64,
    /// Optional free-form provenance note.
    pub provenance: Option<String>,
}

/// A receipt tying a claim to its epistemic state and evidence.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Receipt {
    pub id: String,
    pub state: EpistemicState,
    pub evidence: Option<Evidence>,
}

/// Errors that can occur when attempting a promotion.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PromotionError {
    /// HYPOTHESIZED -> OBSERVED is never allowed.
    HypothesizedToObservedForbidden,
    /// INFERRED -> OBSERVED requires measured evidence with >= 1000 samples.
    InsufficientMeasuredEvidence { samples: u64, required: u64 },
    /// No measured evidence was provided.
    MissingEvidence,
}

impl std::fmt::Display for PromotionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PromotionError::HypothesizedToObservedForbidden => {
                write!(f, "promotion HYPOTHESIZED -> OBSERVED is forbidden")
            }
            PromotionError::InsufficientMeasuredEvidence { samples, required } => {
                write!(f, "insufficient measured evidence: {samples} < {required} samples")
            }
            PromotionError::MissingEvidence => write!(f, "measured evidence required"),
        }
    }
}

impl std::error::Error for PromotionError {}

/// Minimum number of samples required to promote INFERRED -> OBSERVED.
pub const MIN_SAMPLES_FOR_OBSERVED: u64 = 1000;

/// Decide whether a promotion from `from` to `to` is legal given `evidence`.
pub fn can_promote(
    from: EpistemicState,
    to: EpistemicState,
    evidence: Option<&Evidence>,
) -> Result<(), PromotionError> {
    // Same state: no promotion needed, allowed.
    if from == to {
        return Ok(());
    }
    // HYPOTHESIZED -> OBSERVED is always forbidden.
    if from == EpistemicState::Hypothesized && to == EpistemicState::Observed {
        return Err(PromotionError::HypothesizedToObservedForbidden);
    }
    // INFERRED -> OBSERVED requires measured evidence with >= 1000 samples.
    if from == EpistemicState::Inferred && to == EpistemicState::Observed {
        match evidence {
            None => return Err(PromotionError::MissingEvidence),
            Some(e) if !e.measured => return Err(PromotionError::MissingEvidence),
            Some(e) if e.samples < MIN_SAMPLES_FOR_OBSERVED => {
                return Err(PromotionError::InsufficientMeasuredEvidence {
                    samples: e.samples,
                    required: MIN_SAMPLES_FOR_OBSERVED,
                })
            }
            _ => {}
        }
    }
    Ok(())
}

/// Apply a promotion to a receipt, returning the new receipt or an error.
pub fn promote(receipt: &Receipt, to: EpistemicState, evidence: Option<Evidence>) -> Result<Receipt, PromotionError> {
    can_promote(receipt.state, to, evidence.as_ref().or(receipt.evidence.as_ref()))?;
    let new_evidence = evidence.or_else(|| receipt.evidence.clone());
    Ok(Receipt {
        id: receipt.id.clone(),
        state: to,
        evidence: new_evidence,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn measured(samples: u64) -> Evidence {
        Evidence { measured: true, samples, provenance: None }
    }

    #[test]
    fn hypothesized_to_observed_forbidden() {
        let r = can_promote(
            EpistemicState::Hypothesized,
            EpistemicState::Observed,
            Some(&measured(5000)),
        );
        assert_eq!(r, Err(PromotionError::HypothesizedToObservedForbidden));
    }

    #[test]
    fn inferred_to_observed_requires_measured_evidence() {
        assert_eq!(
            can_promote(EpistemicState::Inferred, EpistemicState::Observed, None),
            Err(PromotionError::MissingEvidence)
        );
        let unmeasured = Evidence { measured: false, samples: 5000, provenance: None };
        assert_eq!(
            can_promote(EpistemicState::Inferred, EpistemicState::Observed, Some(&unmeasured)),
            Err(PromotionError::MissingEvidence)
        );
    }

    #[test]
    fn inferred_to_observed_requires_1000_samples() {
        assert_eq!(
            can_promote(EpistemicState::Inferred, EpistemicState::Observed, Some(&measured(999))),
            Err(PromotionError::InsufficientMeasuredEvidence { samples: 999, required: 1000 })
        );
        assert!(can_promote(EpistemicState::Inferred, EpistemicState::Observed, Some(&measured(1000))).is_ok());
    }

    #[test]
    fn same_state_allowed() {
        assert!(can_promote(EpistemicState::Observed, EpistemicState::Observed, None).is_ok());
    }

    #[test]
    fn hypothesized_to_inferred_allowed() {
        assert!(can_promote(EpistemicState::Hypothesized, EpistemicState::Inferred, None).is_ok());
    }

    #[test]
    fn promote_updates_state() {
        let r = Receipt { id: "c1".into(), state: EpistemicState::Inferred, evidence: None };
        let promoted = promote(&r, EpistemicState::Observed, Some(measured(1500))).unwrap();
        assert_eq!(promoted.state, EpistemicState::Observed);
        assert_eq!(promoted.evidence.unwrap().samples, 1500);
    }

    #[test]
    fn promote_forbidden_does_not_change() {
        let r = Receipt { id: "c2".into(), state: EpistemicState::Hypothesized, evidence: None };
        let res = promote(&r, EpistemicState::Observed, Some(measured(5000)));
        assert!(res.is_err());
    }
}
