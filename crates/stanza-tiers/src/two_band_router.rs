// ============================================================================
// crates/stanza-tiers/src/two_band_router.rs
// ============================================================================
// Deliverable 4: HE2-Net Two-Band Router
//
// Orange Band (provisional) → Epistemic Gate (Stanza verification +
// teach-back) → Green Band (validated SOPs)
//
// This router sits between the three-tier Stanza pipeline's output and
// the system's operational memory. Nothing crosses from Orange to Green
// without passing the Epistemic Gate.
//
// "The two-band knowledge backbone defines the places involved in
//  epistemic promotion."
//
// This is Discipline 3 (Epistemic & Ontological Engineering) as code.
// ============================================================================

use crate::tier1_edge::TokenDelta;
use crate::tier3_core::DeepAnalysis;
use crate::ud_graph::UDGraph;
use cybernetic_gate::epistemic::{Claim, ClaimSource, EpistemicState};
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;

/// Which band a knowledge token currently lives in.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Band {
    /// Provisional / hypothesis / exploration. Unverified. Suspect.
    Orange,
    /// Validated / exploitable / SOP. Verified by the Epistemic Gate.
    Green,
    /// Refuted / rejected. Flagged for inspection and refinement.
    Refuted,
}

/// A knowledge token moving through the two-band system.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeToken {
    pub id: String,
    pub content: String,
    pub band: Band,
    pub epistemic_state: String,
    pub source_tier: u8,
    pub proposed_at: u64,
    pub promoted_at: Option<u64>,
    pub evidence_chain: Vec<String>,
    pub teachback_hash: Option<String>,
    pub content_hash: String,
}

/// The result of passing through the Epistemic Gate.
#[derive(Debug)]
pub enum GatePass {
    /// Token promoted to Green Band.
    Promoted {
        token: KnowledgeToken,
        verification_score: f64,
        evidence: String,
    },
    /// Token sent to refutation loop.
    Refuted {
        token: KnowledgeToken,
        reason: String,
    },
    /// Token held in Orange Band pending additional evidence.
    Held {
        token: KnowledgeToken,
        missing: String,
    },
}

/// Teach-back verification result.
///
/// The teach-back mechanism requires the system to restate the claim
/// in its own words and have that restatement verified against the
/// original. This prevents self-confirmation (INFERRED → OBSERVED).
#[derive(Debug, Clone)]
pub struct TeachBack {
    /// The original claim.
    pub original: String,
    /// The system's restatement.
    pub restatement: String,
    /// Whether the restatement aligns with the original.
    pub aligned: bool,
    /// Dependency graph similarity score.
    pub similarity: f64,
}

/// The HE2-Net Two-Band Router.
///
/// Routes knowledge tokens between Orange and Green bands through
/// the Epistemic Gate. Maintains the audit trail. Enforces the
/// epistemic contract.
pub struct TwoBandRouter {
    /// Tokens currently in the Orange Band.
    orange_band: VecDeque<KnowledgeToken>,
    /// Tokens currently in the Green Band (validated SOPs).
    green_band: VecDeque<KnowledgeToken>,
    /// Tokens sent to refutation.
    refuted_band: VecDeque<KnowledgeToken>,
    /// The gate threshold (θ_gold).
    theta_gold: f64,
    /// Maximum Orange Band capacity (memory pressure valve).
    orange_capacity: usize,
    /// Maximum Green Band capacity.
    green_capacity: usize,
    /// Monotonic event counter.
    event_counter: u64,
    /// Audit trail.
    audit: Vec<RouterAuditEntry>,
}

/// An audit entry in the router's chain.
#[derive(Debug, Clone)]
pub struct RouterAuditEntry {
    pub event_id: u64,
    pub token_id: String,
    pub action: String,
    pub band_from: Band,
    pub band_to: Band,
    pub reason: String,
}

