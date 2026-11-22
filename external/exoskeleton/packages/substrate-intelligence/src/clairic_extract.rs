use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", content = "value")]
pub enum ExtractedValue {
    Text(String),
    Number(f64),
    Bool(bool),
    Json(serde_json::Value),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ValueType {
    Text,
    Number,
    Bool,
    Json,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractionRequest {
    pub field: String,
    pub payload: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ExtractionResult {
    pub value: Option<ExtractedValue>,
    pub confidence: f64,
    pub abstained: bool,
    pub source: String,
}

impl ExtractionResult {
    pub fn abstain(source: impl Into<String>) -> Self {
        Self { value: None, confidence: 0.0, abstained: true, source: source.into() }
    }
    pub fn ok(value: ExtractedValue, confidence: f64, source: impl Into<String>) -> Self {
        Self { value: Some(value), confidence: confidence.clamp(0.0, 1.0), abstained: false, source: source.into() }
    }
}

pub struct ClairicClient;

impl ClairicClient {
    pub fn extract(req: &ExtractionRequest) -> ExtractionResult {
        let source = "clairic_flash".to_string();
        let parsed: serde_json::Value = match serde_json::from_str(&req.payload) {
            Ok(v) => v,
            Err(_) => return ExtractionResult::abstain(source),
        };
        let mut cur = &parsed;
        for part in req.field.split('.') {
            match cur.get(part) {
                Some(v) => cur = v,
                None => return ExtractionResult::abstain(source),
            }
        }
        if cur.is_null() {
            return ExtractionResult::abstain(source);
        }
        let val = if let Some(s) = cur.as_str() {
            ExtractedValue::Text(s.to_string())
        } else if let Some(n) = cur.as_f64() {
            ExtractedValue::Number(n)
        } else if let Some(b) = cur.as_bool() {
            ExtractedValue::Bool(b)
        } else {
            ExtractedValue::Json(cur.clone())
        };
        ExtractionResult::ok(val, 1.0, source)
    }
}
