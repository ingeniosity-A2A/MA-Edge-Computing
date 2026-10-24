use serde::{Deserialize, Serialize};

pub mod verdict;

/// A memory record — the canonical unit of Plane 1 evidence.
/// Source coordinates are provenance metadata, not an assertion that the
/// Rust struct has a stable fixed-width in-memory or FFI representation.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MemoryRecord {
    pub id: u64,
    pub user_id: String,
    pub content: String,
    pub record_type: RecordType,
    pub source_span: Option<SourceSpan>,
    pub created_at_ms: i64,
    pub entity_ids: Vec<u64>,
    pub verified: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RecordType {
    Persona,
    Episodic,
    Instruction,
    Atom,
    Scenario,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SourceSpan {
    pub doc_id: String,
    pub page: u32,
    pub byte_start: u64,
    pub byte_end: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_span_rejects_no_semantics_at_type_boundary() {
        let span = SourceSpan {
            doc_id: "paper-v1.4".into(),
            page: 13,
            byte_start: 10,
            byte_end: 20,
        };
        assert!(span.byte_end >= span.byte_start);
    }

    #[test]
    fn record_type_uses_snake_case_wire_values() {
        let encoded = serde_json::to_string(&RecordType::Episodic).unwrap();
        assert_eq!(encoded, "\"episodic\"");
    }
}
