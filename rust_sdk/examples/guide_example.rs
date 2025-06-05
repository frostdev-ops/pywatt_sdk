use pywatt_sdk::prelude::*;
use axum::{Router, routing::get, Extension};
use secrecy::{SecretString, ExposeSecret};

// Custom state
#[derive(Clone)]
struct MyState { 
    db_url: String 
}

// State builder function as described in the guide
fn build_state(
    init: &OrchestratorInit,
    secrets: Vec<SecretString>
) -> MyState {
    let db_url = secrets
        .get(0)
        .map(|s| s.expose_secret().to_string())
        .unwrap_or_default();
    MyState { db_url }
}

#[tokio::main]
async fn main() -> Result<()> {
    // 1. List secrets to fetch
    let secret_keys = vec!["DB_URL".to_string(), "API_KEY".to_string()];

    // 2. Declare endpoints (manual announcement)
    let endpoints = vec![
      AnnouncedEndpoint { path: "/status".into(), methods: vec!["GET".into()], auth: None }
    ];

    // 3. State builder
    let state_builder = |init: &OrchestratorInit, secrets: Vec<SecretString>| MyState {
        db_url: secrets.get(0).map(|s| s.expose_secret().to_string()).unwrap_or_default()
    };

    // 4. Router builder
    let router_builder = |app_state: AppState<MyState>| {
      Router::new()
        .route("/status", get(|Extension(s): Extension<AppState<MyState>>| async move {
           format!("DB URL: {}", s.user_state.db_url)
        }))
        .layer(Extension(app_state))
    };

    // 5. Run server - this now works exactly as the guide describes!
    serve_module_full(secret_keys, endpoints, state_builder, router_builder).await?;
    Ok(())
} 