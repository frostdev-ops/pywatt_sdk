---
trigger: always_on
description: 
globs: 
---
# Component: AppStateBuilder

## Component Type
SDK Feature / Cursor Rule

## File Path
`.cursor/rules/app_state_builder.mdc`

## Purpose
The AppStateBuilder provides a fluent builder API for creating and configuring AppState instances in PyWatt modules. It simplifies the creation of application state with improved ergonomics and readability.

## Key Features
1. **Fluent API**: Chain method calls for a more readable state construction
2. **Optional Components**: Build state incrementally with optional components
3. **Error Handling**: Both panicking and result-returning build methods
4. **Type Safety**: Maintains strong typing of the custom user state

## Usage Examples
```rust
// Basic usage with custom state
#[derive(Clone)]
struct MyAppState {
    db_pool: PgPool,
    cache: Arc<Cache>,
}

let custom_state = MyAppState {
    db_pool: pool.clone(),
    cache: Arc::new(Cache::new()),
};

let state = AppState::builder()
    .with_module_id("my-module".to_string())
    .with_orchestrator_api("http://localhost:9900".to_string())
    .with_secret_client(client.clone())
    .with_custom(custom_state)
    .build();

// Using with error handling
let state_result = AppState::builder()
    .with_module_id("my-module".to_string())
    .with_orchestrator_api("http://localhost:9900".to_string())
    .with_secret_client(client.clone())
    .with_custom(custom_state)
    .try_build();

match state_result {
    Ok(state) => println!("State created successfully"),
    Err(err) => eprintln!("Error creating state: {}", err),
}
```

## Implementation Notes
- The builder is conditionally compiled with the `builder` feature flag
- Uses the builder pattern with method chaining for better ergonomics
- Each setter method takes ownership and returns `self` for chaining
- Final `build` method consumes the builder and returns the constructed state

## Required Components
The following components are required to build a valid AppState:
1. `module_id`: The unique identifier for the module
2. `orchestrator_api`: The URL of the orchestrator API
3. `secret_client`: The client for accessing secrets
4. `user_state`: Custom application state

## Error Handling
- The `build` method will panic if any required component is missing
- For safer construction, use `try_build` which returns a `Result<AppState<T>, String>`

## Feature Flag
The AppStateBuilder is enabled with the `builder` feature flag:

```toml
[dependencies]
pywatt_sdk = { version = "0.1.0", features = ["builder"] }
```

## Best Practices
1. Always provide all required components before calling `build`
2. Use `try_build` in production code to handle errors gracefully
3. Keep custom state (`user_state`) as small and focused as possible
4. Use `Arc` for sharing large resources in the custom state

## Related Components
- `AppState`: The core state structure built by the builder
- `Module macro`: Can use AppState created by the builder
