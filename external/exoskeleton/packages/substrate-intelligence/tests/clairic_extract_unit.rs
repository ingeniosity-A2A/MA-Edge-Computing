use substrate_intelligence::{ClairicClient, ExtractionRequest};

#[test]
fn extract_value() {
    let req = ExtractionRequest { field: "foo".into(), payload: r#"{"foo": 42}"#.into() };
    let r = ClairicClient::extract(&req);
    assert!(!r.abstained);
    assert!(r.value.is_some());
}

#[test]
fn extract_abstains_null() {
    let req = ExtractionRequest { field: "foo".into(), payload: r#"{"foo": null}"#.into() };
    let r = ClairicClient::extract(&req);
    assert!(r.abstained);
    assert!(r.value.is_none());
}

#[test]
fn extract_abstains_missing() {
    let req = ExtractionRequest { field: "bar".into(), payload: r#"{"foo": 1}"#.into() };
    let r = ClairicClient::extract(&req);
    assert!(r.abstained);
}
