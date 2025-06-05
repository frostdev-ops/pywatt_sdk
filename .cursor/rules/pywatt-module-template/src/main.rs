use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use clap::{Parser, Subcommand};
use futures::StreamExt;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    env,
    io::{self, BufRead, BufReader, Write},
    net::SocketAddr,
    path::PathBuf,
    process::exit,
    sync::Arc,
};
use tokio::{
    net::TcpListener,
    sync::{Mutex, RwLock},
};
use tower_http::trace::TraceLayer;
use tracing::{info, warn, error, debug};
use prometheus::{Registry, TextEncoder, Encoder};

// The module's manifest information
const MODULE_NAME: &str = "pywatt_module_template";
const MODULE_VERSION: &str = "0.1.0";
const COMPATIBLE_CORE: &str = ">=1.0.0, <2.0.0";

#[derive(Parser)]
#[command(author, version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Prints the module manifest in JSON format
    Describe,
}

// Module state
#[derive(Clone)]
struct AppState {
    secrets: Arc<RwLock<HashMap<String, String>>>,
    metrics: Arc<Registry>,
    health_status: Arc<Mutex<bool>>,
}

// ======================
// Handshake Protocol
// ======================

#[derive(Debug, Serialize, Deserialize)]
struct OrchestratorHandshake {
    orchestrator_api: String,
    module_id: String,
    env: HashMap<String, String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct ModuleRegistration {
    listen: String,
    endpoints: Vec<EndpointInfo>,
}

#[derive(Debug, Serialize, Deserialize)]
struct EndpointInfo {
    path: String,
    methods: Vec<String>,
    auth: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct SecretRequest {
    op: String,
    name: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct SecretResponse {
    op: String,
    name: String,
    value: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct ManifestInfo {
    name: String,
    version: String,
    compatible_core: String,
    executable: String,
    transport: String,
    env: Vec<String>,
    endpoints: HashMap<String, EndpointManifestInfo>,
}

#[derive(Debug, Serialize, Deserialize)]
struct EndpointManifestInfo {
    methods: Vec<String>,
    auth: Option<String>,
    timeout: Option<String>,
}

// ======================
// API endpoints
// ======================

async fn health_check(State(state): State<AppState>) -> impl IntoResponse {
    let is_healthy = *state.health_status.lock().await;
    if is_healthy {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    }
}

async fn metrics(State(state): State<AppState>) -> impl IntoResponse {
    let encoder = TextEncoder::new();
    let metric_families = state.metrics.gather();
    
    match encoder.encode_to_string(&metric_families) {
        Ok(metrics_output) => Response::builder()
            .status(StatusCode::OK)
            .header("Content-Type", "text/plain")
            .body(metrics_output.into())
            .unwrap(),
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR.into_response(),
    }
}

async fn ping() -> impl IntoResponse {
    "pong"
}

// Sample endpoint - replace with actual module functionality
async fn hello_world() -> impl IntoResponse {
    Json(serde_json::json!({
        "message": "Hello from PyWatt module template!",
        "status": "success"
    }))
}

// Secret request handler
async fn request_secret(name: &str, state: &AppState) -> Option<String> {
    // Check if we already have it cached
    {
        let secrets = state.secrets.read().await;
        if let Some(value) = secrets.get(name) {
            return Some(value.clone());
        }
    }
    
    // Request from orchestrator
    let request = SecretRequest {
        op: "get_secret".to_string(),
        name: name.to_string(),
    };
    
    let json = serde_json::to_string(&request).unwrap();
    println!("{}", json);
    
    // In a real implementation, we would read the response
    // For this template, just return a dummy value
    None
}

// ======================
// Main functions
// ======================

async fn start_server(state: AppState, port: u16) -> io::Result<()> {
    let app = Router::new()
        .route("/health", get(health_check))
        .route("/metrics", get(metrics))
        .route("/ping", get(ping))
        .route("/api/hello", get(hello_world))
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    info!("Starting server on {}", addr);
    
    let listener = TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    
    Ok(())
}

fn register_with_orchestrator(port: u16) -> ModuleRegistration {
    let registration = ModuleRegistration {
        listen: format!("127.0.0.1:{}", port),
        endpoints: vec![
            EndpointInfo {
                path: "/api/hello".to_string(),
                methods: vec!["GET".to_string()],
                auth: None,
            },
        ],
    };
    
    // Print the registration to stdout for the orchestrator
    let json = serde_json::to_string(&registration).unwrap();
    println!("{}", json);
    
    registration
}

fn print_manifest() {
    let manifest = ManifestInfo {
        name: MODULE_NAME.to_string(),
        version: MODULE_VERSION.to_string(),
        compatible_core: COMPATIBLE_CORE.to_string(),
        executable: "pywatt_module_template".to_string(),
        transport: "http".to_string(),
        env: vec!["DATABASE_URL".to_string(), "REDIS_URL".to_string()],
        endpoints: {
            let mut map = HashMap::new();
            map.insert(
                "/api/hello".to_string(), 
                EndpointManifestInfo {
                    methods: vec!["GET".to_string()],
                    auth: None,
                    timeout: Some("30s".to_string()),
                }
            );
            map
        },
    };
    
    println!("{}", serde_json::to_string_pretty(&manifest).unwrap());
}

fn setup_logging() {
    tracing_subscriber::fmt()
        .with_env_filter("info")
        .init();
}

async fn process_orchestrator_handshake() -> Option<OrchestratorHandshake> {
    let stdin = io::stdin();
    let mut reader = BufReader::new(stdin.lock());
    let mut line = String::new();
    
    debug!("Waiting for orchestrator handshake...");
    if reader.read_line(&mut line).is_ok() {
        match serde_json::from_str::<OrchestratorHandshake>(&line) {
            Ok(handshake) => {
                debug!("Received handshake from orchestrator");
                Some(handshake)
            }
            Err(e) => {
                error!("Failed to parse orchestrator handshake: {}", e);
                None
            }
        }
    } else {
        error!("Failed to read from stdin");
        None
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    setup_logging();
    
    let cli = Cli::parse();
    
    // Handle CLI commands
    if let Some(Commands::Describe) = cli.command {
        print_manifest();
        return Ok(());
    }
    
    info!("Starting {} v{}", MODULE_NAME, MODULE_VERSION);
    
    // Initialize state
    let state = AppState {
        secrets: Arc::new(RwLock::new(HashMap::new())),
        metrics: Arc::new(Registry::new()),
        health_status: Arc::new(Mutex::new(true)),
    };
    
    // Process handshake
    let handshake = match process_orchestrator_handshake().await {
        Some(h) => h,
        None => {
            error!("Failed to complete handshake - exiting");
            exit(1);
        }
    };
    
    // Store environment variables
    {
        let mut secrets = state.secrets.write().await;
        for (key, value) in handshake.env {
            secrets.insert(key, value);
        }
    }
    
    // Determine port
    let port = 4100;  // In a real implementation, this would be dynamically allocated
    
    // Register with orchestrator
    let registration = register_with_orchestrator(port);
    
    // Start HTTP server
    if let Err(e) = start_server(state, port).await {
        error!("Server error: {}", e);
        exit(1);
    }
    
    Ok(())
}
