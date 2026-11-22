use axum::{
    extract::State,
    http::{HeaderValue, Method, StatusCode},
    routing::post,
    Json, Router,
};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{net::SocketAddr, path::PathBuf, sync::Arc};
use tokio::{fs, process::Command};
use tower_http::cors::{Any, CorsLayer};

#[derive(Clone)]
struct AppState {
    http: Client,
    refs_dir: PathBuf,
    coder_url: String,
    gate_url: String,
    steel_cdp: String,
}

#[derive(Deserialize)]
struct ParseReq {
    input: String,
}

#[derive(Serialize)]
struct RefResp {
    ref_path: String,
}

#[derive(Deserialize)]
struct SteelReq {
    url: String,
    tool: String,
}

#[derive(Deserialize)]
struct RetrieveReq {
    query: String,
    top_k: Option<usize>,
}

#[derive(Serialize)]
struct RetrieveResp {
    refs: Vec<String>,
}

#[derive(Deserialize)]
struct RouteReq {
    task: String,
}

#[derive(Serialize)]
struct RouteResp {
    seat: String,
    confidence: f64,
    escalate: bool,
}

#[derive(Deserialize)]
struct DispatchReq {
    prompt: String,
    refs: Vec<String>,
}

fn hash_prefix(data: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data.as_bytes());
    hex::encode(hasher.finalize())[..12].to_string()
}

async fn cap_parse(
    State(st): State<Arc<AppState>>,
    Json(req): Json<ParseReq>,
) -> Result<Json<RefResp>, StatusCode> {
    fs::create_dir_all(&st.refs_dir).await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let filename = format!("parse_{}.md", hash_prefix(&req.input));
    let full_path = st.refs_dir.join(&filename);
    fs::write(&full_path, &req.input).await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    Ok(Json(RefResp {
        ref_path: format!("refs/{}", filename),
    }))
}

async fn cap_steel(
    State(st): State<Arc<AppState>>,
    Json(req): Json<SteelReq>,
) -> Result<Json<RefResp>, StatusCode> {
    let allowed = [
        "agent-readiness",
        "page-to-markdown",
        "structured-data",
        "mermaid-page-map",
        "extract-media",
    ];
    if !allowed.contains(&req.tool.as_str()) {
        return Err(StatusCode::BAD_REQUEST);
    }
    let out = Command::new("pnpm")
        .args([
            "exec",
            "tsx",
            "packages/steel-tools/src/inject_bookmarklets.ts",
            &req.url,
            &req.tool,
            &st.steel_cdp,
        ])
        .output()
        .await
        .map_err(|_| StatusCode::BAD_GATEWAY)?;
    if !out.status.success() {
        return Err(StatusCode::BAD_GATEWAY);
    }
    let body = String::from_utf8_lossy(&out.stdout).to_string();
    fs::create_dir_all(&st.refs_dir).await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let filename = format!("steel_{}_{}.md", req.tool, hash_prefix(&body));
    fs::write(st.refs_dir.join(&filename), &body)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    Ok(Json(RefResp {
        ref_path: format!("refs/{}", filename),
    }))
}

async fn cap_retrieve(
    State(st): State<Arc<AppState>>,
    Json(req): Json<RetrieveReq>,
) -> Result<Json<RetrieveResp>, StatusCode> {
    let top_k = req.top_k.unwrap_or(3);
    let mut refs = Vec::new();
    if let Ok(mut entries) = fs::read_dir(&st.refs_dir).await {
        let needle = req.query.to_lowercase();
        while let Ok(Some(entry)) = entries.next_entry().await {
            if refs.len() >= top_k {
                break;
            }
            if let Ok(content) = fs::read_to_string(entry.path()).await {
                if content.to_lowercase().contains(&needle) {
                    refs.push(format!("refs/{}", entry.file_name().to_string_lossy()));
                }
            }
        }
    }
    Ok(Json(RetrieveResp { refs }))
}

