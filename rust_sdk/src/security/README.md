# Security Module

The security module provides comprehensive security functionality for the PyWatt SDK, including secret management, JWT authentication, and secure handshake protocols.

## Overview

This module is organized into several key components:

- **Secret Management**: Secure handling, storage, and rotation of sensitive configuration data
- **JWT Authentication**: Bearer token validation and middleware for Axum applications  
- **Handshake Protocol**: Secure initialization communication between modules and orchestrator
- **Redaction & Logging**: Automatic secret redaction in logs and tracing

## Components

### [`handshake.rs`](./handshake.rs)
Implements the initial handshake protocol for module-orchestrator communication. Provides `read_init()` function that carefully reads the orchestrator's initialization message from stdin without consuming additional data.

### [`secret_client/`](./secret_client/)
Client-side secret management functionality including:
- `SecretClient` for communicating with the orchestrator's secret provider
- Caching and rotation handling
- Automatic secret redaction in logs
- JSON-based IPC communication

### [`secret_provider/`](./secret_provider/)
Server-side secret provider implementations with pluggable backends:
- Environment variable provider
- File-based provider (TOML format)
- In-memory provider for testing
- Chained provider for fallback scenarios
- Metrics and tracing support

### [`secrets/`](./secrets/)
High-level secret management utilities and typed secret wrappers:
- Module secret client initialization
- Typed secret parsing (`Secret<T>`)
- Secret rotation subscription helpers

### [`jwt_auth/`](./jwt_auth/) *(feature-gated)*
JWT authentication middleware for Axum applications:
- Bearer token validation
- Claims extraction and injection
- Proxy adapter for remote JWT validation
- Router extension traits

## Key Features

### Automatic Secret Redaction
All secret values are automatically registered for redaction in logs using the `register_for_redaction()` function and `safe_log!` macros.

### Type-Safe Secret Handling
The `Secret<T>` wrapper provides compile-time safety for sensitive data with automatic redaction in debug output.

### Pluggable Secret Sources
Multiple secret provider implementations allow flexibility in how secrets are stored and retrieved.

### JWT Middleware Integration
Seamless integration with Axum routers for JWT-based authentication with support for both local and remote validation.

### IPC Protocol Support
Standardized JSON-line protocol for secure communication between modules and the orchestrator.

## Usage Examples

### Basic Secret Retrieval
```rust
use pywatt_sdk::security::secrets::get_secret;

let client = get_module_secret_client(&api_url, &module_id).await?;
let db_url = get_secret(&client, "DATABASE_URL").await?;
```

### JWT Authentication
```rust
use pywatt_sdk::security::jwt_auth::{JwtAuthLayer, RouterJwtExt};

let app = Router::new()
    .route("/protected", get(handler))
    .with_jwt::<MyClaims>("secret-key".to_string());
```

### Typed Secrets
```rust
use pywatt_sdk::security::secrets::typed_secret::get_typed_secret;

let port: Secret<u16> = get_typed_secret(&client, "PORT").await?;
let api_key: Secret<String> = get_typed_secret(&client, "API_KEY").await?;
```

## Feature Flags

- `jwt_auth`: Enables JWT authentication middleware
- `metrics`: Enables Prometheus metrics collection for secret operations

## Security Considerations

- All secret values are automatically redacted in logs and debug output
- Secrets are stored using the `secrecy` crate's `SecretString` type
- JWT secrets are registered for redaction upon middleware initialization
- File-based secrets support secure watching for rotation events
- IPC communication uses single-line JSON to prevent protocol corruption 