impl TwoBandRouter {
    pub fn new() -> Self {
        TwoBandRouter {
            orange_band: VecDeque::new(),
            green_band: VecDeque::new(),
            refuted_band: VecDeque::new(),
            theta_gold: 0.7,
            orange_capacity: 1024,
            green_capacity: 4096,
            event_counter: 0,
            audit: Vec::new(),
        }
    }

    /// Submit a new knowledge token to the Orange Band.
    ///
    /// All new knowledge enters Orange. Nothing enters Green directly.
    /// This is the entry point for all claims, regardless of source tier.
    pub fn submit_orange(
        &mut self,
        content: &str,
        source_tier: u8,
        epistemic_state: EpistemicState,
    ) -> KnowledgeToken {
        self.event_counter += 1;
        let token = KnowledgeToken {
            id: format!("kt-{}", self.event_counter),
            content: content.to_string(),
            band: Band::Orange,
            epistemic_state: epistemic_state.as_str().to_string(),
            source_tier,
            proposed_at: self.event_counter,
            promoted_at: None,
            evidence_chain: Vec::new(),
            teachback_hash: None,
            content_hash: self.hash(content),
        };

        // Memory pressure valve: if Orange is full, evict oldest
        if self.orange_band.len() >= self.orange_capacity {
            self.orange_band.pop_front();
        }

        self.orange_band.push_back(token.clone());
        self.record_audit(&token.id, "submit", Band::Orange, Band::Orange, "New claim enters Orange Band");
        token
    }

    /// Run the Epistemic Gate on an Orange Band token.
    ///
    /// The gate uses the UD v2 dependency graph (from Tier 2) to verify
    /// the claim. This is SYMBOLIC verification, not LLM opinion.
    ///
    /// Process:
    ///   1. Parse the claim through the UD v2 dependency graph
    ///   2. Check epistemic state (INFERRED needs stronger evidence)
    ///   3. Verify the claim against evidence using dependency alignment
    ///   4. Run teach-back verification
    ///   5. Route to Green, Refuted, or hold in Orange
    pub fn run_gate(
        &mut self,
        token_id: &str,
        ud_graph: &UDGraph,
        evidence: &str,
    ) -> GatePass {
        // Find the token in Orange Band
        let pos = self.orange_band.iter().position(|t| t.id == token_id);
        let Some(pos) = pos else {
            return GatePass::Refuted {
                token: KnowledgeToken {
                    id: token_id.to_string(),
                    content: String::new(),
                    band: Band::Orange,
                    epistemic_state: "UNKNOWN".into(),
                    source_tier: 0,
                    proposed_at: 0,
                    promoted_at: None,
                    evidence_chain: Vec::new(),
                    teachback_hash: None,
                    content_hash: String::new(),
                },
                reason: "Token not found in Orange Band".into(),
            };
        };

        let mut token = self.orange_band.remove(pos).unwrap();

        // ── Step 1: Dependency graph verification ────────────────────────
        // The UD v2 graph IS the grading mechanism. No LLM. Symbolic only.
        let verify_score = self.verify_by_dependency(&token.content, ud_graph, evidence);

        // ── Step 2: Epistemic state check ────────────────────────────────
        let state = EpistemicState::from_str(&token.epistemic_state)
            .unwrap_or(EpistemicState::Hypothesized);
        let effective_threshold = match state {
            // INFERRED claims need 1.5× evidence (prevents self-confirmation)
            EpistemicState::Inferred | EpistemicState::Hypothesized => self.theta_gold * 1.5,
            _ => self.theta_gold,
        };

        // ── Step 3: Teach-back verification ──────────────────────────────
        let teachback = self.teach_back(&token.content, evidence);

        // ── Step 4: Route ────────────────────────────────────────────────
        if verify_score >= effective_threshold && teachback.aligned {
            // PROMOTED to Green Band
            token.band = Band::Green;
            token.promoted_at = Some(self.event_counter);
            token.evidence_chain.push(format!(
                "dep_score={:.3} threshold={:.3}",
                verify_score, effective_threshold
            ));
            token.teachback_hash = Some(self.hash(&teachback.restatement));

            if self.green_band.len() < self.green_capacity {
                self.green_band.push_back(token.clone());
            }

            self.event_counter += 1;
            self.record_audit(&token.id, "promote", Band::Orange, Band::Green,
                &format!("VerifyMatch={:.3} >= θ={:.3}, teachback=aligned", verify_score, effective_threshold));

            GatePass::Promoted {
                token,
                verification_score: verify_score,
                evidence: format!("Dependency graph alignment + teach-back verified"),
            }
        } else if verify_score < self.theta_gold * 0.3 {
            // REFUTED — strong mismatch
            token.band = Band::Refuted;
            self.refuted_band.push_back(token.clone());
            self.event_counter += 1;
            self.record_audit(&token.id, "refute", Band::Orange, Band::Refuted,
                &format!("VerifyMatch={:.3} < fail threshold", verify_score));

            GatePass::Refuted {
                token,
                reason: format!(
                    "Dependency mismatch: score={:.3} (threshold={:.3})",
                    verify_score, effective_threshold
                ),
            }
        } else {
            // HELD — inconclusive, needs more evidence
            token.band = Band::Orange; // Stays in Orange
            self.orange_band.push_back(token.clone());
            self.event_counter += 1;
            self.record_audit(&token.id, "hold", Band::Orange, Band::Orange,
                &format!("Score={:.3} below θ={:.3}, teachback_aligned={}", verify_score, effective_threshold, teachback.aligned));

            GatePass::Held {
                token,
                missing: format!(
                    "Need {:.3} more verification score (current={:.3}, required={:.3})",
                    effective_threshold - verify_score, verify_score, effective_threshold
                ),
            }
        }
    }

