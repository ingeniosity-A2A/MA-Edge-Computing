use substrate_intelligence::StanzaChecker;

#[test]
fn invariants_list() {
    let invs = StanzaChecker::invariants();
    assert_eq!(invs.len(), 6);
}

#[test]
fn check_clean_dir() {
    let tmp = tempfile::tempdir().unwrap();
    std::fs::write(tmp.path().join("clean.rs"), "fn main() {}\n").unwrap();
    let res = StanzaChecker::check(tmp.path().to_str().unwrap());
    assert_eq!(res.len(), 6);
    assert!(res.iter().all(|r| r.passed));
}

#[test]
fn check_detects_subprocess() {
    let tmp = tempfile::tempdir().unwrap();
    std::fs::write(tmp.path().join("bad.rs"), "std::process::Command::new(\"x\")\n").unwrap();
    let res = StanzaChecker::check(tmp.path().to_str().unwrap());
    let si1 = res.iter().find(|r| r.invariant_id == "SI-001").unwrap();
    assert!(!si1.passed);
}
