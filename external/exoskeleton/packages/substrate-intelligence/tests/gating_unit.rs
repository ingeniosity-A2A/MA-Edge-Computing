use substrate_intelligence::GatingEngine;

#[test]
fn hard_veto_subprocess() {
    let engine = GatingEngine::new();
    let r = engine.verify_text("std::process::Command::new(\"python\")", "bad.rs");
    assert!(matches!(r.verdict, substrate_intelligence::Verdict::HardVeto));
    assert!(r.hard_veto_count > 0);
}

#[test]
fn pass_clean_code() {
    let engine = GatingEngine::new();
    let r = engine.verify_text("fn add(a: i32, b: i32) -> i32 { a + b }", "clean.rs");
    assert!(matches!(r.verdict, substrate_intelligence::Verdict::Pass));
}

#[test]
fn soft_flag_superlative() {
    let engine = GatingEngine::new();
    let r = engine.verify_text("// this is the best approach", "soft.rs");
    assert!(matches!(r.verdict, substrate_intelligence::Verdict::SoftDisagreement));
}
