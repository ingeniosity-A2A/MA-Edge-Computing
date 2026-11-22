use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelOutput {
    pub model: String,
    pub confidence: f64,
    pub answer: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DisagreementResult {
    pub d_ab: f64,
    pub c_final: f64,
    pub disagreement: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfidenceAggregate {
    pub min_confidence: f64,
    pub models: Vec<String>,
}

pub struct DisagreementCalculator;

impl DisagreementCalculator {
    /// Pairwise disagreement D(A,B): 0.0 if answers match, 1.0 otherwise (scaled by confidence gap).
    pub fn pairwise(a: &ModelOutput, b: &ModelOutput) -> f64 {
        if a.answer == b.answer {
            0.0
        } else {
            (a.confidence - b.confidence).abs().max(0.5)
        }
    }

    /// C_final: weakest-link aggregation (min confidence across models).
    pub fn c_final(outputs: &[ModelOutput]) -> f64 {
        outputs.iter().map(|o| o.confidence).fold(1.0_f64, f64::min)
    }

    pub fn aggregate(outputs: &[ModelOutput]) -> DisagreementResult {
        let d_ab = if outputs.len() >= 2 {
            Self::pairwise(&outputs[0], &outputs[1])
        } else {
            0.0
        };
        let c_final = Self::c_final(outputs);
        DisagreementResult {
            d_ab,
            c_final,
            disagreement: d_ab > 0.0,
        }
    }

    pub fn confidence_aggregate(outputs: &[ModelOutput]) -> ConfidenceAggregate {
        ConfidenceAggregate {
            min_confidence: Self::c_final(outputs),
            models: outputs.iter().map(|o| o.model.clone()).collect(),
        }
    }
}
