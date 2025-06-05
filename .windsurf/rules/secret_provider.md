---
trigger: always_on
description: 
globs: 
---
# Secret Provider

## Purpose
Document the goals, public API, thread-safety guarantees, lifetime expectations, redaction rules, and error taxonomy for the Secret Provider subsystem.

## Key Types & Structures
```rust
/// Thread-safe, async-friendly secret source.
///
/// Implementations MUST be `Send + Sync` and error-aware.
#[async_trait]
pub trait SecretProvider: Send + Sync {
    /// Retrieves a secret value for a given key.
    async fn get(&self, key: &str) -> Result<Secret<String>, SecretError>;

    /// Sets or updates a secret value for a given key.
    async fn set(&self, key: &str, value: Secret<String>) -> Result<(), SecretError>;

    /// Returns all stored keys. Used for redaction & discovery.
    async fn keys(&self) -> Result<Vec<String>, SecretError>;

    /// Optional: watch for secret rotations and emit events.
    async fn watch(&self, tx: broadcast::Sender<SecretEvent>);
}

/// Errors that can occur within the Secret Provider subsystem.
#[derive(thiserror::Error, Debug)]
pub enum SecretError {
    /// The requested secret was not found.
    #[error("secret {0} not found")]
    NotFound(String),

    /// Underlying backend error.
    #[error("backend error: {0}")]
    Backend(#[from] anyhow::Error),
}

/// Events emitted when secrets change.
pub enum SecretEvent {
    /// Secret(s) have been rotated. List of affected keys.
    Rotated(Vec<String>),
    /// A new secret was added.
    Added(String),
    /// An existing secret was removed.
    Removed(String),
}
```

## Design Patterns
### Trait-first Design
- **Purpose**: Defines a consistent interface for secret sources to support pluggable implementations.
- **Implementation**: Uses `async_trait` to allow async methods in traits.
- **Usage**: All providers (env, file, memory, chained) implement this trait.

## Error Handling
### Error Types
```rust
pub enum SecretError {
    NotFound(String),
    Backend(anyhow::Error),
}
```

### Error Propagation
- Errors are returned via `Result<_, SecretError>`.
- Backend errors use `anyhow::Error` for rich error context.

## Usage Examples
```rust
async fn example(provider: Arc<dyn SecretProvider>) -> Result<(), SecretError> {
    // Fetch a secret
    let secret = provider.get("DATABASE_URL").await?;
    // Use the secret
    println!("db: {}", secret.expose_secret());
    Ok(())
}
```

## Testing Approach
### Unit Tests
```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn memory_provider_roundtrip() {
        let provider = MemoryProvider::new();
        provider.set("foo".into(), SecretString::new("bar".into())).await.unwrap();
        assert_eq!(provider.get("foo").await.unwrap().expose_secret(), "bar");
    }
}
```

### Integration Tests
- Place in `tests/secret_provider_integration.rs`.
- Test scenario: chain env and file providers, rotate and retrieve secrets.

## Dependencies
### Internal Dependencies
- Depends on `dashmap` for concurrent in-memory storage (MemoryProvider).
- Uses `async_trait` for async trait support.

### External Dependencies
- `anyhow` for error handling.
- `secrecy` crate for secret types.
- `tokio` for async runtime.

## Notes & Best Practices
### Performance Considerations
- Implementations should minimize lock contention (e.g., use `DashMap`).

### Security Considerations
- Use `secrecy::Secret` to avoid accidental logging.
- Zeroize memory on drop to reduce secret persistence.
- Redact secrets in logs; use `keys()` for redaction logic.

### Rust Idioms
- Avoid blocking file IO; use async-friendly file watchers.

### Maintenance Notes
- Deprecate old `Vault` type after feature flag rollout.
- Migrate existing `VaultConfig` to new `secret_provider` config schema.

## Related Components
- `orchestrator`: integrates `SecretProvider` chain for module supervision.
- `secret_client`: module-side helper crate for fetching secrets.
