---
trigger: model_decision
description: The middleware system provides a layered approach to request processing, handling cross-cutting concerns such as authentication, authorization, rate limiting, security headers, and CORS. It uses Tower's middleware stack to compose these concerns in a modular way.
globs: 
---
# Middleware System

## Purpose
The middleware system provides a layered approach to request processing, handling cross-cutting concerns such as authentication, authorization, rate limiting, security headers, and CORS. It uses Tower's middleware stack to compose these concerns in a modular way.

## Key Types & Structures
```rust
// Authentication Middleware
pub async fn auth_guard<B>(
    claims: Option<Claims>,
    request: Request<B>,
    next: Next<B>,
) -> Result<Response, AppError>;

// Rate Limiting
pub struct RateLimitConfig {
    pub requests_per_minute: u32,
    pub window_seconds: u64,
}

// Session Management
pub struct SessionConfig {
    pub cookie_name: String,
    pub max_age: Duration,
    pub secure: bool,
}

// Security Headers
pub struct SecurityConfig {
    pub csp_enabled: bool,
    pub xss_protection: bool,
    pub custom_headers: HashMap<String, String>,
}

// CORS Configuration
pub struct CorsConfig {
    pub allowed_origins: Vec<String>,
    pub allowed_methods: Vec<Method>,
    pub allowed_headers: Vec<HeaderName>,
    pub allow_credentials: bool,
    pub max_age: Duration,
}
```

## Design Patterns
### Middleware Stack
- **Purpose**: Composes request processing layers
- **Implementation**: Uses Tower middleware traits
- **Usage**: Applied in order of definition

### Extractor Pattern
- **Purpose**: Type-safe access to request data
- **Implementation**: Custom extractors for auth/session
- **Usage**: Used in route handlers

### Guard Pattern
- **Purpose**: Protects routes with conditions
- **Implementation**: Async middleware functions
- **Usage**: Authentication and authorization

## Middleware Categories
### Authentication & Authorization
```rust
// JWT Authentication
pub async fn auth_guard<B>(
    claims: Option<Claims>,
    request: Request<B>,
    next: Next<B>,
) -> Result<Response, AppError> {
    let claims = claims.ok_or(AppError::Unauthorized)?;
    request.extensions_mut().insert(claims);
    Ok(next.run(request).await)
}

// API Key Authentication
pub async fn api_key_auth<B>(
    TypedHeader(api_key): TypedHeader<ApiKey>,
    State(state): State<AppState>,
    request: Request<B>,
    next: Next<B>,
) -> Result<Response, AppError> {
    let api_key = state.api_key_service.validate_key(&api_key).await?;
    request.extensions_mut().insert(api_key);
    Ok(next.run(request).await)
}

// Permission Check
pub async fn require_permission<B>(
    claims: Claims,
    permission: &str,
) -> Result<(), AppError> {
    if !claims.permissions.contains(permission) {
        return Err(AppError::Forbidden("Insufficient permissions".into()));
    }
    Ok(())
}
```

### Security
```rust
// Rate Limiting
pub async fn rate_limit<B>(
    State(state): State<AppState>,
    request: Request<B>,
    next: Next<B>,
) -> Result<Response, AppError> {
    let key = extract_rate_limit_key(&request)?;
    state.rate_limiter.check_rate_limit(&key).await?;
    Ok(next.run(request).await)
}

// Security Headers
pub fn security_headers_layer() -> impl Layer<BoxService<Request, Response>> {
    tower::ServiceBuilder::new()
        .layer(SetResponseHeader::if_not_present(
            header::X_FRAME_OPTIONS,
            HeaderValue::from_static("DENY"),
        ))
        // ... other security headers
}
```

### Session Management
```rust
// Session Authentication
pub async fn session_auth<B>(
    cookies: Cookies,
    State(state): State<AppState>,
    request: Request<B>,
    next: Next<B>,
) -> Result<Response, AppError> {
    let session = state.session_service.validate_session(cookies).await?;
    request.extensions_mut().insert(session);
    Ok(next.run(request).await)
}

// Session Refresh
pub async fn refresh_session<B>(
    session: Session,
    response: Response,
) -> Result<Response, AppError> {
    if session.needs_refresh() {
        session.refresh().await?;
        // Update session cookie
    }
    Ok(response)
}
```

## Usage Examples
```rust
// Applying Middleware Stack
let app = Router::new()
    .route("/api/v1/*", api_routes())
    .layer(cors_layer())
    .layer(security_headers_layer())
    .layer(rate_limit_layer())
    .layer(auth_layer());

// Protected Route with Multiple Guards
async fn admin_action(
    claims: Claims,
    session: Session,
    State(state): State<AppState>,
) -> Result<impl IntoResponse, AppError> {
    require_permission(&claims, "admin")?;
    require_active_session(&session)?;
    // Handler logic...
}
```

## Testing Approach
### Unit Tests
```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[tokio::test]
    async fn test_auth_guard() {
        let app = Router::new()
            .route("/", get(handler))
            .layer(auth_guard);
            
        let response = app
            .oneshot(
                Request::builder()
                    .header("Authorization", "Bearer valid_token")
                    .uri("/")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
            
        assert_eq!(response.status(), StatusCode::OK);
    }
}
```

### Integration Tests
- Test middleware composition
- Validate security headers
- Test rate limiting behavior
- Session management flows

## Dependencies
### Internal Dependencies
- `services/*`: Business logic
- `errors.rs`: Error handling
- `models/*`: Data types
- `state.rs`: Application state

### External Dependencies
- `tower`: Middleware framework
- `tower-http`: HTTP middleware
- `axum`: Web framework
- `headers`: HTTP headers

## Notes & Best Practices
### Performance Considerations
- Efficient rate limiting
- Session caching
- Header optimization
- Middleware ordering

### Security Considerations
- Secure session handling
- CSRF protection
- XSS prevention
- Rate limit tuning

### Rust Idioms
- Type-safe middleware
- Error propagation
- Async patterns
- Extension traits

### Maintenance Notes
- Document middleware order
- Monitor rate limits
- Update security headers
- Session cleanup

## Related Components
- `routes/*`: Route handlers
- `services/*`: Business logic
- `models/*`: Data types
- `errors.rs`: Error handling
