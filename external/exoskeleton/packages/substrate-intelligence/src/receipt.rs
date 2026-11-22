use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum EpistemicState {
    Hypothesized,
    Inferred,
    Observed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Evidence {
    pub measured: bool,
    pub samples: u64,
    pub provenance: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpistemicReceipt {
    pub id: String,
    pub state: EpistemicState,
    pub evidence: Option<Evidence>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PromotionError {
    HypothesizedToObservedForbidden,
    MissingEvidence,
    InsufficientSamples { samples: u64, required: u64 },
}

impl std::fmt::Display for PromotionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PromotionError::HypothesizedToObservedForbidden => write!(f, "HYPOTHESIZED->OBSERVED forbidden"),
            PromotionError::MissingEvidence => write!(f, "missing evidence"),
            PromotionError::InsufficientSamples { samples, required } => write!(f, "insufficient samples: {} < {}", samples, required),
        }
    }
}

impl std::error::Error for PromotionError {}

pub struct ReceiptValidator;

impl ReceiptValidator {
    pub const MIN_SAMPLES: u64 = 1000;

    pub fn can_promote(from: EpistemicState, to: EpistemicState, evidence: Option<&Evidence>) -> Result<(), PromotionError> {
        if from == to { return Ok(()); }
        if from == EpistemicState::Hypothesized && to == EpistemicState::Observed {
            return Err(PromotionError::HypothesizedToObservedForbidden);
        }
        if from == EpistemicState::Inferred && to == EpistemicState::Observed {
            match evidence {
                None => return Err(PromotionError::MissingEvidence),
                Some(e) if !e.measured => return Err(PromotionError::MissingEvidence),
                Some(e) if e.samples < Self::MIN_SAMPLES => return Err(PromotionError::InsufficientSamples { samples: e.samples, required: Self::MIN_SAMPLES }),
                _ => {}
            }
        }
        Ok(())
    }

    pub fn validate(receipt: &EpistemicReceipt) -> bool {
        // A receipt is valid if its state/evidence are internally consistent.
        match receipt.state {
            EpistemicState::Observed => receipt.evidence.as_ref().map(|e| e.measured && e.samples >= Self::MIN_SAMPLES).unwrap_or(false),
            _ => true,
        }
    }
}