async fn cap_route(
    State(st): State<Arc<AppState>>,
    Json(req): Json<RouteReq>,
) -> Json<RouteResp> {
    let stripped: String = req.task.chars().take(1000).collect();
    let payload = json!({
        "model": "MachinePulseAI/karpo-decision-31B",
        "state": { "task": stripped },
        "questions": {
            "seat": {
                "type": "choice",
                "criteria": {
                    "lookup": "Find, list, summarize, or explain existing code/docs",
                    "build":  "Edit code with a clear spec in <= 3 files",
                    "hard":   "Unknown bug, 2+ failed attempts, design choice, or 4+ files",
                    "big":    "Multi-part job splitting into parallel non-overlapping briefs",
                    "other":  "Unclear or irreversible action"
                }
            }
        }
    });
    let res = st.http.post(&st.gate_url).json(&payload).send().await;
    if let Ok(resp) = res {
        if let Ok(body) = resp.json::<Value>().await {
            let seat = body["answers"]["seat"]["choice"]
                .as_str()
                .unwrap_or("other")
                .to_string();
            let conf = body["answers"]["seat"]["confidence"]
                .as_f64()
                .unwrap_or(0.0);
            let escalate = conf < 0.90 || matches!(seat.as_str(), "hard" | "big" | "other");
            return Json(RouteResp { seat, confidence: conf, escalate });
        }
    }
    Json(RouteResp {
        seat: "unsure".into(),
        confidence: 0.0,
        escalate: true,
    })
}

async fn exo_dispatch(
    State(st): State<Arc<AppState>>,
    Json(req): Json<DispatchReq>,
) -> Result<Json<Value>, StatusCode> {
    let mut context_block = String::new();
    for r in &req.refs {
        if let Some(name) = r.strip_prefix("refs/") {
            if !name.contains("..") && !name.contains('/') {
                if let Ok(txt) = fs::read_to_string(st.refs_dir.join(name)).await {
                    context_block.push_str(&format!("\n--- {} ---\n{}\n", r, txt));
                }
            }
        }
    }
    let payload = json!({
        "model": "Edge0/Edge0-145B-NVFP4",
        "temperature": 0.2,
        "messages": [
            { "role": "user", "content": format!("{}\n{}", req.prompt, context_block) }
        ]
    });
    let resp = st
        .http
        .post(format!("{}/chat/completions", st.coder_url))
        .json(&payload)
        .send()
        .await
        .map_err(|_| StatusCode::BAD_GATEWAY)?;
    let body: Value = resp.json().await.map_err(|_| StatusCode::BAD_GATEWAY)?;
    Ok(Json(body))
}

#[tokio::main]
async fn main() {
    let state = Arc::new(AppState {
        http: Client::new(),
        refs_dir: PathBuf::from("./refs"),
        coder_url: std::env::var("EXO_CODER_URL")
            .unwrap_or_else(|_| "http://127.0.0.1:8080/v1".into()),
        gate_url: std::env::var("EXO_GATE_URL")
            .unwrap_or_else(|_| "http://127.0.0.1:8081/v1/systemone".into()),
        steel_cdp: std::env::var("STEEL_CDP_URL")
            .unwrap_or_else(|_| "ws://127.0.0.1:3000/".into()),
    });
    let cors = CorsLayer::new()
        .allow_origin("http://127.0.0.1:3000".parse::<HeaderValue>().unwrap())
        .allow_methods([Method::POST, Method::OPTIONS])
        .allow_headers(Any);
    let app = Router::new()
        .route("/cap/parse", post(cap_parse))
        .route("/cap/steel", post(cap_steel))
        .route("/cap/retrieve", post(cap_retrieve))
        .route("/cap/route", post(cap_route))
        .route("/exo/dispatch", post(exo_dispatch))
        .layer(cors)
        .with_state(state);
    let addr = SocketAddr::from(([127, 0, 0, 1], 8090));
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    println!("exo-gateway listening on http://{}", addr);
    axum::serve(listener, app).await.unwrap();
}
