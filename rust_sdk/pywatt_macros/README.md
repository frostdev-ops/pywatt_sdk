# PyWatt Macros

This crate provides procedural macros to simplify the development of Rust-based PyWatt modules.

## `#[pywatt_sdk::module]`

The primary macro offered is `#[pywatt_sdk::module]`. This attribute macro is designed to be applied to an `async` function that returns an `axum::Router` and takes an `pywatt_sdk::AppState<T>` as its argument (where `T` is your custom module state).

It automates the following boilerplate tasks:

1.  **Initialization**: Sets up module logging.
2.  **Orchestrator Handshake**: Reads initial configuration from the orchestrator.
3.  **Secret Management**:
    *   Creates a `SecretClient` for interacting with the orchestrator's secret service.
    *   Prefetches specified secrets.
    *   Optionally subscribes to secret rotation events for the prefetched secrets.
4.  **State Creation**:
    *   Builds the user-defined module state. It calls a user-provided state builder function (or `Default::default()` if none is specified), passing the orchestrator's initialization data and any prefetched secrets.
    *   Constructs the main `pywatt_sdk::AppState` which wraps the user state and other SDK components.
5.  **Router Setup**:
    *   Calls the annotated function to get the base Axum router.
    *   Layers the `pywatt_sdk::AppState` into the router so it's accessible to handlers.
6.  **Standard Endpoints**:
    *   Adds a health check endpoint (defaults to `/health`, path is configurable).
    *   Optionally adds a Prometheus metrics endpoint (defaults to `/metrics`, currently a placeholder).
7.  **Module Announcement**: Announces the module's listen address and its HTTP endpoints (including health and metrics if enabled) to the orchestrator.
8.  **Server Startup**: Starts an Axum HTTP server listening on the TCP address provided by the orchestrator.

### Arguments

The `#[pywatt_sdk::module]` macro accepts the following arguments:

*   `secrets: [&str]`: An array of secret keys (string literals) to be prefetched at startup. Example: `secrets = ["api_key", "db_password"]`.
*   `rotate: bool`: If `true`, subscribes to rotation events for the secrets specified in the `secrets` argument. Defaults to `false`. Example: `rotate = true`.
*   `endpoints: [AnnouncedEndpoint]`: An array of `pywatt_sdk::AnnouncedEndpoint` structs describing the custom endpoints your module provides. Example: `endpoints = [pywatt_sdk::AnnouncedEndpoint { path: "/my/data".to_string(), methods: vec!["GET".to_string(), "POST".to_string()], auth: None }]`.
*   `health: &str` (or `health_path: &str`): Optional. Custom path for the health check endpoint. Defaults to `"/health"`. Example: `health = "/status"`.
*   `metrics: bool`: If `true`, enables a `/metrics` endpoint. Defaults to `false`. Example: `metrics = true`.
*   `version: &str`: Optional. A version string to prefix all announced custom endpoint paths (health and metrics paths are not prefixed). Example: `version = "v1"` would change an endpoint `/data` to `/v1/data` in the announcement.
*   `state: fn_path`: Optional. A path to a function that builds your custom module state. The function must have a signature compatible with `fn(&pywatt_sdk::OrchestratorInit, Vec<secrecy::SecretString>) -> UserStateType`. If not provided, `Default::default()` is used to create the user state. Example: `state = my_custom_state_builder`.
*   `channels`, `security_level`, `auth_required`: These arguments are currently parsed but ignored. They are included for potential future compatibility.

### Example Usage

```rust
use pywatt_sdk::{self, AppState, AnnouncedEndpoint, Result};
use axum::{routing::get, Router};
use secrecy::ExposeSecret;

// Define your custom module state (if any)
#[derive(Default, Clone)]
struct MyModuleState {
    api_key: Option<String>,
}

// Optional: Define a custom state builder function
fn build_my_state(init_data: &pywatt_sdk::OrchestratorInit, secrets: Vec<secrecy::SecretString>) -> MyModuleState {
    println!("Building MyModuleState. Orchestrator API: {}", init_data.orchestrator_api);
    let mut api_key = None;
    if let Some(secret_value) = secrets.get(0) { // Assuming "MY_API_KEY" is the first secret
        api_key = Some(secret_value.expose_secret().clone());
        println!("API Key prefetched!");
    }
    MyModuleState { api_key }
}

async fn get_hello(state: AppState<MyModuleState>) -> String {
    if let Some(key) = &state.user_state.api_key {
        format!("Hello from PyWatt module with API key: {}...", &key[..5])
    } else {
        "Hello from PyWatt module!".to_string()
    }
}

#[pywatt_sdk::module(
    secrets = ["MY_API_KEY"],
    rotate = true,
    endpoints = [
        AnnouncedEndpoint {
            path: "/hello".to_string(),
            methods: vec!["GET".to_string()],
            auth: None,
        }
    ],
    state = build_my_state,
    version = "v1"
)]
async fn my_module_router(state: AppState<MyModuleState>) -> Router {
    Router::new().route("/hello", get(get_hello).with_state(state))
}

// The macro will generate the main function and all boilerplate.
// To run this (assuming it's in src/main.rs and Cargo.toml is set up):
// cargo run
```

This macro significantly reduces the amount of code needed to get a PyWatt module up and running, allowing developers to focus on the module's core logic.
