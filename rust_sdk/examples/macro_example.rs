use pywatt_sdk::prelude::*;
use axum::{Router, routing::get, Extension, Json};
use secrecy::{SecretString, ExposeSecret};
use serde_json::Value;

// Custom state for our module
#[derive(Clone, Debug)]
struct MyModuleState {
    database_url: String,
    api_key: String,
}

// State builder function
fn build_my_state(_init: &OrchestratorInit, secrets: Vec<SecretString>) -> MyModuleState {
    let database_url = secrets
        .get(0)
        .map(|s| s.expose_secret().to_string())
        .unwrap_or_else(|| "sqlite::memory:".to_string());
    
    let api_key = secrets
        .get(1)
        .map(|s| s.expose_secret().to_string())
        .unwrap_or_else(|| "development-key".to_string());
    
    MyModuleState {
        database_url,
        api_key,
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    // Manual implementation demonstrating what the macro would generate
    let secret_keys = vec!["DATABASE_URL".to_string(), "API_KEY".to_string()];
    
    let endpoints = vec![
        AnnouncedEndpoint { 
            path: "/status".to_string(), 
            methods: vec!["GET".to_string()], 
            auth: None 
        }
    ];
    
    let state_builder = build_my_state;
    
    let router_builder = |app_state: AppState<MyModuleState>| {
        Router::new()
            .route("/status", get(status_handler))
            .route("/health", get(health_handler))
            .layer(Extension(app_state))
    };
    
    serve_module_full(secret_keys, endpoints, state_builder, router_builder).await?;
    Ok(())
}

// Handler functions
async fn status_handler(Extension(state): Extension<AppState<MyModuleState>>) -> Json<Value> {
    Json(serde_json::json!({
        "status": "ok",
        "module_id": state.module_id(),
        "database_connected": !state.user_state.database_url.is_empty()
    }))
}

async fn health_handler() -> Json<Value> {
    Json(serde_json::json!({
        "status": "healthy",
        "timestamp": chrono::Utc::now().to_rfc3339(),
        "version": env!("CARGO_PKG_VERSION")
    }))
} 