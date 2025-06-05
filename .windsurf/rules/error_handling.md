---
trigger: model_decision
description: The error handling system provides a comprehensive, type-safe approach to error management across the application. It defines a central `AppError` type that encompasses all possible error cases, provides meaningful error messages, and maps errors to appropriate HTTP responses.
globs: 
---
# Error Handling System

## Purpose
The error handling system provides a comprehensive, type-safe approach to error management across the application. It defines a central `AppError` type that encompasses all possible error cases, provides meaningful error messages, and maps errors to appropriate HTTP responses.

## Key Types & Structures
```rust
#[derive(Error, Debug)]
pub enum AppError {
    // Authentication & Authorization
    #[error("Authentication failed: {0}")]
    AuthError(String),
    #[error("Invalid credentials")]
    InvalidCredentials,
    #[error("Unauthorized")]
    Unauthorized,
    #[error("Forbidden: {0}")]
    Forbidden(String),
    
    // User Management
    #[error("User already exists")]
    UserAlreadyExists,
    #[error("User not found")]
    UserNotFound,
    #[error("User is not verified")]
    UserNotVerified,
    
    // Token & Session Management
    #[error("Token has expired")]
    TokenExpired,
    #[error("Token is invalid")]
    TokenInvalid,
    #[error("Session expired")]
    SessionExpired,
    #[error("Session not found")]
    SessionNotFound,
    
    // Infrastructure
    #[error("Database error: {0}")]
    DatabaseError(#[from] sqlx::Error),
    #[error("Redis error: {0}")]
    RedisError(String),
    #[error("Migration error: {0}")]
    MigrationError(String),
    
    // Security
    #[error("Too many requests, please try again later")]
    RateLimited,
    #[error("Account is locked until {locked_until}")]
    AccountLocked { locked_until: DateTime<Utc> },
    
    // OAuth & Authentication
    #[error("OAuth provider {0} is not configured or not supported")]
    OAuthProviderNotConfigured(String),
    #[error("Two-factor authentication code required")]
    TotpRequired { user_id: Uuid },
    
    // LLM & AI
    #[error("LLM API error: {0}")]
    LlmApiError(String),
    #[error("LLM configuration error: {0}")]
    LlmConfigError(String),
    
    // Generic Errors
    #[error("Internal server error: {0}")]
    InternalServerError(#[from] anyhow::Error),
    #[error("Bad request: {0}")]
    BadRequest(String),
    #[error("Not Found: {0}")]
    NotFound(String),
}

// Type alias for Results using AppError
pub type AppResult<T> = Result<T, AppError>;
```

## Design Patterns
### Error Type Hierarchy
- **Purpose**: Organizes errors into logical categories
- **Implementation**: Uses `thiserror` for deriving error implementations
- **Usage**: Errors are grouped by domain (auth, database, etc.)

### Error Conversion
- **Purpose**: Converts between error types seamlessly
- **Implementation**: Uses `From` trait implementations
- **Usage**: External errors are converted to `AppError` automatically

### HTTP Response Mapping
- **Purpose**: Maps errors to appropriate HTTP responses
- **Implementation**: Implements `IntoResponse` for `AppError`
- **Usage**: Errors are automatically converted to HTTP responses

## Error Handling
### Error Propagation
```rust
impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, error_message) = match self {
            AppError::NotFound(_) => (StatusCode::NOT_FOUND, ...),
            AppError::Unauthorized => (StatusCode::UNAUTHORIZED, ...),
            AppError::Forbidden(_) => (StatusCode::FORBIDDEN, ...),
            // ... other mappings
        };
        
        let body = Json(json!({
            "error": error_message,
            "status": status.as_u16(),
            "code": error_code,
        }));

        (status, body).into_response()
    }
}
```

### Error Conversion Examples
```rust
// Converting from external errors
impl From<RedisError> for AppError {
    fn from(err: RedisError) -> Self {
        AppError::RedisError(err.to_string())
    }
}

impl From<sqlx::Error> for AppError {
    fn from(err: sqlx::Error) -> Self {
        AppError::DatabaseError(err)
    }
}
```

## Usage Examples
```rust
// Using Result type alias
async fn create_user(user: NewUser) -> AppResult<User> {
    if user_exists(&user.email).await? {
        return Err(AppError::UserAlreadyExists);
    }
    
    let user = db::insert_user(user).await?;
    Ok(user)
}

// Error propagation in handlers
async fn handler(
    State(db): State<PgPool>,
    Json(payload): Json<LoginPayload>,
) -> Result<impl IntoResponse, AppError> {
    let user = db.get_user(&payload.email)
        .await
        .map_err(AppError::DatabaseError)?;
        
    if !user.is_verified {
        return Err(AppError::UserNotVerified);
    }
    
    Ok(Json(user))
}
```

## Testing Approach
### Unit Tests
```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[tokio::test]
    async fn test_error_responses() {
        let err = AppError::NotFound("User not found".to_string());
        let res = err.into_response();
        assert_eq!(res.status(), StatusCode::NOT_FOUND);
        
        // Test response body
        let body = hyper::body::to_bytes(res.into_body()).await.unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert!(json["error"].as_str().unwrap().contains("not found"));
    }
}
```

### Integration Tests
- Test error propagation through service layers
- Validate HTTP response codes and bodies
- Test error conversion from external errors

## Dependencies
### Internal Dependencies
- `models`: Data structures used in errors
- `middleware`: Rate limiting and auth errors

### External Dependencies
- `thiserror`: Error trait derivation
- `axum`: HTTP response types
- `serde_json`: JSON serialization
- `tracing`: Error logging

## Notes & Best Practices
### Performance Considerations
- Error types are kept small and efficient
- Error messages are allocated only when needed
- Stack traces are captured only in development

### Security Considerations
- Sensitive information is never exposed in errors
- Authentication errors are generic
- Rate limiting prevents brute force attacks

### Rust Idioms
- Use of `#[from]` attribute for conversions
- Error type organization with `thiserror`
- Result type aliases for convenience

### Maintenance Notes
- Keep error messages user-friendly
- Document new error types
- Consider error code stability
- Group related errors together

## Related Components
- `middleware/error.rs`: Error handling middleware
- `handlers/*`: Error usage in request handlers
- `services/*`: Service-level error handling
- `logging/*`: Error logging configuration
