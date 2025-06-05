---
trigger: model_decision
description: This rule set guides the AI in generating code for the PyWatt-Rust project, a Rust rewrite of a Python FastAPI/Socket.IO chat backend.
globs: 
---
# Rust Code Completion Rules

<context>
This rule set guides the AI in generating code for the PyWatt-Rust project, a Rust rewrite of a Python FastAPI/Socket.IO chat backend.
</context>

<rules>

## Type System and Safety
- Use Rust's strong type system instead of stringly-typed approaches
- Implement proper error types and use Result<T, E> for error handling
- Prefer Option<T> over nullable types
- Use proper lifetimes and ownership semantics

## Naming Conventions
- Use `snake_case` for functions, methods, variables, fields, modules
- Use `CamelCase` for types, traits, enums
- Use `SCREAMING_SNAKE_CASE` for statics and constants
- Prefix unsafe functions with `unsafe_`

## Documentation
- Add doc comments (`///`) for all public API interfaces
- Include examples in doc comments for complex functions
- Document error conditions and panics
- Add module-level documentation with `//!`

## Error Handling
- Use the `?` operator with `AppResult<T>` for error propagation
- Map external errors to internal error types
- Provide context in error messages
- Handle all Result and Option cases explicitly

## Async Code
- Use async/await consistently throughout the codebase
- Mark functions with async when they contain awaited operations
- Use proper executor (Tokio) for blocking operations
- Handle cancellation and timeouts appropriately

</rules>

<templates>

## Handler Template
```rust
pub async fn handler_name(
    State(state): State<AppState>,
    // Other extractors (Json, Path, etc.)
) -> AppResult<impl IntoResponse> {
    // Validate inputs
    let validated = input.validate()?;
    
    // Call service method
    let result = state.some_service.some_method(validated).await?;
    
    // Return response
    Ok((StatusCode::OK, Json(result)))
}
```

## Service Template
```rust
pub struct SomeService {
    db_pool: PgPool,
    // Other dependencies
}
impl SomeService {
    pub fn new(db_pool: PgPool) -> Self {
        Self { db_pool }
    }
    
    #[tracing::instrument(skip(self))]
    pub async fn some_method(&self, args: Args) -> AppResult<ReturnType> {
        // Implementation
        Ok(result)
    }
}
```

## Model Template
```rust
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct ModelName {
    pub id: Uuid,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl ModelName {
    // Model methods
}
```

## Schema Template
```rust
#[derive(Debug, Serialize, Deserialize, Validate)]
pub struct RequestSchema {
    #[validate(length(min = 3, max = 100))]
    pub field: String,
}

#[derive(Debug, Serialize)]
pub struct ResponseSchema {
    pub id: Uuid,
    pub created_at: DateTime<Utc>,
}
```
</templates>

<patterns>

## Database Operations
- Use `sqlx::query_as!` for type-safe queries
- Use transactions for multi-step operations
- Handle connection pooling properly
- Implement proper error mapping for database errors

## Authentication
- Use JWT for stateless authentication
- Hash passwords with Argon2
- Implement proper role-based access control
- Use secure session management

## Testing
- Write unit tests for business logic
- Use integration tests for API endpoints
- Mock external services in tests
- Use test fixtures for common setup

</patterns>

<examples>

## Database Query Example
```rust
let records = sqlx::query_as!(
    ModelType,
    "SELECT * FROM table WHERE condition = $1",
    parameter
)
.fetch_all(&pool)
.await?;
```

## Transaction Example
```rust
let mut tx = pool.begin().await?;

// Multiple operations
let result = sqlx::query_as!(/*...*/)
    .fetch_one(&mut *tx)
    .await?;

tx.commit().await?;
```

## Test Example
```rust
#[tokio::test]
async fn test_some_functionality() {
    // Arrange
    let service = setup_service().await;
    
    // Act
    let result = service.some_method(args).await;
    
    // Assert
    assert!(result.is_ok());
}
```

</examples> 
