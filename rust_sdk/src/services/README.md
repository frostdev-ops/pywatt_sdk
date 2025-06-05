# Services Module

This directory provides high-level SDK service components for the PyWatt Rust SDK.

## Submodules

- **registration/** ([README](registration/README.md))
  - Implements module registration protocol over TCP:
    - `register_module` / `unregister_module`
    - `heartbeat` health reporting
    - `advertise_capabilities` for endpoints and message types
- **announce.rs**: Handles sending the module's announcement to the orchestrator.
  - Function: `send_announce(announce: &AnnounceBlob) -> Result<(), AnnounceError>`
    - Takes an `AnnounceBlob` (from `crate::ipc_types`) containing module details (ID, version, endpoints, etc.).
    - Wraps it in `ModuleToOrchestrator::Announce` (from `crate::ipc_types`).
    - Serializes the wrapped structure to a single-line JSON string.
    - Writes this JSON string to `stdout` and flushes `stdout`. This is the standard mechanism for modules to communicate their initial announcement to the PyWatt orchestrator.
  - Errors: `AnnounceError` enum captures issues like `Serialization(serde_json::Error)` or `Io(std::io::Error)`.
  - Example:
    ```rust,no_run
    use pywatt_sdk::ipc_types::{Announce as AnnounceBlob, ModuleInfo as IpcModuleInfo}; // Renamed to avoid conflict if ModuleInfo from registration is in scope
    use pywatt_sdk::services::announce::send_announce;
    use pywatt_sdk::AnnouncedEndpoint;
    use uuid::Uuid;
    use std::collections::HashMap;

    fn do_announce() -> Result<(), pywatt_sdk::services::announce::AnnounceError> {
        let announce_data = AnnounceBlob {
            module_id: Uuid::new_v4().to_string(),
            module_info: IpcModuleInfo {
                name: "MyModule".to_string(),
                version: "0.1.0".to_string(),
                description: Some("A sample PyWatt module.".to_string()),
                ipc_version: "1.0".to_string(), // Example IPC version
            },
            endpoints: vec![
                AnnouncedEndpoint {
                    path: "/status".to_string(),
                    methods: vec!["GET".to_string()],
                    auth: None,
                }
            ],
            port: Some(8080),
            secret_keys_provided: Vec::new(),
            custom_capabilities: Some(HashMap::new()),
        };
        send_announce(&announce_data)
    }
    ```
- **model_manager/** ([README](model_manager/README.md))
  - Database-agnostic model definition and schema management
  - SQL generation (`ModelGenerator`), config (`ModelManagerConfig`), adapters
  - SDK integration trait `ModelManager` for live schema application
- **router_discovery.rs**: Provides utilities to discover HTTP endpoints from an Axum `Router`. (Feature-gated by `discover_endpoints`)
  - Main Function: `announce_from_router(router: &Router) -> Vec<AnnouncedEndpoint>`
    - Purpose: Intended to traverse an Axum `Router` to extract its defined routes (paths and HTTP methods) and convert them into a `Vec<AnnouncedEndpoint>` (where `AnnouncedEndpoint` is from `crate`). This list can then be used in the module's announcement.
    - Current Implementation (when feature is enabled): The actual traversal of Axum's internal router structure is complex due to its private internals. The current version provides a placeholder or basic discovery, often returning a predefined set of common endpoints or using simplified pattern matching (as seen in `discover_endpoints_advanced`).
    - Helper utilities like `normalize_method`, `has_path_parameters`, and `extract_base_path` assist in processing discovered route information.
  - If the `discover_endpoints` feature is *not* enabled, `announce_from_router` and related functions return an empty `Vec<AnnouncedEndpoint>`.
  - Example (illustrating intended use):
    ```rust,no_run
    # #[cfg(feature = "discover_endpoints")]
    # {
    use axum::{Router, routing::{get, post}};
    use pywatt_sdk::services::router_discovery::announce_from_router;
    use pywatt_sdk::AnnouncedEndpoint;

    let api_routes = Router::new().route("/users/:id", get(|| async { "User" }));
    let app_router = Router::new()
        .route("/foo", get(|| async { "Hello" }))
        .route("/bar", post(|| async { "Post" }))
        .nest("/api", api_routes);

    let discovered_endpoints: Vec<AnnouncedEndpoint> = announce_from_router(&app_router);
    // discovered_endpoints would ideally contain representations for:
    // "/foo" (GET), "/bar" (POST), "/api/users/:id" (GET)
    // (Actual output depends on the current placeholder implementation if feature is active)
    # }
    ```
- **server.rs**: Manages serving the module's Axum router over IPC and/or HTTP.
  - Core Functionality:
    - **IPC Serving (`serve_ipc`)**: (Requires `ipc_channel` feature)
      - Subscribes to HTTP-over-IPC requests using `IpcManager`.
      - Converts incoming `IpcHttpRequest` into Axum `Request<AxumBody>`.
      - Dispatches the request to the provided Axum `Router`.
      - Converts the Axum `Response` back into an `IpcHttpResponse` and sends it via `IpcManager`.
    - **HTTP Binding & Port Negotiation**:
      - `ServeOptions` struct: Configures server behavior (`bind_http: bool`, `specific_port: Option<u16>`, `listen_addr: Option<String>`).
      - `negotiate_port(specific_port: Option<u16>) -> Result<u16, Error>`: (Requires `ipc_channel` feature)
        - First checks for a pre-allocated port (set via `set_pre_allocated_port`, typically from `InitBlob` during module handshake).
        - If no pre-allocated port, sends an `IpcPortNegotiation` request to the orchestrator to obtain a port.
      - `set_pre_allocated_port(port: u16)` / `get_pre_allocated_port() -> Option<u16>`: Manage port information received during module initialization.
    - **Main Server Functions**:
      - `serve_with_options(app: axum::Router, options: ServeOptions) -> Result<(), Error>`:
        - Always starts the IPC serving task (`serve_ipc`) if the `ipc_channel` feature is enabled.
        - If `options.bind_http` is true, it calls `negotiate_port` (if `ipc_channel` enabled) or uses `options.specific_port` or a random port, and then starts an HTTP server (e.g., `axum::serve`) listening on the obtained port and specified address (defaults to `127.0.0.1`).
        - If `!options.bind_http`, sets `IPC_ONLY=true` / `PYWATT_IPC_ONLY=true` environment variables to signal other SDK components (like secret management) to operate in IPC-only mode.
      - `serve_module(app: axum::Router) -> Result<(), Error>`: A simpler entry point, typically defaults to `serve_with_options` with default options (HTTP binding enabled).
      - `serve_module_full(...)` / `serve_module_with_lifecycle(...)`: High-level functions designed to manage the complete module lifecycle including initialization (logging, handshake), secret fetching, state and router building, announcement of endpoints, and then serving the module using `serve_with_options`. These are often the primary entry points for starting a PyWatt module.
  - Errors: `Error` enum (e.g., `Io`, `Announce` (from `crate::services::announce`), `Config`, `Server`, `Internal`).
  - Conceptual Example (`serve_module_full`):
    ```rust,no_run
    # #[cfg(all(feature = "ipc_channel", feature = "secrets_management"))]
    # async fn run_module() -> Result<(), Box<dyn std::error::Error>> {
    use pywatt_sdk::prelude::*;
    use pywatt_sdk::services::server::serve_module_full;
    use axum::{Router, routing::get, Extension};
    use secrecy::SecretString;
    use std::collections::HashMap;
    use std::sync::Arc;

    #[derive(Clone)]
    struct MyState { api_key: SecretString }

    async fn build_my_state(
        _init_data: &OrchestratorInit, // Contains info from orchestrator
        secrets: Arc<HashMap<String, SecretString>> // Secrets fetched by the SDK
    ) -> Result<MyState, Box<dyn std::error::Error + Send + Sync>> {
        Ok(MyState {
            api_key: secrets.get("MY_API_KEY").cloned().unwrap_or_else(|| SecretString::from("default_key"))
        })
    }

    fn build_my_router(app_state: AppState<MyState>) -> Router {
        Router::new()
            .route("/my_data", get(|Extension(state): Extension<AppState<MyState>>| async move {
                // Use state.inner.api_key.expose_secret() securely
                format!("Sensitive data processed with key: {}", state.inner.api_key.expose_secret().chars().take(5).collect::<String>())
            }))
            .layer(Extension(app_state))
    }
    
    let secret_keys_to_fetch = vec!["MY_API_KEY".to_string()];
    let announced_endpoints = vec![
        AnnouncedEndpoint { path: "/my_data".to_string(), methods: vec!["GET".to_string()], auth: Some("APIKeyRequired".to_string()) }
    ];

    // This function call orchestrates the entire module startup and serving process.
    serve_module_full(
        secret_keys_to_fetch,
        announced_endpoints,
        build_my_state,
        build_my_router
    ).await?;
    # Ok(())
    # }
    ```
- **mod.rs**
  - Module-level documentation and re-exports of service APIs

Each subdirectory (e.g., `registration`, `model_manager`) includes its own detailed README with deeper insights.
