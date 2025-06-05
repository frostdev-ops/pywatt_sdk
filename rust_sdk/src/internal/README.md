# Internal SDK Low-Level Modules and Utilities

This directory contains the foundational building blocks and private utilities of the PyWatt SDK. These components are not intended for direct end-user consumption but provide critical functionality that underpins module bootstrap, extension traits, inter-module messaging, macro support, and JSON utilities.

# Table of Contents

- [Overview](#overview)
- [Modules](#modules)
- [Feature Flags](#feature-flags)
- [Subdirectories](#subdirectories)
- [Contributing](#contributing)

## Overview

The `internal` directory groups together code that enables advanced SDK functionality:

- **Module Builders**: Fluent APIs to bootstrap modules and assemble application state.
- **Extension Traits**: Ergonomic helpers for core SDK types like `OrchestratorInit` and `Router`.
- **Internal Messaging**: Client logic to route messages between modules via the orchestrator.
- **Macro Utilities**: Core macro initialization and re-exports for proc-macro support.
- **JSON Helpers**: Simple functions to serialize and print JSON to stdout/stderr.

### Why “internal”?

These modules are hidden from the primary SDK surface to maintain a clean public API. Advanced users or SDK contributors may explore or extend these components when working on lower-level integrations or debugging complex behaviors.

## Modules

### builder.rs

- **Purpose**: Implements builder patterns for module bootstrap and direct `AppState` construction.

- **Key Types**:
  - `ModuleBuilder<T>`: Orchestrates:
    1. Handshake with orchestrator
    2. Secret retrieval
    3. Endpoint announcement
    4. Internal messaging client setup

  - `AppStateBuilder<T>` *(feature `builder`)*: Allows manual composition of `AppState<T>` without full network bootstrap.

- **Important Methods**:
  - `secret_keys(&mut self, keys: &[&str])` — specify which secrets to fetch.
  - `endpoints(&mut self, endpoints: Vec<AnnouncedEndpoint>)` — define service endpoints to announce.
  - `state<F>(builder: F)` — closure constructing user state from `OrchestratorInit` and secrets.
  - `build(self) -> Result<(AppState<T>, JoinHandle<()>), BootstrapError>` — executes the full bootstrap flow.
  - `AppStateBuilder::build() -> Result<AppState<T>, ConfigError>` — finalizes a local-only state.

- **Example**:
  ```rust
  let (app_state, handle) = ModuleBuilder::new()
      .secret_keys(&["DB_URL", "API_KEY"])
      .endpoints(vec![AnnouncedEndpoint::new("compute", "/compute")])
      .state(|init, secrets| MyState::new(init, secrets))
      .build().await?;
  ```

### ext.rs

- **Purpose**: Add ergonomic extension methods to existing SDK types.

- **Traits & Methods**:
  - `OrchestratorInitExt`
    - `listen_to_string(&self) -> String` — yields `Tcp(addr)` or `Unix(path)`.
    - `listen_address(&self) -> &ListenAddress` — raw enum reference.
  - `ListenExt`
    - `to_string_lossy(&self) -> String` — similar conversion on `ListenAddress`.
  - `RouterExt` *(feature `router_ext`)*
    - `with_default_health()` — mounts `/health` returning build metadata.
    - `with_cors_preflight()` *(feature `cors`)* — CORS middleware and preflight handler.
    - `with_prometheus_metrics()` *(feature `metrics`)* — `/metrics` endpoint with Prometheus integration.

- **Example**:
  ```rust
  let router = Router::new()
      .with_default_health()
      .with_prometheus_metrics();
  ```

### internal_messaging.rs

- **Purpose**: Facilitate asynchronous request/response messaging between modules through the orchestrator.

- **Key Struct**:
  - `InternalMessagingClient`:
    - `orchestrator_channel: Arc<TcpChannel>`
    - `pending_responses: PendingInternalResponses` (map of UUID to response senders)
    - `default_encoding: EncodingFormat`

- **Main API**:
  - `send_request<Req, Res>(target_module_id, target_endpoint, payload, timeout)` — sends a typed request, awaits typed response.
  - `process_routed_module_response(...)` — called internally to dispatch incoming responses to awaiting callers.

- **Error Handling**:
  - `InternalMessagingError` covers serialization, network, timeout, target not found, application errors, deserialization.

### macros.rs

- **Purpose**: Provide basic module initialization and entrypoint macros.

- **Items**:
  - `module_init() -> Result<(), Error>` — sets up basic logging and environment.
  - `module()` placeholder when `proc_macros` disabled.
  - Re-export of `#[module]` attribute from proc-macro crate when `proc_macros` feature is enabled.

- **Usage**:
  ```rust
  #[tokio::main]
  async fn main() -> Result<(), Box<dyn std::error::Error>> {
      module_init().await?;
      // module code...
      Ok(())
  }
  ```

### utils.rs

- **Purpose**: Simplify JSON serialization and output for debugging or structured logging.

- **Functions**:
  - `print_json<T: Serialize>(&T)`
  - `print_pretty_json<T: Serialize>(&T)`
  - `eprint_json<T: Serialize>(&T)`
  - `eprint_pretty_json<T: Serialize>(&T)`

- **Return**: `Result<(), serde_json::Error>` for error propagation.

## Feature Flags

| Feature         | Description                                           |
|-----------------|-------------------------------------------------------|
| `builder`       | Enables `AppStateBuilder<T>` and related tests.       |
| `router_ext`    | Activates `RouterExt` methods for health/metrics.     |
| `cors`          | Provides CORS preflight handling in `RouterExt`.      |
| `metrics`       | Adds Prometheus endpoint in `RouterExt`.              |
| `ipc_channel`   | Enables TCP-based constructors for messaging client.   |
| `proc_macros`   | Exposes `#[module]` procedural macro from proc-macro crate. |

## Subdirectories

- **`pywatt_macros/`**: Integration stubs and re-exports for procedural macros. Real implementations are in the workspace root `pywatt_macros` crate (crate-type = "proc-macro").

## Contributing

1. Update or extend functionality in the appropriate `.rs` file.
2. Reflect new methods or types in this README, adding examples.
3. Maintain consistency in feature flags and `Cargo.toml` entries.
4. Run `cargo fmt`, `cargo clippy`, and `cargo test` to verify.  

_This README provides a comprehensive reference for developers and maintainers working on the internal SDK modules._
