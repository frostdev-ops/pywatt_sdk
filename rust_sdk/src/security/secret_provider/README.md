# Secret Provider

The secret provider module implements server-side secret management with pluggable backends, metrics collection, and event-driven rotation support. It provides a trait-based architecture for different secret storage implementations.

## Architecture

The module is built around the `SecretProvider` trait, which defines a common interface for secret storage backends. Multiple implementations can be chained together for fallback scenarios, and all providers support async operations with optional watching for changes.

## Core Components

### [`mod.rs`](./mod.rs)
Main module defining the `SecretProvider` trait and initialization logic:

#### SecretProvider Trait
```rust
#[async_trait]
pub trait SecretProvider: Send + Sync + std::fmt::Debug {
    async fn get(&self, key: &str) -> Result<SecretString, SecretError>;
    async fn set(&self, key: &str, value: SecretString) -> Result<(), SecretError>;
    async fn keys(&self) -> Result<Vec<String>, SecretError>;
    async fn watch(&self, tx: broadcast::Sender<SecretEvent>) -> Result<(), SecretError>;
}
```

#### Initialization
- `init()` - Creates provider chain based on `SECRET_PROVIDER_CHAIN` environment variable
- Supports `env` and `file` providers with configuration via environment variables
- Automatic fallback chaining when multiple providers are specified

#### Utility Functions
- `redact_line()` - Redacts secret values from log lines using provider keys
- Re-exports all provider implementations and supporting types

### [`errors.rs`](./errors.rs)
Defines `SecretError` enum for comprehensive error handling:

```rust
pub enum SecretError {
    NotFound(String),                    // Secret key not found
    UnsupportedOperation(String),        // Operation not supported by provider
    Backend(anyhow::Error),             // Underlying backend error
    Configuration(String),               // Provider configuration error
}
```

### [`events.rs`](./events.rs)
Defines `SecretEvent` enum for change notifications:

```rust
pub enum SecretEvent {
    Rotated(Vec<String>),    // Secrets have been updated/rotated
    Added(String),           // New secret key added
    Removed(String),         // Existing secret key removed
}
```

### [`metrics.rs`](./metrics.rs) *(feature-gated)*
Comprehensive metrics collection for secret operations:

#### Metrics Functions
- `record_operation()` - Track operation counts by provider/operation/outcome
- `record_rotation()` - Track rotation events and counts
- `record_cache_access()` - Track cache hit/miss ratios
- `record_operation_duration()` - Track operation latency
- `record_cache_size()` - Track current cache size

#### OpTimer Utility
```rust
let timer = OpTimer::new("env", "get");
// ... perform operation ...
timer.finish_with_outcome("success");
```

Automatic timing and outcome recording with RAII cleanup.

### [`tracing.rs`](./tracing.rs)
Structured tracing support with security considerations:

#### Key Hashing
- `hash_key()` - Hash secret key names to avoid exposing sensitive key names in logs
- `add_hashed_key()` - Add hashed key to current tracing span

#### Span Management
- `record_success()` - Mark operation as successful in current span
- `record_error()` - Record error details with categorization
- `instrument_secret_op!()` - Macro for instrumenting secret operations

#### Security Features
- Prevents secret key names from appearing in logs
- Categorizes errors without exposing sensitive details
- Structured fields for metrics correlation

## Provider Implementations

### [`providers/env_provider.rs`](./providers/env_provider.rs)
Environment variable-based secret provider:

