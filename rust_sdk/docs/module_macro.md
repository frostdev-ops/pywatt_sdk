# PyWatt SDK Module Macro Documentation

## Overview

The `#[pywatt_sdk::module]` macro is a procedural macro that simplifies the creation of PyWatt modules by automatically generating the boilerplate code required for module initialization, handshake, secret management, and lifecycle management.

## Macro Syntax

```rust
#[pywatt_sdk::module(
    secrets = ["SECRET_KEY1", "SECRET_KEY2"],
    endpoints = [
        AnnouncedEndpoint { path: "/path", methods: vec!["GET"], auth: None },
        // ... more endpoints
    ],
    health = "/health",      // Optional: health check endpoint
    metrics = true,          // Optional: enable Prometheus metrics
    state = state_builder    // Function to build custom state
)]
async fn module_function(state: AppState<CustomState>) -> Router {
    // Return your Axum router here
}
```

## Macro Parameters

### Required Parameters

- **`secrets`**: Array of secret keys to fetch at startup
  - Type: `&[&str]`
  - Example: `["DATABASE_URL", "API_KEY", "JWT_SECRET"]`

- **`endpoints`**: Array of endpoints to announce to the orchestrator
  - Type: `&[AnnouncedEndpoint]`
  - Each endpoint must specify `path`, `methods`, and optional `auth`

- **`state`**: Function that builds custom state from init data and secrets
  - Type: `fn(&OrchestratorInit, Vec<SecretString>) -> CustomState`
  - Must be a function that takes init data and secrets, returns custom state

### Optional Parameters

- **`health`**: Path for health check endpoint (defaults to "/health")
  - Type: `&str`
  - The macro will automatically add a health endpoint if specified

- **`metrics`**: Enable Prometheus metrics collection (defaults to false)
  - Type: `bool`
  - Adds `/metrics` endpoint when enabled

## Generated Code

The macro generates a complete `main()` function that:

1. **Initializes logging** with proper redaction
2. **Performs handshake** with the orchestrator
3. **Fetches secrets** specified in the `secrets` parameter
4. **Builds custom state** using the provided `state` function
5. **Creates AppState** with SDK context and custom state
6. **Builds router** by calling the annotated function
7. **Announces endpoints** to the orchestrator
8. **Starts IPC processing** in background
9. **Serves the module** using Axum

## Complete Example

Here's how to use the macro:

```rust
use pywatt_sdk::prelude::*;
use axum::{Router, routing::get, Extension, Json};
use secrecy::{SecretString, ExposeSecret};
use serde_json::Value;

// Define your custom state
#[derive(Clone, Debug)]
struct MyModuleState {
    database_url: String,
    api_key: String,
    feature_flags: Vec<String>,
}

// State builder function
fn build_my_state(init: &OrchestratorInit, secrets: Vec<SecretString>) -> MyModuleState {
    let database_url = secrets
        .get(0)
        .map(|s| s.expose_secret().clone())
        .unwrap_or_else(|| "sqlite::memory:".to_string());
    
    let api_key = secrets
        .get(1)
        .map(|s| s.expose_secret().clone())
        .unwrap_or_else(|| "development-key".to_string());
    
    MyModuleState {
        database_url,
        api_key,
        feature_flags: vec!["feature_a".to_string(), "feature_b".to_string()],
    }
}

// Use the macro to define your module
#[pywatt_sdk::module(
    secrets = ["DATABASE_URL", "API_KEY"],
    endpoints = [
        AnnouncedEndpoint { 
            path: "/status".to_string(), 
            methods: vec!["GET".to_string()], 
            auth: None 
        },
        AnnouncedEndpoint { 
            path: "/config".to_string(), 
            methods: vec!["GET".to_string()], 
            auth: Some("jwt".to_string()) 
        }
    ],
    health = "/health",
    metrics = true,
    state = build_my_state
)]
async fn my_module(state: AppState<MyModuleState>) -> Router {
    Router::new()
        .route("/status", get(status_handler))
        .route("/config", get(config_handler))
        .layer(Extension(state))
}

// Handler functions
async fn status_handler(Extension(state): Extension<AppState<MyModuleState>>) -> Json<Value> {
    Json(serde_json::json!({
        "status": "ok",
        "module_id": state.module_id(),
        "database_connected": !state.user_state.database_url.is_empty(),
        "feature_flags": state.user_state.feature_flags
    }))
}

async fn config_handler(Extension(state): Extension<AppState<MyModuleState>>) -> Json<Value> {
    Json(serde_json::json!({
        "database_url": "[REDACTED]", // Never expose secrets
        "api_key": "[REDACTED]",
        "feature_flags": state.user_state.feature_flags,
        "orchestrator_api": state.orchestrator_api()
    }))
}
```