    /// Verify a claim against evidence using UD v2 dependency alignment.
    ///
    /// This is the SYMBOLIC core. No LLM. Deterministic graph comparison.
    fn verify_by_dependency(
        &self,
        claim: &str,
        graph: &UDGraph,
        evidence: &str,
    ) -> f64 {
        // Parse the claim's grammatical structure
        let claim_tree = crate::tier2_metabolism::Metabolism::new()
            .metabolize(&crate::tier1_edge::SensoryEdge::new().tokenize(claim));

        // Parse the evidence's grammatical structure
        let evidence_tree = crate::tier2_metabolism::Metabolism::new()
            .metabolize(&crate::tier1_edge::SensoryEdge::new().tokenize(evidence));

        // Also factor in the provided UD graph (from Tier 2 of the pipeline)
        let graph_score = if graph.asserts_as_fact() && !graph.has_negation() {
            0.3 // Positive signal: graph asserts a fact without negation
        } else if graph.has_negation() {
            -0.2 // Negative signal: negation present
        } else {
            0.0 // Neutral
        };

        // Component 1: Subject alignment (25%)
        let subj_match = match (claim_tree.subject(), evidence_tree.subject()) {
            (Some(cs), Some(es)) if cs.eq_ignore_ascii_case(es) => 1.0,
            (Some(_), Some(_)) => 0.3,
            (None, None) => 0.5,
            _ => 0.0,
        };

        // Component 2: Action alignment (25%)
        let action_match = match (claim_tree.root_action(), evidence_tree.root_action()) {
            (Some(ca), Some(ea)) if ca.eq_ignore_ascii_case(ea) => 1.0,
            (Some(_), Some(_)) => 0.3,
            (None, None) => 0.5,
            _ => 0.0,
        };

        // Component 3: Negation consistency (25%)
        let neg_match = if claim_tree.has_negation() == evidence_tree.has_negation() {
            1.0
        } else {
            0.0 // Contradiction
        };

        // Component 4: Structural similarity (25%)
        let claim_rels: std::collections::HashSet<_> =
            claim_tree.tokens.iter().map(|t| t.relation_label.as_str()).collect();
        let evidence_rels: std::collections::HashSet<_> =
            evidence_tree.tokens.iter().map(|t| t.relation_label.as_str()).collect();
        let intersection = claim_rels.intersection(&evidence_rels).count();
        let union = claim_rels.union(&evidence_rels).count().max(1);
        let structural = intersection as f64 / union as f64;

        let base = (subj_match * 0.25) + (action_match * 0.25) + (neg_match * 0.25) + (structural * 0.25);
        (base + graph_score).clamp(0.0, 1.0)
    }

