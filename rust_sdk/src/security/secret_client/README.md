# Secret Client

The secret client module provides client-side functionality for secure communication with the PyWatt orchestrator's secret management system. It handles secret retrieval, caching, rotation notifications, and automatic redaction.

## Architecture

The secret client implements a caching layer with automatic rotation handling and secure IPC communication over stdin/stdout. It uses JSON-line protocol for communication with the orchestrator.

## Core Components

### [`client.rs`](./client.rs)
The main `SecretClient` implementation providing:

#### Key Features
- **Caching**: DashMap-based concurrent cache for secret values
- **Request Modes**: `CacheThenRemote`, `ForceRemote`, `CacheOnly`
- **Rotation Tracking**: Automatic handling of secret rotation notifications
- **Background Processing**: Async task for processing incoming IPC messages
- **Timeout Handling**: 5-second timeout for orchestrator responses

#### Core Methods
```rust
// Get secret with caching strategy
async fn get_secret(&self, key: &str, mode: RequestMode) -> Result<SecretString, SecretClientError>

// Acknowledge rotation completion
async fn acknowledge_rotation(&self, rotation_id: &str, status: &str) -> Result<(), SecretClientError>

// Subscribe to rotation events
fn subscribe_to_rotations(&self) -> broadcast::Receiver<Vec<String>>

// Process incoming server messages
async fn process_server_message(&self, message: &str) -> Result<(), SecretClientError>
```

#### Typed Secret Support
The client provides convenience methods for typed secret retrieval:
- `get_typed<T>()` - Parse secret into any `FromStr` type
- `get_string()` - Get secret as `Secret<String>`
- `get_bool()` - Get secret as `Secret<bool>`
- `get_int<T>()` - Get secret as numeric type

### [`error.rs`](./error.rs)
Defines `SecretClientError` enum with variants:
- `NotFound(String)` - Secret key not found
- `Json(serde_json::Error)` - JSON serialization/deserialization errors
- `Io(std::io::Error)` - I/O communication errors
- `Unexpected(String)` - Unexpected responses or behavior
- `Other(String)` - General error cases

### [`logging.rs`](./logging.rs)
Provides automatic secret redaction functionality:

#### Redaction Registry
- Global `DashMap` tracking secrets that need redaction
- `register_for_redaction()` - Register secret values for redaction
- `redact()` - Replace secret values with `[REDACTED]` in strings
- Uses Aho-Corasick algorithm for efficient multi-pattern matching

#### Safe Logging Macros
```rust
safe_log!(error, "Database connection failed: {}", connection_string);
safe_log!(info, "API key loaded: {}", api_key);
```

#### Tracing Integration
- `init_logging()` - Configure tracing subscriber with JSON output to stderr
- Automatic redaction in all log output

### [`schema.rs`](./schema.rs)
Defines IPC message schemas:
- Re-exports from `crate::ipc_types` for protocol compatibility
- `GetSecretResponse` - Response wrapper with automatic redaction in serialization
- Rotation tracking with `rotation_id` fields

### [`stdout.rs`](./stdout.rs)
Provides structured JSON output utilities:

#### JsonStdout
Type-safe wrapper for stdout JSON serialization:
```rust
let mut stdout = JsonStdout::new();
stdout.write(&announcement)?;
```

#### Macros
- `json_println!()` - Write serializable values as JSON to stdout
- `stderr!()` - Write messages to stderr (for non-IPC output)

#### Feature Guards
Optional compile-time prevention of `println!` usage to enforce JSON-only stdout.

### [`mod.rs`](./mod.rs)
Module organization and re-exports:
- Public API surface with key types and functions
- `init()` - Get global client instance
- `with_redaction()` - Convenience wrapper for secret registration

## Usage Patterns

### Basic Client Setup
```rust
use pywatt_sdk::security::secret_client::{SecretClient, RequestMode};

// Create client with IPC channels
let client = SecretClient::new("http://orchestrator:9000", "my-module").await?;

// Start background message processing
let handle = client.start_background_task();
```

### Secret Retrieval
```rust
// Cache-first retrieval
let secret = client.get_secret("DATABASE_URL", RequestMode::CacheThenRemote).await?;

// Force fresh fetch
let fresh_secret = client.get_secret("API_KEY", RequestMode::ForceRemote).await?;

// Cache-only (no network)
let cached = client.get_secret("CONFIG", RequestMode::CacheOnly).await?;
```

### Rotation Handling
```rust
// Subscribe to rotation events
let mut rx = client.subscribe_to_rotations();

tokio::spawn(async move {
    while let Ok(rotated_keys) = rx.recv().await {
        for key in rotated_keys {
            // Handle rotation for specific keys
            if key == "DATABASE_URL" {
                reconnect_database().await;
            }
        }
    }
});
```

### Typed Secrets
```rust
// Parse secrets into specific types
let port: Secret<u16> = client.get_typed("PORT").await?;
let debug_mode: Secret<bool> = client.get_bool("DEBUG_MODE").await?;
let timeout: Secret<u64> = client.get_int("TIMEOUT_SECONDS").await?;
```

## IPC Protocol

### Message Flow
1. **Handshake**: Module reads `Init` message from stdin
2. **Requests**: Module sends `GetSecretRequest` to stdout
3. **Responses**: Orchestrator sends `Secret` responses via stdin
4. **Notifications**: Orchestrator sends `Rotated` notifications for secret updates
5. **Acknowledgments**: Module sends `RotationAck` confirmations

### Message Types
- `ClientRequest::GetSecret` - Request secret by name
- `ClientRequest::RotationAck` - Acknowledge rotation completion
- `ServerResponse::Secret` - Secret value with optional rotation ID
- `ServerResponse::Rotated` - Notification of rotated secrets
- `ServerResponse::Shutdown` - Graceful shutdown signal

## Security Features

### Automatic Redaction
All secret values are automatically registered for redaction:
```rust
let secret = client.get_secret("API_KEY").await?;
// Secret is automatically registered for redaction
log::info!("Loaded API key: {}", secret.expose_secret()); // Will show [REDACTED]
```

### Memory Safety
- Uses `secrecy::SecretString` for in-memory secret storage
- Automatic zeroization on drop
- No accidental secret exposure in debug output

### Concurrent Access
- Thread-safe `DashMap` for caching
- Async-safe with `tokio::sync::Mutex` for I/O channels
- Lock-free reads for cached values

## Testing Support

### Test Utilities
```rust
// Create dummy client for testing
let client = SecretClient::new_dummy();

// Insert test secrets
client.insert_test_secret("TEST_KEY", "test_value").await;

// Simulate rotation events
client.send_test_rotation(vec!["TEST_KEY".to_string()])?;
```

### Integration Testing
The client supports full integration testing with mock orchestrator communication through configurable I/O channels.

## Error Handling

All operations return `Result<T, SecretClientError>` with comprehensive error information:
- Network timeouts are handled gracefully
- JSON parsing errors include context
- Missing secrets return `NotFound` with key name
- I/O errors are wrapped with additional context

## Performance Considerations

- **Caching**: Reduces orchestrator round-trips for frequently accessed secrets
- **Concurrent Access**: Lock-free reads from cache using DashMap
- **Efficient Redaction**: Aho-Corasick algorithm for O(n) multi-pattern replacement
- **Background Processing**: Non-blocking message handling in separate task 