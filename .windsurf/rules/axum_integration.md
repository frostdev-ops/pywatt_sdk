---
trigger: model_decision
description: This rule documents patterns and practices for integrating with the Axum web framework in the PyWatt-Rust project.
globs: 
---
# Axum Integration

<context>
This rule documents patterns and practices for integrating with the Axum web framework in the PyWatt-Rust project.
</context>

<rules>

## Response Types
- Always use explicit response types that implement `IntoResponse`
- Prefer using the tuple form `(StatusCode, Json<T>)` for JSON responses
- For empty responses, use `StatusCode` directly
- Import `IntoResponse` from `axum` directly, not from an intermediate module

## Route Handlers
- Use the `#[axum::debug_handler]` attribute for complex handlers during development
- Separate route definitions from handler implementations
- Group routes logically using `Router::new()` and `.route()` calls
- Use state extraction via `State(state)` as the first parameter

## Error Handling
- Use `AppResult<impl IntoResponse>` as the return type for handlers
- The `?` operator will convert errors to the appropriate HTTP responses
- Custom errors should implement `IntoResponse` through the `AppError` type

## Extractors
- Authentication data comes from `AuthenticatedUser` extractor
- Query parameters use the `Query<T>` extractor
- JSON request bodies use the `Json<T>` extractor
- Path parameters use the `Path<T>` extractor

## Middleware
- Authentication middleware is applied at the router level
- Other common middleware includes:
  - CORS
  - Compression
  - Request tracing
  - Rate limiting

</rules>

<patterns>

## JSON Response Pattern
```rust
// Return a JSON response with status code
async fn handler() -> AppResult<impl IntoResponse> {
    let data = get_data().await?;
    Ok((StatusCode::OK, Json(data)))
}
```

## Empty Response Pattern
```rust
// Return an empty response with status code
async fn handler() -> AppResult<impl IntoResponse> {
    perform_action().await?;
    Ok(StatusCode::NO_CONTENT)
}
```

## Query Parameter Extraction
```rust
// Extract and use query parameters
async fn handler(
    Query(params): Query<ListParams>,
) -> AppResult<impl IntoResponse> {
    let data = get_data_with_params(params).await?;
    Ok((StatusCode::OK, Json(data)))
}
```

## Path Parameter Extraction
```rust
// Extract and use path parameters
async fn handler(
    Path(id): Path<Uuid>,
) -> AppResult<impl IntoResponse> {
    let item = get_item_by_id(id).await?;
    Ok((StatusCode::OK, Json(item)))
}
```

## Custom Extractor Implementation
```rust
// Implement a custom extractor with the correct lifetimes
#[async_trait]
impl<S> FromRequestParts<S> for MyCustomExtractor
where
    S: Send + Sync,
{
    type Rejection = AppError;

    // Notice the different lifetime parameters for parts and state
    async fn from_request_parts<'a, 'b>(
        parts: &'a mut Parts, 
        state: &'b S
    ) -> Result<Self, Self::Rejection> {
        // Implementation details
        // ...
    }
}
```

</patterns>

<examples>

## Complete Handler Example
```rust
/// Get a resource by ID
async fn get_resource(
    State(state): State<AppState>,
    auth_user: AuthenticatedUser,
    Path(resource_id): Path<Uuid>,
) -> AppResult<impl IntoResponse> {
    // Check permission
    if !state.permission_service.can_view_resource(auth_user.user_id, resource_id).await? {
        return Err(AppError::Forbidden("No permission to view this resource".to_string()));
    }
    
    // Retrieve the resource
    let resource = state.resource_service.get_by_id(resource_id).await?;
    
    // Return the resource
    Ok((StatusCode::OK, Json(resource)))
}
```

## Route Definition Example
```rust
/// Define routes for resource management
pub fn resource_routes(state: AppState) -> Router {
    Router::new()
        .route("/", post(create_resource))
        .route("/", get(list_resources))
        .route("/:id", get(get_resource))
        .route("/:id", put(update_resource))
        .route("/:id", delete(delete_resource))
        .with_state(state)
}
```

## DTOs for Request/Response Example
```rust
// Data Transfer Objects

#[derive(Debug, Deserialize)]
struct CreateResourceDto {
    name: String,
    description: Option<String>,
    category: String,
}

#[derive(Debug, Serialize)]
struct ResourceResponseDto {
    id: Uuid,
    name: String,
    description: Option<String>,
    category: String,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}
```

</examples>

<troubleshooting>

## Common Errors
- "the trait bound `(StatusCode, Json<T>): IntoResponse` is not satisfied"
  - Cause: Mixing different versions of dependencies that include Axum
  - Solution 1: Make sure to import `IntoResponse` directly from `axum`
  - Solution 2: Use explicit response types that match your Axum version

- "expected a value of type `(StatusCode, axum::Json<T>)`, found `(http::StatusCode, axum::Json<T>)`"
  - Cause: Mixing imports from `http` and `axum`
  - Solution: Import `StatusCode` from the same module as `Json`

- "handler failed with error: request data error"
  - Cause: JSON deserialization failed, usually from missing fields or wrong types
  - Solution: Check request body format, make sure DTO matches expected format

## Debugging Tips
- Use `#[axum::debug_handler]` to get better error messages during development
- Check request/response format with logging middleware
- Make sure error types implement the correct traits for Axum integration
- Use explicit types rather than `impl Trait` during debugging

</troubleshooting>