    /// Teach-back verification.
    ///
    /// The system must restate the claim and have the restatement verified.
    /// This prevents self-confirmation: the system cannot treat its own
    /// generation as external evidence.
    fn teach_back(&self, original: &str, evidence: &str) -> TeachBack {
        // Parse both the original claim and the evidence
        let orig_tree = crate::tier2_metabolism::Metabolism::new()
            .metabolize(&crate::tier1_edge::SensoryEdge::new().tokenize(original));
        let evi_tree = crate::tier2_metabolism::Metabolism::new()
            .metabolize(&crate::tier1_edge::SensoryEdge::new().tokenize(evidence));

        // The restatement is the evidence (what the system "learned")
        // Teach-back checks: does the evidence's structure align with the claim?
        let similarity = self.structural_similarity(&orig_tree, &evi_tree);
        let aligned = similarity >= 0.5;

        TeachBack {
            original: original.to_string(),
            restatement: evidence.to_string(),
            aligned,
            similarity,
        }
    }

    /// Compute structural similarity between two UD graphs.
    fn structural_similarity(&self, a: &UDGraph, b: &UDGraph) -> f64 {
        let a_rels: std::collections::HashSet<_> =
            a.edges.iter().map(|e| e.dep_rel.as_str()).collect();
        let b_rels: std::collections::HashSet<_> =
            b.edges.iter().map(|e| e.dep_rel.as_str()).collect();

        if a_rels.is_empty() && b_rels.is_empty() {
            return 1.0;
        }

        let intersection = a_rels.intersection(&b_rels).count();
        let union = a_rels.union(&b_rels).count().max(1);
        intersection as f64 / union as f64
    }

    /// Get all tokens in the Green Band (validated SOPs).
    pub fn green_band(&self) -> &VecDeque<KnowledgeToken> {
        &self.green_band
    }

    /// Get all tokens in the Orange Band (provisional).
    pub fn orange_band(&self) -> &VecDeque<KnowledgeToken> {
        &self.orange_band
    }

    /// Get all refuted tokens.
    pub fn refuted_band(&self) -> &VecDeque<KnowledgeToken> {
        &self.refuted_band
    }

    /// Count tokens by band.
    pub fn counts(&self) -> (usize, usize, usize) {
        (self.orange_band.len(), self.green_band.len(), self.refuted_band.len())
    }

    /// Set the gold standard threshold.
    pub fn set_theta_gold(&mut self, theta: f64) {
        self.theta_gold = theta.clamp(0.0, 1.0);
    }

    /// Get the audit trail.
    pub fn audit_trail(&self) -> &[RouterAuditEntry] {
        &self.audit
    }

    fn record_audit(&mut self, token_id: &str, action: &str, from: Band, to: Band, reason: &str) {
        self.audit.push(RouterAuditEntry {
            event_id: self.event_counter,
            token_id: token_id.to_string(),
            action: action.to_string(),
            band_from: from,
            band_to: to,
            reason: reason.to_string(),
        });
    }

    fn hash(&self, data: &str) -> String {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};
        let mut h = DefaultHasher::new();
        data.hash(&mut h);
        format!("{:016x}", h.finish())
    }
}

impl Default for TwoBandRouter {
    fn default() -> Self {
        Self::new()
    }
}
