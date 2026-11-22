//! Typed extraction contracts for Cloudflare / clairic-flash.
//!
//! `cap.extract.clairic_flash` performs a typed extraction over a raw payload.
//! When the extractor cannot produce a value (null result) it *abstains*: the
//! result carries `None` and no promotion is implied.

use serde::{Deserialize, Serialize};

/// A typed value produced by an extractor.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", content = "value")]
pub enum ExtractedValue {
    Text(String),
    Number(f64),
    Bool(bool),
    Json(serde_json::Value),
}

/// Outcome of an extraction attempt.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ExtractionResult<T> {
    /// The extracted value, or `None` when the extractor abstains (null).
    pub value: Option<T>,
    /// Confidence in [0.0, 1.0]. 0.0 when abstaining.
    pub confidence: f64,
    /// Whether abstention occurred.
    pub abstained: bool,
    /// Provenance / source identifier.
    pub source: String,
}

impl<T> ExtractionResult<T> {
    pub fn abstain(source: impl Into<String>) -> Self {
        Self {
            value: None,
            confidence: 0.0,
            abstained: true,
            source: source.into(),
        }
    }

    pub fn ok(value: T, confidence: f64, source: impl Into<String>) -> Self {
        Self {
            value: Some(value),
            confidence: confidence.clamp(0.0, 1.0),
            abstained: false,
            source: source.into(),
        }
    }
}

/// Contract for a typed extraction capability.
pub trait Extractor<T> {
    fn name(&self) -> &'static str;
    fn extract(&self, payload: &str) -> ExtractionResult<T>;
}

/// clairic-flash extractor: pulls a field from a JSON payload by path.
/// Returns `None` (abstains) when the field is missing or null.
pub struct ClairicFlashExtractor {
    pub field: String,
}

impl Extractor<serde_json::Value> for ClairicFlashExtractor {
    fn name(&self) -> &'static str {
        "cap.extract.clairic_flash"
    }

    fn extract(&self, payload: &str) -> ExtractionResult<serde_json::Value> {
        let source = "clairic_flash".to_string();
        let parsed: serde_json::Value = match serde_json::from_str(payload) {
            Ok(v) => v,
            Err(_) => return ExtractionResult::abstain(source),
        };
        // Walk dotted path.
        let mut cur = &parsed;
        for part in self.field.split('.') {
            match cur.get(part) {
                Some(v) => cur = v,
                None => return ExtractionResult::abstain(source),
            }
        }
        if cur.is_null() {
            return ExtractionResult::abstain(source);
        }
        ExtractionResult::ok(cur.clone(), 1.0, source)
    }
}

/// Convenience function matching the capability name.
pub fn cap_extract_clairic_flash(field: &str, payload: &str) -> ExtractionResult<serde_json::Value> {
    ClairicFlashExtractor { field: field.to_string() }.extract(payload)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn abstains_on_null_field() {
        let r = cap_extract_clairic_flash("foo", r#"{"foo": null}"#);
        assert!(r.abstained);
        assert!(r.value.is_none());
    }

    #[test]
    fn abstains_on_missing_field() {
        let r = cap_extract_clairic_flash("bar", r#"{"foo": 1}"#);
        assert!(r.abstained);
    }

    #[test]
    fn extracts_value() {
        let r = cap_extract_clairic_flash("foo", r#"{"foo": 42}"#);
        assert!(!r.abstained);
        assert_eq!(r.value, Some(serde_json::json!(42)));
    }

    #[test]
    fn dotted_path() {
        let r = cap_extract_clairic_flash("a.b", r#"{"a": {"b": "hi"}}"#);
        assert_eq!(r.value, Some(serde_json::json!("hi")));
    }

    #[test]
    fn invalid_json_abstains() {
        let r = cap_extract_clairic_flash("foo", "not json");
        assert!(r.abstained);
    }
}