## Manual Equivalent

The macro generates code equivalent to this manual implementation:

```rust
#[tokio::main]
async fn main() -> Result<()> {
    // 1. Initialize logging
    init_module();

    // 2. Perform handshake
    let init = read_init::<OrchestratorInit>().await?;

    // 3. Fetch secrets
    let secret_client = get_module_secret_client(&init.orchestrator_api, &init.module_id).await?;
    let secrets = get_secrets(&secret_client, vec!["DATABASE_URL", "API_KEY"]).await?;

    // 4. Build custom state
    let custom_state = build_my_state(&init, secrets);

    // 5. Create AppState
    let app_state = AppState::new(
        init.module_id.clone(),
        init.orchestrator_api.clone(),
        Arc::new(secret_client),
        custom_state,
    );

    // 6. Build router
    let router = my_module(app_state.clone()).await;

    // 7. Announce endpoints
    let endpoints = vec![
        AnnouncedEndpoint { path: "/status".to_string(), methods: vec!["GET".to_string()], auth: None },
        AnnouncedEndpoint { path: "/config".to_string(), methods: vec!["GET".to_string()], auth: Some("jwt".to_string()) },
        AnnouncedEndpoint { path: "/health".to_string(), methods: vec!["GET".to_string()], auth: None },
    ];
    send_announce(&AnnounceBlob {
        listen: init.listen.clone(),
        endpoints,
    })?;

    // 8. Start IPC processing
    let ipc_handle = tokio::spawn(async move {
        process_ipc_messages(secret_client).await
    });

    // 9. Serve the module
    serve_module(router, &init.listen.parse()?).await?;

    Ok(())
}
```

## Current Implementation Status

Based on the current macro implementation in `pywatt_macros/src/lib.rs`, the macro:

1. ✅ Parses the attribute arguments correctly
2. ✅ Validates required parameters (secrets, endpoints, state)
3. ✅ Generates a complete main() function
4. ✅ Includes proper error handling
5. ✅ Supports optional health and metrics endpoints
6. ✅ Uses the correct SDK functions for lifecycle management

## Error Handling

The macro includes comprehensive error handling:

- **Handshake errors**: Logged and cause process exit
- **Secret fetch errors**: Logged and cause process exit  
- **State building errors**: Compilation errors if state function is invalid
- **Server errors**: Logged and propagated through the Result type

## Best Practices

1. **Keep state builders simple**: State building functions should be deterministic and fast
2. **Handle missing secrets gracefully**: Provide sensible defaults for development
3. **Don't expose secrets in logs**: Use "[REDACTED]" placeholders in responses
4. **Use proper authentication**: Specify `auth: Some("jwt")` for protected endpoints
5. **Follow naming conventions**: Use kebab-case for endpoint paths

## Debugging

If the macro isn't working as expected:

1. Check that all required parameters are provided
2. Ensure the state builder function signature is correct
3. Verify that `AnnouncedEndpoint` structs are properly formatted
4. Use `cargo expand` to see the generated code (requires cargo-expand)
5. Check compiler errors carefully - they'll point to the specific issue

## Migration from Manual Implementation

To migrate from manual implementation to the macro:

1. Extract your state building logic into a separate function
2. List all secrets your module needs
3. Define your endpoints using `AnnouncedEndpoint` structs
4. Replace your main() function with the macro annotation
5. Test that the behavior is identical 