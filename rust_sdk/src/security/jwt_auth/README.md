# JWT Authentication

The JWT authentication module provides comprehensive JWT Bearer token validation middleware for Axum applications. It supports both local validation and remote proxy validation, with automatic secret redaction and flexible claims handling.

## Architecture

The module implements Tower middleware layers that intercept HTTP requests, validate JWT tokens from `Authorization: Bearer <token>` headers, and inject decoded claims into request extensions. It supports both strongly-typed and dynamic claims handling.

## Core Components

### [`mod.rs`](./mod.rs)
Main module providing public API and router integration:

#### RouterJwtExt Trait
Extension trait for Axum Router to easily apply JWT authentication:
```rust
pub trait RouterJwtExt {
    fn with_jwt<T>(self, secret_key: String) -> Self
    where
        T: serde::de::DeserializeOwned + Send + Sync + Clone + 'static;
}
```

#### Type Aliases
- `JwtAuthLayer<T>` - Backward compatibility alias for `JwtAuthenticationLayer<T>`
- Default claims type is `serde_json::Value` for dynamic handling

#### Module Detection
- `is_running_as_module()` - Detects if running as PyWatt module via `PYWATT_MODULE_ID` env var
- Determines whether to use local or proxy validation

### [`middleware.rs`](./middleware.rs)
Core middleware implementation with Tower integration:

#### JwtAuthenticationLayer
Main middleware layer providing JWT validation:
```rust
pub struct JwtAuthenticationLayer<T = serde_json::Value> {
    secret_key: String,
    _marker: PhantomData<T>,
}
```

**Features:**
- Generic claims type support with default `serde_json::Value`
- Automatic secret registration for redaction
- Custom validation rules via `with_validation()`
- HS256 algorithm by default with disabled expiration checking

#### JwtAuthService
Tower service that performs the actual JWT validation:
```rust
pub struct JwtAuthService<S, T = serde_json::Value> {
    inner: S,
    secret_key: String,
    validation: Validation,
    _marker: PhantomData<T>,
    #[cfg(feature = "ipc")]
    proxy_service: Option<Arc<Mutex<Option<JwtProxyService>>>>,
}
```

**Validation Logic:**
1. Extract `Authorization: Bearer <token>` header
2. Determine validation method (local vs. proxy)
3. Decode and validate JWT token
4. Inject claims into request extensions
5. Forward request to inner service

#### Error Responses
- Missing header: `401 Unauthorized` with JSON error
- Invalid token: `401 Unauthorized` with detailed error message
- Proxy errors: `500 Internal Server Error` for service issues

### [`error.rs`](./error.rs)
Comprehensive error handling for JWT operations:

```rust
pub enum JwtAuthError {
    InvalidToken(String),           // Token validation failed
    MissingHeader,                  // Authorization header missing
    MalformedToken,                 // Token format invalid
    VerificationFailed(String),     // Signature/claims verification failed
    PayloadError(String),           // Claims processing error
    JwtError(jsonwebtoken::errors::Error), // Library errors
}
```

### [`proxy_adapter.rs`](./proxy_adapter.rs) *(feature-gated)*
Remote JWT validation service adapter for module environments:

#### JwtProxyService
Client for communicating with orchestrator's JWT service:
```rust
pub struct JwtProxyService {
    connection_id: String,
}
```

**Operations:**
- `connect()` - Establish connection to JWT service
- `validate_token<T>()` - Validate token and return typed claims
- `generate_token<T>()` - Generate token from claims
- `close()` - Close service connection

#### IPC Protocol
Uses standardized service operation protocol:
- `ServiceRequest` - Initial connection request
- `ServiceOperation` - Token validation/generation operations
- `ServiceOperationResult` - Operation responses

#### Helper Functions
- `validate_token_proxy<T>()` - Convenience wrapper for validation
- `generate_token_proxy<T>()` - Convenience wrapper for generation

### [`compat.rs`](./compat.rs)
Backward compatibility layer for deprecated types:
- All exports marked with `#[deprecated]` attributes
- Provides migration path from old API to new structure
- Maintains API compatibility during transition period

### [`tests.rs`](./tests.rs)
Comprehensive test suite covering all functionality:

#### Test Coverage
- Missing/invalid authorization headers
- Valid token validation and claims extraction
- Custom validation rules (audience, expiration)
- Invalid signatures and wrong algorithms
- Optional claims handling
- Secret redaction verification
- Backward compatibility aliases

#### Test Utilities
- `TestClaims` struct for strongly-typed testing
- Token generation with `jsonwebtoken` crate
- Mock HTTP requests with various scenarios

## Usage Patterns

### Basic JWT Authentication
```rust
use axum::{Router, routing::get, extract::Extension};
use pywatt_sdk::security::jwt_auth::{JwtAuthLayer, RouterJwtExt};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
struct MyClaims {
    sub: String,
    role: String,
    exp: usize,
}

// Method 1: Using extension trait
let app = Router::new()
    .route("/protected", get(protected_handler))
    .with_jwt::<MyClaims>("my-secret-key".to_string());

// Method 2: Using layer directly
let app = Router::new()
    .route("/protected", get(protected_handler))
    .layer(JwtAuthLayer::<MyClaims>::new("my-secret-key".to_string()));

async fn protected_handler(
    Extension(claims): Extension<MyClaims>
) -> String {
    format!("Hello, {}! Role: {}", claims.sub, claims.role)
}
```

