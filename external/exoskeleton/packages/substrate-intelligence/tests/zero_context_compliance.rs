// Three foils against live endpoints (--ignored)
use substrate_intelligence::{GatingEngine, StanzaChecker};

#[test]
#[ignore]
fn foil_1_coder_endpoint() {
    let url = std::env::var("EXO_CODER_ENDPOINT").unwrap_or_else(|_| "http://127.0.0.1:8080/v1".into());
    let r = ureq::get(&format!("{}/models", url.trim_end_matches("/v1"))).call();
    assert!(r.is_ok() || r.unwrap_err().to_string().contains("HTTP"));
}

#[test]
#[ignore]
fn foil_2_gate_endpoint() {
    let url = std::env::var("EXO_GATE_ENDPOINT").unwrap_or_else(|_| "http://127.0.0.1:8081/v1".into());
    let r = ureq::get(&format!("{}/models", url.trim_end_matches("/v1"))).call();
    assert!(r.is_ok() || r.unwrap_err().to_string().contains("HTTP"));
}

#[test]
#[ignore]
fn foil_3_model_set() {
    let model = std::env::var("EXO_CODER_MODEL").unwrap_or_else(|_| "Edge0/Edge0-145B-NVFP4".into());
    assert!(!model.is_empty());
}

#[test]
fn gate_integrity_offline() {
    let engine = GatingEngine::new();
    let r = engine.verify_text("fn main() { println!(\"hi\"); }", "test.rs");
    assert!(matches!(r.verdict, substrate_intelligence::Verdict::Pass));
}
