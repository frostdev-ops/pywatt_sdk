# PyWatt Module Template

A template for creating PyWatt-Rust modules that follow the standardized modular architecture.

## Overview

This template implements all the required components for a PyWatt module:

- Module manifest with endpoint definitions
- JSONL handshake protocol implementation
- Required endpoints: `/health`, `/metrics`, and `/ping`
- Secret management integration
- CLI with `--describe` option for manifest inspection

## Getting Started

1. Clone this template to create a new module:

```bash
cp -r src/pywatt-module-template src/modules/my_new_module
cd src/modules/my_new_module
```

2. Update the module identity in:
   - `Cargo.toml`: Change package name and description
   - `manifest.toml`: Update name, version, and endpoints
   - `src/main.rs`: Modify constants and implement your endpoints

3. Build and test your module:

```bash
cargo build
cargo run -- --describe  # Print manifest
```

## Module Contract

Each PyWatt module must:

1. Run as a separate process
2. Listen on an allocated TCP port (default: first available in 4100-4999 range)
3. Implement the JSONL handshake protocol
4. Expose required endpoints: `/health` and `/metrics`
5. Provide a valid manifest

## Handshake Protocol

The module follows this startup sequence:

1. Receives handshake JSON from orchestrator via stdin
2. Processes environment variables and secrets
3. Sends module registration JSON to stdout
4. Starts HTTP server on the specified port

## Adding New Endpoints

To add new functionality:

1. Update manifest.toml with your new endpoints
2. Add the routes in `src/main.rs`:

```rust
.route("/api/my-endpoint", post(my_handler))
```

3. Create the corresponding handler function:

```rust
async fn my_handler() -> impl IntoResponse {
    // Your implementation here
}
```

## Health Checks

The built-in `/health` endpoint can be configured to return different statuses based on your module's internal state. Update the health status mutex to reflect your module's health.

## Metrics

The `/metrics` endpoint provides Prometheus-compatible metrics. Add your custom metrics to the registry in the `AppState`.

## Secret Management

Use the `request_secret` function to fetch secrets from the orchestrator.

## See Also

For more detailed information, refer to the [Module Development Guide](../docs/modules.md).