### Dynamic Claims Handling
```rust
use serde_json::Value;

let app = Router::new()
    .route("/api", get(api_handler))
    .with_jwt::<Value>("secret".to_string());

async fn api_handler(
    Extension(claims): Extension<Value>
) -> String {
    let user_id = claims["sub"].as_str().unwrap_or("unknown");
    format!("User ID: {}", user_id)
}
```

### Custom Validation Rules
```rust
use jsonwebtoken::{Algorithm, Validation};

let mut validation = Validation::new(Algorithm::HS256);
validation.set_required_spec_claims(&["aud", "exp"]);
validation.set_audience(&["my-app"]);
validation.validate_exp = true;

let layer = JwtAuthLayer::<MyClaims>::new("secret".to_string())
    .with_validation(validation);

let app = Router::new()
    .route("/strict", get(handler))
    .layer(layer);
```

### Module Environment (Proxy Validation)
When running as a PyWatt module (detected via `PYWATT_MODULE_ID` environment variable), the middleware automatically uses proxy validation:

```rust
// Same API, but validation happens via orchestrator
let app = Router::new()
    .route("/protected", get(handler))
    .with_jwt::<MyClaims>("secret".to_string()); // Secret may be ignored in proxy mode
```

## Security Features

### Automatic Secret Redaction
JWT secrets are automatically registered for redaction:
```rust
let layer = JwtAuthLayer::new("super-secret-key".to_string());
// "super-secret-key" is now redacted in all logs
```

### Memory Safety
- Secrets stored using `secrecy` crate patterns
- No accidental exposure in debug output
- Automatic cleanup on drop

### Validation Security
- Configurable algorithm validation (default: HS256)
- Optional expiration checking
- Audience validation support
- Custom claim requirements

### Error Handling
- No secret leakage in error messages
- Detailed error categorization for debugging
- Consistent HTTP status codes

## Configuration

### Environment Variables
- `PYWATT_MODULE_ID` - Enables proxy validation mode when set

### Validation Options
```rust
let mut validation = Validation::new(Algorithm::HS256);
validation.validate_exp = true;           // Check expiration
validation.validate_nbf = true;           // Check not-before
validation.set_audience(&["my-app"]);     // Require specific audience
validation.set_issuer(&["my-issuer"]);    // Require specific issuer
validation.set_required_spec_claims(&["aud", "exp"]); // Required claims
```

## Feature Flags

### `ipc` Feature
Enables proxy adapter functionality:
- `JwtProxyService` and related types
- Remote validation via orchestrator
- Service operation protocol support

Without this feature, proxy validation will return errors in module environments.

## Error Handling

### HTTP Error Responses
All authentication failures return appropriate HTTP status codes:

```json
// Missing header (401)
{"error": "Missing Authorization header"}

// Invalid token (401)
{"error": "Unauthorized: InvalidSignature"}

// Proxy service error (500)
{"error": "JWT proxy service not initialized"}
```

### Error Categories
- **Client Errors (4xx)**: Missing/invalid tokens, malformed headers
- **Server Errors (5xx)**: Proxy service issues, configuration problems

## Testing

### Unit Tests
Comprehensive test coverage including:
- Valid/invalid token scenarios
- Custom validation rules
- Error conditions
- Secret redaction verification
- Backward compatibility

### Integration Testing
```rust
use axum_test::TestServer;

let app = Router::new()
    .route("/test", get(|| async { "ok" }))
    .with_jwt::<TestClaims>("test-secret".to_string());

let server = TestServer::new(app).unwrap();

// Test with valid token
let token = create_test_token("test-secret", &claims);
let response = server
    .get("/test")
    .add_header("Authorization", format!("Bearer {}", token))
    .await;
assert_eq!(response.status_code(), 200);
```

### Mock Proxy Service
For testing proxy validation scenarios:
```rust
// Mock orchestrator responses
let mock_service = MockJwtProxyService::new();
mock_service.expect_validate()
    .returning(|_| Ok(test_claims));
```

## Performance Considerations

### Local Validation
- Fast HMAC verification using `jsonwebtoken` crate
- No network overhead
- Minimal CPU impact for HS256

### Proxy Validation
- Network round-trip to orchestrator
- Connection pooling for efficiency
- Async operation to prevent blocking

### Caching
- No built-in token caching (stateless validation)
- Claims injected per-request
- Minimal memory overhead

## Migration Guide

### From Deprecated API
```rust
// Old (deprecated)
use pywatt_sdk::jwt_auth_compat::JwtAuthenticationLayer;

// New
use pywatt_sdk::security::jwt_auth::JwtAuthLayer;
```

### Version Compatibility
- All deprecated types remain functional
- Gradual migration supported
- No breaking changes in current version 