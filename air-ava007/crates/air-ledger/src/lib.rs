//! Append-only ledger boundary. The DuckDB 2.0.0 adapter and live-runtime
//! bindings are deliberately not fabricated; add them after validating the
//! selected DuckDB crate/API and runtime ABI.

use air_core::MemoryRecord;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LedgerError(pub String);

impl std::fmt::Display for LedgerError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for LedgerError {}

pub trait MemoryLedger {
    fn append(&mut self, record: &MemoryRecord) -> Result<(), LedgerError>;
    fn get(&self, id: u64) -> Result<Option<MemoryRecord>, LedgerError>;
}