#### Features
- **Read-only**: `set()` operations return `UnsupportedOperation`
- **No watching**: `watch()` is a no-op (environment variables don't change dynamically)
- **Empty keys**: Returns empty list for `keys()` for security/performance
- **Error handling**: Distinguishes between missing variables and access errors

#### Usage
```rust
let provider = EnvProvider::new();
let secret = provider.get("DATABASE_URL").await?;
```

#### Instrumentation
- Full tracing support with operation timing
- Metrics collection when feature enabled
- Hashed key logging for security

### [`providers/file_provider.rs`](./providers/file_provider.rs)
File-based secret provider with watching support:

#### Features
- **TOML format**: Currently supports TOML file format
- **File watching**: Uses `notify` crate for real-time change detection
- **Read-only**: `set()` operations are not supported
- **Atomic reloading**: Complete file reload on changes
- **Change detection**: Tracks which keys changed during reload

#### File Format
```toml
DATABASE_URL = "postgresql://user:pass@localhost/db"
API_KEY = "secret-api-key-value"
DEBUG_MODE = "true"
```

#### Usage
```rust
let provider = FileProvider::new("/path/to/secrets.toml", FileFormat::Toml).await?;
let secret = provider.get("API_KEY").await?;

// Enable watching
let (tx, rx) = broadcast::channel(10);
provider.watch(tx).await?;
```

#### Watching Implementation
- Background task monitors file system events
- Debounced reloading to handle multiple rapid changes
- Broadcasts `SecretEvent::Rotated` with changed key list
- Handles file creation, modification, and deletion events

### [`providers/memory_provider.rs`](./providers/memory_provider.rs)
In-memory secret provider for testing and development:

#### Features
- **Full CRUD**: Supports all operations including `set()`
- **Concurrent access**: Thread-safe using `DashMap`
- **Event notifications**: Broadcasts `Added` and `Rotated` events
- **Testing utilities**: Easy setup with initial secret maps

#### Usage
```rust
let provider = MemoryProvider::new();
provider.set("TEST_KEY", SecretString::new("test_value".into())).await?;

// With initial secrets
let initial = DashMap::new();
initial.insert("KEY1".to_string(), SecretString::new("value1".into()));
let provider = MemoryProvider::with_secrets(initial);
```

#### Event Handling
- `set()` operations trigger appropriate events
- Multiple subscribers supported via `broadcast::Sender`
- Automatic event generation for additions vs. rotations

### [`providers/chained_provider.rs`](./providers/chained_provider.rs)
Chains multiple providers for fallback scenarios:

#### Features
- **Fallback logic**: Tries providers in order until one succeeds
- **Combined keys**: Returns union of all provider keys
- **Set operations**: Attempts `set()` on first supporting provider
- **Event aggregation**: Forwards events from all chained providers

#### Usage
```rust
let providers = vec![
    Arc::new(EnvProvider::new()),
    Arc::new(FileProvider::new("secrets.toml", FileFormat::Toml).await?),
    Arc::new(MemoryProvider::new()),
];
let chained = ChainedProvider::new(providers);
```

#### Behavior
- `get()`: Returns first successful result, continues on `NotFound`
- `set()`: Tries each provider until one supports the operation
- `keys()`: Returns deduplicated union of all provider keys
- `watch()`: Attaches same event sender to all providers

## Configuration

### Environment Variables
- `SECRET_PROVIDER_CHAIN` - Comma-separated list of providers (`env,file`)
- `SECRET_FILE_PATH` - Path to secrets file (required for `file` provider)
- `SECRET_FILE_FORMAT` - File format (`toml`, default: `toml`)

### Example Configuration
```bash
export SECRET_PROVIDER_CHAIN="env,file"
export SECRET_FILE_PATH="/etc/secrets/app.toml"
export SECRET_FILE_FORMAT="toml"
```

## Usage Patterns

### Basic Provider Setup
```rust
use pywatt_sdk::security::secret_provider::{init, SecretProvider};

// Initialize from environment
let provider = init().await?;
let secret = provider.get("DATABASE_URL").await?;
```

### Custom Provider Chain
```rust
use pywatt_sdk::security::secret_provider::providers::*;

let providers: Vec<Arc<dyn SecretProvider>> = vec![
    Arc::new(EnvProvider::new()),
    Arc::new(FileProvider::new("secrets.toml", FileFormat::Toml).await?),
    Arc::new(MemoryProvider::new()),
];
let provider = ChainedProvider::new(providers);
```

### Event Watching
```rust
let (tx, mut rx) = broadcast::channel(10);
provider.watch(tx).await?;

tokio::spawn(async move {
    while let Ok(event) = rx.recv().await {
        match event {
            SecretEvent::Rotated(keys) => {
                println!("Secrets rotated: {:?}", keys);
                // Refresh application state
            }
            SecretEvent::Added(key) => {
                println!("Secret added: {}", key);
            }
            SecretEvent::Removed(key) => {
                println!("Secret removed: {}", key);
            }
        }
    }
});
```

### Metrics Integration
```rust
#[cfg(feature = "metrics")]
{
    use pywatt_sdk::security::secret_provider::metrics::OpTimer;
    
    let timer = OpTimer::new("file", "get");
    let result = provider.get("API_KEY").await;
    match result {
        Ok(_) => timer.finish_with_outcome("success"),
        Err(_) => timer.finish_with_outcome("error"),
    }
}
```

## Security Considerations

### Key Name Protection
- Secret key names are hashed before appearing in logs
- Tracing spans use hashed keys to prevent exposure
- Error messages avoid including sensitive key names

### Memory Safety
- All secret values use `secrecy::SecretString`
- Automatic zeroization on drop
- No accidental exposure in debug output

### File Security
- File provider validates file permissions
- Atomic reloading prevents partial reads
- Secure handling of file system events

### Access Control
- Providers can implement custom access controls
- Error categorization helps with security auditing
- Comprehensive logging for security monitoring

## Testing

### Unit Tests
Each provider includes comprehensive unit tests:
- Basic CRUD operations
- Error conditions
- Event generation
- Concurrent access patterns

### Integration Tests
- Provider chaining scenarios
- File watching functionality
- Metrics collection verification
- Event propagation testing

### Test Utilities
```rust
// Memory provider for testing
let provider = MemoryProvider::new();
provider.set("TEST_KEY", SecretString::new("test_value".into())).await?;

// Verify events
let (tx, mut rx) = broadcast::channel(1);
provider.watch(tx).await?;
provider.set("KEY", SecretString::new("value".into())).await?;
assert_eq!(rx.recv().await?, SecretEvent::Added("KEY".to_string()));
```

## Performance Characteristics

### Memory Provider
- O(1) get/set operations using DashMap
- Lock-free concurrent reads
- Minimal memory overhead

### File Provider
- O(n) reload time proportional to file size
- Debounced reloading reduces I/O overhead
- Efficient change detection

### Environment Provider
- O(1) access via system calls
- No caching (relies on OS caching)
- Minimal memory footprint

### Chained Provider
- O(n) worst-case where n is number of providers
- Short-circuits on first success
- Minimal overhead for successful operations 