//! Deep Fusion Memory (DFM) integration boundary, inspired by arXiv:2610.25100.
//!
//! This crate implements substrate-candidate validation and promotion decisions.
//! It does NOT implement a learned causal predictor, gated cross-attention,
//! parametric inference, model training, or weight serialization. Those require
//! a model-specific implementation and trained artifacts. In particular,
//! similarity lookup below is governance-time deduplication, not DFM fast-path
//! inference and not a substitute for the paper's architecture.

#[derive(Debug, Clone, PartialEq)]
pub struct MemoryChunk {
    pub chunk_id: String,
    pub embedding: Vec<f32>,
    pub context_chain: Vec<String>,
    pub eval_score: f64,
    pub generation: u64,
}

#[derive(Debug, Clone, PartialEq)]
pub enum DfmError {
    EmptyId,
    EmptyEmbedding,
    InvalidEmbedding,
    DimensionMismatch,
    InvalidEvalScore,
    InvalidThreshold,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Mem0Operation {
    Add,
    Update { supersedes: String },
    Noop,
}

#[derive(Debug, Clone, PartialEq)]
pub enum PromotionDecision {
    Promote { operation: Mem0Operation, reason: &'static str },
    Reject { reason: &'static str },
}

#[derive(Debug, Clone, PartialEq)]
pub struct PromotionPolicy {
    pub minimum_eval_score: f64,
    pub minimum_chain_depth: usize,
    pub duplicate_similarity: f64,
}

impl Default for PromotionPolicy {
    fn default() -> Self {
        Self { minimum_eval_score: 0.70, minimum_chain_depth: 2, duplicate_similarity: 0.85 }
    }
}

fn validate_chunk(chunk: &MemoryChunk) -> Result<(), DfmError> {
    if chunk.chunk_id.trim().is_empty() { return Err(DfmError::EmptyId); }
    if chunk.embedding.is_empty() { return Err(DfmError::EmptyEmbedding); }
    if chunk.embedding.iter().any(|x| !x.is_finite()) { return Err(DfmError::InvalidEmbedding); }
    if !chunk.eval_score.is_finite() || !(0.0..=1.0).contains(&chunk.eval_score) {
        return Err(DfmError::InvalidEvalScore);
    }
    Ok(())
}

fn cosine_similarity(a: &[f32], b: &[f32]) -> Result<f64, DfmError> {
    if a.len() != b.len() { return Err(DfmError::DimensionMismatch); }
    if a.is_empty() { return Err(DfmError::EmptyEmbedding); }
    if a.iter().chain(b).any(|x| !x.is_finite()) { return Err(DfmError::InvalidEmbedding); }
    let dot: f64 = a.iter().zip(b).map(|(x, y)| f64::from(*x) * f64::from(*y)).sum();
    let aa: f64 = a.iter().map(|x| f64::from(*x).powi(2)).sum();
    let bb: f64 = b.iter().map(|x| f64::from(*x).powi(2)).sum();
    if aa == 0.0 || bb == 0.0 { return Ok(0.0); }
    Ok(dot / (aa.sqrt() * bb.sqrt()))
}

/// Governance-time candidate registry. It does not contain learned DFM weights.
#[derive(Debug, Clone)]
pub struct DfmPromotionRegistry {
    policy: PromotionPolicy,
    promoted: Vec<MemoryChunk>,
}

impl Default for DfmPromotionRegistry {
    fn default() -> Self { Self::new(PromotionPolicy::default()).expect("default policy is valid") }
}

impl DfmPromotionRegistry {
    pub fn new(policy: PromotionPolicy) -> Result<Self, DfmError> {
        if !policy.minimum_eval_score.is_finite()
            || !(0.0..=1.0).contains(&policy.minimum_eval_score)
            || !policy.duplicate_similarity.is_finite()
            || !(-1.0..=1.0).contains(&policy.duplicate_similarity) {
            return Err(DfmError::InvalidThreshold);
        }
        Ok(Self { policy, promoted: Vec::new() })
    }

    pub fn promoted(&self) -> &[MemoryChunk] { &self.promoted }

    /// Produce a Mem0-style decision. Caller remains responsible for durable
    /// commit/rollback and for the authoritative substrate write.
    pub fn evaluate(&self, candidate: &MemoryChunk) -> Result<PromotionDecision, DfmError> {
        validate_chunk(candidate)?;
        if candidate.eval_score < self.policy.minimum_eval_score {
            return Ok(PromotionDecision::Reject { reason: "eval score below promotion threshold" });
        }
        if candidate.context_chain.len() < self.policy.minimum_chain_depth {
            return Ok(PromotionDecision::Reject { reason: "causal context chain too shallow" });
        }

        let mut closest: Option<(&MemoryChunk, f64)> = None;
        for existing in &self.promoted {
            let similarity = cosine_similarity(&existing.embedding, &candidate.embedding)?;
            if closest.as_ref().map_or(true, |(_, score)| similarity > *score) {
                closest = Some((existing, similarity));
            }
        }
        match closest {
            Some((existing, score)) if score >= self.policy.duplicate_similarity => {
                if candidate.eval_score > existing.eval_score {
                    Ok(PromotionDecision::Promote {
                        operation: Mem0Operation::Update { supersedes: existing.chunk_id.clone() },
                        reason: "stronger evaluated candidate supersedes similar promoted chunk",
                    })
                } else {
                    Ok(PromotionDecision::Promote {
                        operation: Mem0Operation::Noop,
                        reason: "similar chunk already promoted with equal or stronger score",
                    })
                }
            }
            _ => Ok(PromotionDecision::Promote {
                operation: Mem0Operation::Add,
                reason: "candidate passed quality and causal-chain gates",
            }),
        }
    }

    /// Apply a previously evaluated decision to this in-memory registry.
    /// This is not the authoritative atomic substrate; persistence integration
    /// must be performed by the Exoskeleton storage adapter.
    pub fn apply(&mut self, candidate: MemoryChunk, decision: &PromotionDecision) -> Result<(), DfmError> {
        validate_chunk(&candidate)?;
        match decision {
            PromotionDecision::Promote { operation: Mem0Operation::Add, .. } => {
                self.promoted.push(candidate);
            }
            PromotionDecision::Promote { operation: Mem0Operation::Update { supersedes }, .. } => {
                let index = self.promoted.iter().position(|item| &item.chunk_id == supersedes)
                    .ok_or(DfmError::EmptyId)?;
                self.promoted[index] = candidate;
            }
            PromotionDecision::Promote { operation: Mem0Operation::Noop, .. }
            | PromotionDecision::Reject { .. } => {}
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunk(id: &str, score: f64, embedding: Vec<f32>, depth: usize) -> MemoryChunk {
        MemoryChunk {
            chunk_id: id.into(), embedding,
            context_chain: (0..depth).map(|i| format!("tween-{i}")).collect(),
            eval_score: score, generation: 1,
        }
    }

    #[test]
    fn rejects_low_quality_candidate() {
        let registry = DfmPromotionRegistry::default();
        assert!(matches!(registry.evaluate(&chunk("low", 0.5, vec![1.0, 0.0], 4)).unwrap(),
            PromotionDecision::Reject { .. }));
    }

    #[test]
    fn rejects_shallow_context_chain() {
        let registry = DfmPromotionRegistry::default();
        assert!(matches!(registry.evaluate(&chunk("shallow", 0.9, vec![1.0, 0.0], 1)).unwrap(),
            PromotionDecision::Reject { .. }));
    }

    #[test]
    fn adds_new_candidate_and_updates_stronger_duplicate() {
        let mut registry = DfmPromotionRegistry::default();
        let first = chunk("first", 0.8, vec![1.0, 0.0], 3);
        let decision = registry.evaluate(&first).unwrap();
        registry.apply(first, &decision).unwrap();
        let stronger = chunk("stronger", 0.95, vec![1.0, 0.01], 3);
        let decision = registry.evaluate(&stronger).unwrap();
        assert!(matches!(decision, PromotionDecision::Promote {
            operation: Mem0Operation::Update { .. }, ..
        }));
        registry.apply(stronger, &decision).unwrap();
        assert_eq!(registry.promoted()[0].chunk_id, "stronger");
    }

    #[test]
    fn rejects_mismatched_embedding_dimensions() {
        let mut registry = DfmPromotionRegistry::default();
        let first = chunk("a", 0.8, vec![1.0, 0.0], 3);
        let decision = registry.evaluate(&first).unwrap();
        registry.apply(first, &decision).unwrap();
        assert_eq!(registry.evaluate(&chunk("b", 0.9, vec![1.0], 3)),
            Err(DfmError::DimensionMismatch));
    }
}
