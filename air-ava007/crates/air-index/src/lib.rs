//! Vector-index contract boundary. Concrete TurboVec/TurboQuant adapters are
//! added only after their APIs and versions are verified against upstream.

#[derive(Debug, Clone, PartialEq)]
pub struct Candidate {
    pub id: u64,
    pub score: f32,
}

pub trait VectorIndex {
    type Error: std::error::Error + Send + Sync + 'static;

    fn search(&self, query: &[f32], top_k: usize) -> Result<Vec<Candidate>, Self::Error>;
}
