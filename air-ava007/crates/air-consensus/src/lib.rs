//! Distributed coordination primitives inspired by arXiv:2401.18030.
//!
//! IMPORTANT: these are deterministic software primitives, not a reproduction
//! of the paper's complete algorithm or proof. Weighted neighbor mixing alone
//! does not establish quasi-Fejer convergence on arbitrary time-varying,
//! directed, unbalanced graphs. OTA-C requires a physical multiple-access
//! channel; packet aggregation here is digital aggregation.

use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub struct Estimate {
    pub node_id: String,
    pub values: Vec<f64>,
    pub confidence: f64,
    pub generation: u64,
}

#[derive(Debug, Clone, PartialEq)]
pub enum CoordinationError {
    EmptyNodeId, EmptyVector, DimensionMismatch, InvalidConfidence,
    InvalidValue, EmptyContributions, InvalidSafetyMargin,
}
impl fmt::Display for CoordinationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { write!(f, "{self:?}") }
}
impl std::error::Error for CoordinationError {}

fn validate_vector(values: &[f64]) -> Result<(), CoordinationError> {
    if values.is_empty() { return Err(CoordinationError::EmptyVector); }
    if values.iter().any(|v| !v.is_finite()) { return Err(CoordinationError::InvalidValue); }
    Ok(())
}

#[derive(Debug, Clone, PartialEq)]
pub struct FeasiblePolicy<T> {
    pub action: T, pub objective: f64, pub safety_margin: f64, pub generation: u64,
}

/// Bounded superiorization-inspired selection; not the paper's full algorithm.
pub fn superiorize<T: Clone>(
    baseline: &FeasiblePolicy<T>, candidates: &[FeasiblePolicy<T>], minimum_margin_ratio: f64,
) -> Result<FeasiblePolicy<T>, CoordinationError> {
    if !baseline.objective.is_finite() || !baseline.safety_margin.is_finite()
        || !minimum_margin_ratio.is_finite() || minimum_margin_ratio < 0.0
        || baseline.safety_margin <= 0.0 {
        return Err(CoordinationError::InvalidSafetyMargin);
    }
    let floor = baseline.safety_margin * minimum_margin_ratio;
    let mut best = baseline.clone();
    for candidate in candidates {
        if candidate.objective.is_finite() && candidate.safety_margin.is_finite()
            && candidate.safety_margin >= floor && candidate.objective > best.objective {
            best = candidate.clone();
        }
    }
    Ok(best)
}

/// One local weighted-mixing update. No convergence guarantee is implied.
pub fn mix_estimates(local: &Estimate, neighbors: &[Estimate]) -> Result<Estimate, CoordinationError> {
    if local.node_id.is_empty() { return Err(CoordinationError::EmptyNodeId); }
    validate_vector(&local.values)?;
    if !local.confidence.is_finite() || local.confidence <= 0.0 {
        return Err(CoordinationError::InvalidConfidence);
    }
    let mut total = local.confidence;
    let mut accum: Vec<f64> = local.values.iter().map(|v| v * local.confidence).collect();
    let mut generation = local.generation;
    for peer in neighbors {
        if peer.node_id.is_empty() { return Err(CoordinationError::EmptyNodeId); }
        validate_vector(&peer.values)?;
        if peer.values.len() != local.values.len() { return Err(CoordinationError::DimensionMismatch); }
        if !peer.confidence.is_finite() || peer.confidence <= 0.0 {
            return Err(CoordinationError::InvalidConfidence);
        }
        total += peer.confidence;
        if !total.is_finite() { return Err(CoordinationError::InvalidConfidence); }
        for (sum, value) in accum.iter_mut().zip(&peer.values) { *sum += value * peer.confidence; }
        generation = generation.max(peer.generation);
    }
    for value in &mut accum { *value /= total; }
    Ok(Estimate { node_id: local.node_id.clone(), values: accum, confidence: local.confidence, generation })
}

#[derive(Debug, Clone, PartialEq)]
pub struct DigitalAggregate {
    pub weighted_mean: Vec<f64>, pub minimum: Vec<f64>, pub maximum: Vec<f64>,
    pub node_count: usize, pub generation: u64,
}

/// Packet-level Rustunnel aggregation. This is NOT physical-layer OTA-C.
pub fn aggregate_digital(contributions: &[Estimate]) -> Result<DigitalAggregate, CoordinationError> {
    let first = contributions.first().ok_or(CoordinationError::EmptyContributions)?;
    validate_vector(&first.values)?;
    let dim = first.values.len();
    let mut weighted = vec![0.0; dim];
    let mut minimum = vec![f64::INFINITY; dim];
    let mut maximum = vec![f64::NEG_INFINITY; dim];
    let mut total_weight = 0.0;
    let mut generation = 0;
    for item in contributions {
        validate_vector(&item.values)?;
        if item.values.len() != dim { return Err(CoordinationError::DimensionMismatch); }
        if !item.confidence.is_finite() || item.confidence <= 0.0 {
            return Err(CoordinationError::InvalidConfidence);
        }
        total_weight += item.confidence;
        if !total_weight.is_finite() { return Err(CoordinationError::InvalidConfidence); }
        generation = generation.max(item.generation);
        for i in 0..dim {
            weighted[i] += item.values[i] * item.confidence;
            minimum[i] = minimum[i].min(item.values[i]);
            maximum[i] = maximum[i].max(item.values[i]);
        }
    }
    for value in &mut weighted { *value /= total_weight; }
    Ok(DigitalAggregate { weighted_mean: weighted, minimum, maximum, node_count: contributions.len(), generation })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn superiorization_keeps_only_improved_safe_candidates() {
        let baseline = FeasiblePolicy { action: "hold", objective: 2.0, safety_margin: 1.0, generation: 1 };
        let candidates = [
            FeasiblePolicy { action: "better", objective: 3.0, safety_margin: 0.9, generation: 2 },
            FeasiblePolicy { action: "unsafe", objective: 4.0, safety_margin: 0.2, generation: 3 },
        ];
        assert_eq!(superiorize(&baseline, &candidates, 0.8).unwrap().action, "better");
    }

    #[test]
    fn weighted_mixing_handles_unequal_confidence() {
        let local = Estimate { node_id: "a".into(), values: vec![1.0], confidence: 1.0, generation: 1 };
        let peer = Estimate { node_id: "b".into(), values: vec![5.0], confidence: 3.0, generation: 2 };
        let result = mix_estimates(&local, &[peer]).unwrap();
        assert_eq!(result.values, vec![4.0]);
        assert_eq!(result.generation, 2);
    }

    #[test]
    fn digital_aggregation_reports_mean_min_max() {
        let items = [
            Estimate { node_id: "a".into(), values: vec![1.0, 4.0], confidence: 1.0, generation: 2 },
            Estimate { node_id: "b".into(), values: vec![3.0, 2.0], confidence: 3.0, generation: 3 },
        ];
        let result = aggregate_digital(&items).unwrap();
        assert_eq!(result.weighted_mean, vec![2.5, 2.5]);
        assert_eq!(result.minimum, vec![1.0, 2.0]);
        assert_eq!(result.maximum, vec![3.0, 4.0]);
        assert_eq!(result.node_count, 2);
    }

    #[test]
    fn rejects_mismatched_dimensions() {
        let local = Estimate { node_id: "a".into(), values: vec![1.0], confidence: 1.0, generation: 0 };
        let peer = Estimate { node_id: "b".into(), values: vec![1.0, 2.0], confidence: 1.0, generation: 0 };
        assert_eq!(mix_estimates(&local, &[peer]), Err(CoordinationError::DimensionMismatch));
    }
}
