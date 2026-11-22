#![forbid(unsafe_code)]

pub mod gating;
pub mod stanza;
pub mod disagreement;
pub mod route;
pub mod clairic_extract;
pub mod receipt;
pub mod audit;

pub use gating::{GateResult, GatingEngine, Severity, VetoRule, VetoViolation, Verdict};
pub use stanza::{InvariantResult, StanzaChecker, StructuralInvariant};
pub use disagreement::{ConfidenceAggregate, DisagreementCalculator, DisagreementResult, ModelOutput};
pub use route::{RouteDecision, RouteEngine, Seat};
pub use clairic_extract::{ExtractionRequest, ExtractionResult, ClairicClient, ExtractedValue, ValueType};
pub use receipt::{EpistemicReceipt, EpistemicState, ReceiptValidator};
pub use audit::{AuditEvent, AuditLedger};
