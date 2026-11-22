use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.iter().any(|a| a == "--full-check") {
        let results = full_check_foils();
        for r in &results {
            println!("{}: {} ({})", r.0, if r.1 { "PASS" } else { "FAIL" }, r.2);
        }
        let all = results.iter().all(|r| r.1);
        std::process::exit(if all { 0 } else { 1 });
    }
    if let Some(idx) = args.iter().position(|a| a == "--route") {
        if let Some(task) = args.get(idx + 1) {
            println!("{}", route_task(task));
        }
    }
}

fn full_check_foils() -> Vec<(&'static str, bool, String)> {
    let coder = env::var("EXO_CODER_ENDPOINT").unwrap_or_else(|_| "http://127.0.0.1:8080/v1".into());
    let gate = env::var("EXO_GATE_ENDPOINT").unwrap_or_else(|_| "http://127.0.0.1:8081/v1".into());
    let model = env::var("EXO_CODER_MODEL").unwrap_or_else(|_| "Edge0/Edge0-145B-NVFP4".into());
    let mut results = Vec::new();
    let ok1 = ureq::get(&format!("{}/models", coder.trim_end_matches("/v1"))).call().map(|r| r.status().as_u16() < 500).unwrap_or(false);
    results.push(("coder_endpoint", ok1, coder.clone()));
    let ok2 = ureq::get(&format!("{}/models", gate.trim_end_matches("/v1"))).call().map(|r| r.status().as_u16() < 500).unwrap_or(false);
    results.push(("gate_endpoint", ok2, gate.clone()));
    results.push(("coder_model_set", !model.is_empty(), model));
    results
}

fn route_task(task: &str) -> String {
    let lower = task.to_lowercase();
    let seat = if lower.contains("extract") || lower.contains("clairic") {
        "clairic_flash"
    } else if lower.contains("find") || lower.contains("list") {
        "lookup"
    } else {
        "coder"
    };
    format!("route -> {}", seat)
}
