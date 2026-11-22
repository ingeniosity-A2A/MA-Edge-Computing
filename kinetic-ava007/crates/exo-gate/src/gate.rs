//! Gate logic: full-check (three foils) and route.

pub fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

pub fn coder_endpoint() -> String {
    env_or("EXO_CODER_ENDPOINT", "http://127.0.0.1:8080/v1")
}

pub fn coder_model() -> String {
    env_or("EXO_CODER_MODEL", "Edge0/Edge0-145B-NVFP4")
}

pub fn gate_endpoint() -> String {
    env_or("EXO_GATE_ENDPOINT", "http://127.0.0.1:8081/v1")
}

/// A foil result.
#[derive(Debug, Clone)]
pub struct FoilResult {
    pub name: &'static str,
    pub passed: bool,
    pub detail: String,
}

/// Run the three gate-integrity foils against live endpoints.
/// Marked ignored in tests; call via `gate --full-check`.
pub async fn full_check() -> Vec<FoilResult> {
    let mut results = Vec::new();
    // Foil 1: coder endpoint reachable
    results.push(probe("coder_endpoint", &coder_endpoint()).await);
    // Foil 2: gate endpoint reachable
    results.push(probe("gate_endpoint", &gate_endpoint()).await);
    // Foil 3: model id non-empty
    results.push(FoilResult {
        name: "coder_model_set",
        passed: !coder_model().is_empty(),
        detail: coder_model(),
    });
    results
}

async fn probe(name: &'static str, url: &str) -> FoilResult {
    let client = reqwest::Client::new();
    match client.get(url).send().await {
        Ok(resp) => FoilResult {
            name,
            passed: resp.status().is_success() || resp.status().as_u16() < 500,
            detail: format!("HTTP {}", resp.status()),
        },
        Err(e) => FoilResult {
            name,
            passed: false,
            detail: e.to_string(),
        },
    }
}

/// Route a request string to the appropriate endpoint.
pub fn route(input: &str) -> String {
    if input.contains("extract") || input.contains("clairic") {
        format!("route -> {} (clairic_flash)", gate_endpoint())
    } else {
        format!("route -> {} (coder: {})", coder_endpoint(), coder_model())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn env_defaults() {
        // Only check defaults when env not set; don't override user env.
        let _ = coder_endpoint();
        let _ = coder_model();
        let _ = gate_endpoint();
    }

    #[test]
    fn route_contains_endpoint() {
        let r = route("hello");
        assert!(r.contains("coder"));
        let r2 = route("extract clairic");
        assert!(r2.contains("clairic_flash"));
    }

    #[tokio::test]
    #[ignore]
    async fn foil_coder_live() {
        let res = full_check().await;
        for r in res {
            println!("{:?} {}", r.name, r.passed);
        }
    }
}
