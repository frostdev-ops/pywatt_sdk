---
trigger: always_on
description: 
globs: 
---
# Cursor Rule: jwt_middleware

<context>
This rule documents the `JwtAuthLayer` and `RouterJwtExt` middleware provided by the `jwt_auth` feature in `pywatt_sdk`. It enables easy JWT Bearer token validation on Axum routers.
</context>

<rules>

## Purpose
Provide a simple Axum middleware layer (`JwtAuthLayer`) that validates incoming `Authorization: Bearer <token>` headers using an HMAC secret.

## Key Types & Structures
```rust
/// Tower layer to enforce JWT validation
pub struct JwtAuthLayer {
    secret_key: String,
}

/// Tower service that performs JWT decoding and injects claims into request extensions
pub struct JwtAuthService<S> {
    inner: S,
    secret_key: String,
}

/// Extension trait for applying JWT validation to `Router`
pub trait RouterJwtExt {
    fn with_jwt(self, secret_key: String) -> Self;
}
```

## Design Patterns
### Tower Layer/Service Pattern
- **Purpose**: Wrap an existing service (the router) with extra pre-processing logic (JWT validation).
- **Implementation**: `JwtAuthLayer` implements `tower::Layer`, producing a `JwtAuthService`; `JwtAuthService` implements `tower::Service<Request<B>>`.
- **Usage**: `.layer(JwtAuthLayer::new(secret))` or the shorthand `.with_jwt(secret)` on a `Router`.

## Error Handling
- Missing or malformed `Authorization` header → responds `401 Unauthorized` with JSON `{ "error": "Missing Authorization header" }`.
- JWT decode error (invalid signature, expired, wrong algorithm, etc.) → responds `401 Unauthorized` with JSON `{ "error": "Unauthorized: <error>" }`.
- All errors are mapped to `axum::response::Response` via `IntoResponse`.

## Usage Examples
```rust,no_run
use axum::{routing::get, Router, extract::Extension};
use pywatt_sdk::ext::RouterJwtExt;

// Assume `secret` is fetched via `get_secret` and unwrapped
let secret = "my_hmac_secret".to_string();
let app = Router::new()
    .route("/protected", get(handler))
    .with_jwt(secret);
```

Inside your handler, you can extract the decoded claims:
```rust
async fn handler(
    Extension(claims): Extension<serde_json::Value>,
) -> String {
    format!("Hello, {}!", claims["sub"].as_str().unwrap_or("user"))
}
```

## Required Components
- HMAC secret string passed to `JwtAuthLayer::new(secret)`.
- `jsonwebtoken` crate (via `jwt_auth` feature).

## Notes & Best Practices
- Register the raw secret for redaction using `secret_client::register_for_redaction` to avoid leaking secrets in logs.
- Default JWT algorithm is HS256; adjust `Validation` if you need different algorithms.
- Insert typed claims into `Request::extensions()`; you may wrap them in a strongly-typed struct for your application.

## Related Components
- `module_secret_management` cursor rule for fetching secrets with redaction.
- `middleware` rule for general Tower patterns.
- `pywatt_module_utils` for IPC and secret utilities.
</rules>
