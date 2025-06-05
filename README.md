# PyWatt SDK

[![Latest Version](https://img.shields.io/crates/v/pywatt_sdk.svg)](https://crates.io/crates/pywatt_sdk)
[![Docs](https://docs.rs/pywatt_sdk/badge.svg)](https://docs.rs/pywatt_sdk)

A comprehensive Rust SDK for building PyWatt modules that integrate seamlessly with the PyWatt orchestrator ecosystem.

## Overview

The PyWatt SDK provides a complete toolkit for developing robust, production-ready modules in Rust. It handles the complex orchestration, communication, and security requirements of distributed PyWatt applications, allowing developers to focus on their core business logic.

### Key Features

- **🔄 IPC & Communication**: Multi-channel communication (TCP, Unix sockets) with automatic failover and intelligent routing
- **🔐 Security**: Comprehensive secret management, JWT authentication, and automatic secret redaction
- **📊 Database Integration**: Database-agnostic modeling with schema generation and synchronization
- **🚀 Module Lifecycle**: Automated bootstrap, handshake, and announcement protocols
- **📈 Observability**: Built-in metrics, tracing, and performance monitoring
- **🛠️ Developer Experience**: Procedural macros for rapid development and extensive type safety

## Quick Start

Add the SDK to your `Cargo.toml`:

```toml
[dependencies]
pywatt_sdk = { version = "0.2.9", features = ["proc_macros"] }
tokio = { version = "1", features = ["full"] }
axum = "0.8"
```

Create a simple module:

```rust
use pywatt_sdk::prelude::*;
use axum::{routing::get, Router};

#[derive(Default, Clone)]
struct MyModuleState {
    counter: std::sync::Arc<std::sync::atomic::AtomicU64>,
}

#[pywatt_sdk::module(
    secrets = ["API_KEY"],
    endpoints = [
        AnnouncedEndpoint {
            path: "/count".to_string(),
            methods: vec!["GET".to_string()],
            auth: None,
        }
    ]
)]
async fn my_module(state: AppState<MyModuleState>) -> Router {
    Router::new()
        .route("/count", get(|| async { "Hello from PyWatt!" }))
        .with_state(state)
}
```

## Architecture

The SDK is organized into several core modules, each handling specific aspects of module development:

### 📁 [`rust_sdk/src/core/`](rust_sdk/src/core/README.md)
**Fundamental building blocks for module initialization and state management**

- **`bootstrap.rs`**: Complete module lifecycle management including handshake, secret fetching, and communication setup
- **`state.rs`**: Centralized application state with support for advanced features like routing, failover, and performance monitoring
- **`error.rs`**: Unified error handling system with comprehensive error types
- **`logging.rs`**: Standardized logging with automatic secret redaction
- **`config.rs`**: SDK configuration structures and loading

### 📁 [`rust_sdk/src/communication/`](rust_sdk/src/communication/README.md)
**Comprehensive inter-process communication and networking**

- **Multi-channel support**: TCP, Unix Domain Sockets with automatic failover
- **Message routing**: Intelligent channel selection based on performance and preferences  
- **HTTP tunneling**: HTTP-over-IPC and direct HTTP-over-TCP capabilities
- **Advanced features**: Streaming, compression, circuit breakers, and metrics collection
- **Port negotiation**: Dynamic port allocation from the orchestrator

Key components:
- `tcp_channel.rs` / `ipc_channel.rs`: Channel implementations
- `routing.rs`: Intelligent message routing
- `failover.rs`: Circuit breakers and reliability features
- `streaming.rs`: Large payload streaming support
- `http_ipc/` & `http_tcp/`: HTTP protocol adapters

### 📁 [`rust_sdk/src/security/`](rust_sdk/src/security/README.md)
**Comprehensive security and secret management**

- **Secret management**: Secure retrieval, caching, and rotation handling
- **JWT authentication**: Bearer token validation with Axum middleware integration
- **Type-safe secrets**: Compile-time safety with automatic redaction
- **Pluggable providers**: Environment, file-based, and in-memory secret sources

Key components:
- `secret_client/`: Client-side secret management
- `secret_provider/`: Server-side secret provider implementations
- `jwt_auth/`: JWT middleware for Axum applications
- `secrets/`: High-level secret utilities and typed wrappers

### 📁 [`rust_sdk/src/services/`](rust_sdk/src/services/README.md)
**High-level service components and utilities**

- **Module registration**: TCP-based registration protocol with health reporting
- **Router discovery**: Automatic endpoint discovery from Axum routers
- **Server management**: IPC and HTTP serving with lifecycle management
- **Model manager**: Database-agnostic schema definition and synchronization

Key components:
- `registration/`: Module registration and health reporting
- `model_manager/`: Database modeling toolkit
- `server.rs`: Module serving and lifecycle management
- `router_discovery.rs`: Automatic endpoint discovery

### 📁 [`rust_sdk/src/data/`](rust_sdk/src/data/README.md)
**Data persistence and caching**

- **Database abstraction**: Support for PostgreSQL, MySQL, and SQLite
- **Caching**: Redis, Memcached, and file-based caching implementations
- **Schema management**: Automated migrations and synchronization

### 📁 [`rust_sdk/src/internal/`](rust_sdk/src/internal/README.md)
**Internal utilities and advanced features**

- **Builder patterns**: Fluent APIs for module and state construction
- **Extension traits**: Ergonomic helpers for core SDK types
- **Internal messaging**: Module-to-module communication via orchestrator
- **Macro support**: Core functionality for procedural macros

## Feature Flags

The SDK uses feature flags to enable optional functionality:

### Core Features
- `default = ["tcp", "ipc_channel", "bincode_serialization"]`
- `proc_macros`: Enable the `#[pywatt_sdk::module]` attribute macro
- `jwt_auth`: JWT authentication middleware
- `metrics`: Prometheus metrics collection
- `discover_endpoints`: Automatic endpoint discovery from Axum routers

### Database & Caching
- `database`: Core database functionality
- `postgres`, `mysql`, `sqlite`: Database-specific support
- `redis_cache`, `memcached`, `file_cache`: Caching implementations

### Communication
- `tcp`: TCP communication support
- `ipc_channel`: Unix Domain Socket support
- `tls`, `native_tls`: TLS encryption support
- `advanced_features`: Enable all advanced communication features

### Development
- `builder`: AppState builder pattern
- `router_ext`: Router extension traits
- `cors`: CORS middleware support

## Documentation

### Core Documentation
- **[Module Macro Guide](rust_sdk/docs/module_macro.md)**: Complete guide to the `#[pywatt_sdk::module]` macro
- **[Model Manager Guide](rust_sdk/docs/model_manager.md)**: Database modeling and schema management
- **[Service Integration](rust_sdk/docs/service_integration.md)**: Integrating with PyWatt services
- **[Independent Channels](rust_sdk/docs/independent_channels.md)**: Advanced communication patterns

### API Reference
Each major component includes detailed README files:
- [Core Module](rust_sdk/src/core/README.md)
- [Communication Module](rust_sdk/src/communication/README.md)
- [Security Module](rust_sdk/src/security/README.md)
- [Services Module](rust_sdk/src/services/README.md)
- [Internal Module](rust_sdk/src/internal/README.md)

## Examples

The SDK includes comprehensive examples in [`rust_sdk/examples/`](rust_sdk/examples/):

- **[`macro_example.rs`](rust_sdk/examples/macro_example.rs)**: Using the `#[pywatt_sdk::module]` macro
- **[`guide_example.rs`](rust_sdk/examples/guide_example.rs)**: Manual module setup without macros

## Testing

The SDK includes extensive test coverage in [`rust_sdk/tests/`](rust_sdk/tests/):

- **Integration tests**: End-to-end module lifecycle testing
- **Feature tests**: Testing optional feature combinations
- **IPC tests**: Communication protocol validation
- **Database tests**: Schema management and persistence
- **Security tests**: Secret management and JWT validation

Run tests with:
```bash
cd rust_sdk
cargo test
cargo test --all-features  # Test with all features enabled
```

## Procedural Macros

The SDK includes a separate procedural macro crate at [`rust_sdk/pywatt_macros/`](rust_sdk/pywatt_macros/README.md) that provides the `#[pywatt_sdk::module]` attribute macro for simplified module development.

## Development Tools

### Database Tool
The SDK includes a command-line tool for database operations:

```bash
# Generate SQL from model definitions
database-tool schema generate --model-file models.yaml --database-type postgres

# Apply schema to database
database-tool schema apply --model-file models.yaml --database-config config.toml

# Validate model definitions
database-tool model validate --model-file models.yaml
```

### Docker Testing
Use the provided Docker testing script:

```bash
cd rust_sdk
./scripts/test_with_docker.sh
```

## Contributing

1. **Explore the codebase**: Start with the [core module](rust_sdk/src/core/README.md) documentation
2. **Run tests**: Ensure all tests pass with `cargo test --all-features`
3. **Follow conventions**: Use `cargo fmt` and `cargo clippy`
4. **Update documentation**: Keep README files and examples current

## License

This project is licensed under the MIT OR Apache-2.0 license. See [LICENSE-MIT](LICENSE-MIT) or [LICENSE-APACHE](LICENSE-APACHE) for details.

## Version

Current version: **0.2.9**

For detailed changelog and migration guides, see the [releases page](https://github.com/frostdev-ops/pywatt_sdk/releases). 