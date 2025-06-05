# Secrets

The secrets module provides high-level utilities for secret management in PyWatt modules, including client initialization, typed secret handling, and rotation subscription. It serves as the primary interface for modules to interact with the orchestrator's secret management system.

## Architecture

This module builds on top of the `secret_client` to provide convenient, type-safe APIs for common secret management tasks. It handles automatic redaction registration and provides utilities for secret rotation handling.

## Core Components

### [`mod.rs`](./mod.rs)
Main module providing high-level secret management functions:

#### Client Management
```rust
// Create a new SecretClient for module use
pub async fn get_module_secret_client(
    orchestrator_api: &str,
    module_id: &str,
) -> Result<Arc<SecretClient>, ModuleSecretError>

// Retrieve a secret with automatic redaction registration
pub async fn get_secret(
    client: &Arc<SecretClient>,
    key: &str,
) -> Result<SecretString, ModuleSecretError>

// Retrieve multiple secrets at once
pub async fn get_secrets(
    client: &Arc<SecretClient>,
    keys: &[&str],
) -> Result<Vec<SecretString>, ModuleSecretError>
```

#### Rotation Handling
```rust
// Subscribe to secret rotations with callback
pub fn subscribe_secret_rotations<F>(
    client: Arc<SecretClient>,
    keys: Vec<String>,
    on_rotate: F,
) -> JoinHandle<()>
where
    F: Fn(String, SecretString) + Send + 'static
```

#### Type Aliases
- `ModuleSecretError` - Alias for `SecretError` for consistency

### [`typed_secret.rs`](./typed_secret.rs)
Type-safe secret wrapper and parsing utilities:

#### Secret<T> Wrapper
```rust
pub struct Secret<T> {
    value: T,
}
```

**Features:**
- Generic wrapper for any type
- Automatic redaction in debug output
- Safe exposure via `expose_secret()`
- Functional mapping with `map()`
- Serialization/deserialization support

#### Parsing Functions
```rust
// Parse secret into any FromStr type
pub async fn get_typed_secret<T, S>(
    client: &SecretClient,
    key: S,
) -> Result<Secret<T>, TypedSecretError>

// Convenience functions for common types
pub async fn get_string_secret<S>(
    client: &SecretClient,
    key: S,
) -> Result<Secret<String>, TypedSecretError>

pub async fn get_int_secret<T, S>(
    client: &SecretClient,
    key: S,
) -> Result<Secret<T>, TypedSecretError>

pub async fn get_bool_secret<S>(
    client: &SecretClient,
    key: S,
) -> Result<Secret<bool>, TypedSecretError>
```

#### Error Handling
```rust
pub enum TypedSecretError {
    SecretError(SecretError),    // Error from secret client
    ParseError(String),          // Type parsing error
}
```

## Usage Patterns

### Basic Module Setup
```rust
use pywatt_sdk::security::secrets::{get_module_secret_client, get_secret};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize secret client
    let client = get_module_secret_client(
        "http://orchestrator:9000",
        "my-module"
    ).await?;
    
    // Get secrets with automatic redaction
    let db_url = get_secret(&client, "DATABASE_URL").await?;
    let api_key = get_secret(&client, "API_KEY").await?;
    
    // Use secrets safely
    connect_database(db_url.expose_secret()).await?;
    
    Ok(())
}
```

### Multiple Secret Retrieval
```rust
use pywatt_sdk::security::secrets::get_secrets;

let secrets = get_secrets(&client, &[
    "DATABASE_URL",
    "API_KEY", 
    "JWT_SECRET"
]).await?;

let [db_url, api_key, jwt_secret] = secrets.try_into()
    .map_err(|_| "Expected exactly 3 secrets")?;
```

### Typed Secret Handling
```rust
use pywatt_sdk::security::secrets::typed_secret::{
    get_typed_secret, get_string_secret, get_int_secret, get_bool_secret
};

// Parse secrets into specific types
let port: Secret<u16> = get_typed_secret(&client, "PORT").await?;
let timeout: Secret<u64> = get_int_secret(&client, "TIMEOUT_SECONDS").await?;
let debug_mode: Secret<bool> = get_bool_secret(&client, "DEBUG_MODE").await?;
let api_key: Secret<String> = get_string_secret(&client, "API_KEY").await?;

// Use typed values
let server_addr = format!("0.0.0.0:{}", port.expose_secret());
let timeout_duration = Duration::from_secs(*timeout.expose_secret());

if *debug_mode.expose_secret() {
    println!("Debug mode enabled");
}
```

### Secret Rotation Handling
```rust
use pywatt_sdk::security::secrets::subscribe_secret_rotations;
use std::sync::Arc;
use tokio::sync::RwLock;

// Shared application state
#[derive(Clone)]
struct AppState {
    db_pool: Arc<RwLock<DatabasePool>>,
    api_client: Arc<RwLock<ApiClient>>,
}

let state = AppState {
    db_pool: Arc::new(RwLock::new(initial_pool)),
    api_client: Arc::new(RwLock::new(initial_client)),
};

// Subscribe to rotations
let rotation_handle = subscribe_secret_rotations(
    client.clone(),
    vec!["DATABASE_URL".to_string(), "API_KEY".to_string()],
    {
        let state = state.clone();
        move |key, new_secret| {
            let state = state.clone();
            tokio::spawn(async move {
                match key.as_str() {
                    "DATABASE_URL" => {
                        // Reconnect database
                        let new_pool = create_pool(new_secret.expose_secret()).await;
                        *state.db_pool.write().await = new_pool;
                        println!("Database connection rotated");
                    }
                    "API_KEY" => {
                        // Update API client
                        let new_client = create_api_client(new_secret.expose_secret()).await;
                        *state.api_client.write().await = new_client;
                        println!("API client credentials rotated");
                    }
                    _ => {}
                }
            });
        }
    }
);
```

### Advanced Typed Secret Usage
```rust
use pywatt_sdk::security::secrets::typed_secret::Secret;

// Custom parsing with validation
let port_secret: Secret<u16> = get_typed_secret(&client, "PORT").await?;
let validated_port = port_secret.map(|port| {
    if port < 1024 {
        panic!("Port must be >= 1024");
    }
    port
});

// Serialization support
#[derive(Serialize, Deserialize)]
struct Config {
    database_url: Secret<String>,
    api_key: Secret<String>,
    port: Secret<u16>,
}

let config = Config {
    database_url: get_string_secret(&client, "DATABASE_URL").await?,
    api_key: get_string_secret(&client, "API_KEY").await?,
    port: get_typed_secret(&client, "PORT").await?,
};

// Serialize config (secrets are included in serialization)
let json = serde_json::to_string(&config)?;
```

## Security Features

### Automatic Redaction
All secrets retrieved through this module are automatically registered for redaction:

```rust
let secret = get_secret(&client, "API_KEY").await?;
// "API_KEY" value is now redacted in all logs

println!("Secret: {:?}", secret); // Prints: Secret([REDACTED])
log::info!("Using API key: {}", secret.expose_secret()); // Shows [REDACTED]
```

### Type Safety
The `Secret<T>` wrapper prevents accidental exposure:

```rust
let api_key: Secret<String> = get_string_secret(&client, "API_KEY").await?;

// This won't compile - no direct access to inner value
// let key_str = api_key.value; // Error!

// Must explicitly expose
let key_str = api_key.expose_secret(); // Intentional access
```

### Memory Safety
- Uses `secrecy::SecretString` internally for secure storage
- Automatic zeroization on drop
- No accidental copying of sensitive data

## Error Handling

### Comprehensive Error Types
```rust
// From secret client operations
match get_secret(&client, "MISSING_KEY").await {
    Ok(secret) => { /* use secret */ }
    Err(ModuleSecretError::NotFound(key)) => {
        eprintln!("Secret '{}' not found", key);
    }
    Err(ModuleSecretError::Io(e)) => {
        eprintln!("Communication error: {}", e);
    }
    Err(e) => {
        eprintln!("Other error: {}", e);
    }
}

// From typed secret parsing
match get_typed_secret::<u16>(&client, "PORT").await {
    Ok(port) => { /* use port */ }
    Err(TypedSecretError::SecretError(e)) => {
        eprintln!("Failed to retrieve secret: {}", e);
    }
    Err(TypedSecretError::ParseError(e)) => {
        eprintln!("Failed to parse port number: {}", e);
    }
}
```

### Error Context
All errors include sufficient context for debugging:
- Secret key names in error messages
- Parsing error details
- Communication failure reasons

## Testing Support

### Test Utilities
```rust
use pywatt_sdk::security::secret_client::SecretClient;

#[tokio::test]
async fn test_secret_retrieval() {
    let client = Arc::new(SecretClient::new_dummy());
    
    // Insert test secrets
    client.insert_test_secret("TEST_KEY", "test_value").await;
    client.insert_test_secret("PORT", "8080").await;
    
    // Test basic retrieval
    let secret = get_secret(&client, "TEST_KEY").await.unwrap();
    assert_eq!(secret.expose_secret(), "test_value");
    
    // Test typed retrieval
    let port: Secret<u16> = get_typed_secret(&client, "PORT").await.unwrap();
    assert_eq!(*port.expose_secret(), 8080);
}
```

### Mock Rotation Events
```rust
#[tokio::test]
async fn test_rotation_handling() {
    let client = Arc::new(SecretClient::new_dummy());
    let rotated_keys = Arc::new(Mutex::new(Vec::new()));
    
    let keys_clone = rotated_keys.clone();
    let _handle = subscribe_secret_rotations(
        client.clone(),
        vec!["TEST_KEY".to_string()],
        move |key, _value| {
            keys_clone.lock().unwrap().push(key);
        }
    );
    
    // Simulate rotation
    client.send_test_rotation(vec!["TEST_KEY".to_string()]).unwrap();
    
    // Verify callback was called
    tokio::time::sleep(Duration::from_millis(50)).await;
    assert_eq!(rotated_keys.lock().unwrap().len(), 1);
}
```

## Performance Considerations

### Caching
- Leverages `SecretClient` caching for performance
- Multiple calls to same secret key use cached values
- Rotation events invalidate cache automatically

### Memory Usage
- `Secret<T>` wrapper has minimal overhead
- Secrets stored as `SecretString` with secure cleanup
- Efficient redaction using Aho-Corasick algorithm

### Async Operations
- All operations are fully async
- Non-blocking secret retrieval
- Background rotation handling

## Best Practices

### Secret Lifecycle
1. **Initialization**: Get client early in module startup
2. **Retrieval**: Fetch secrets as needed with automatic redaction
3. **Usage**: Expose secrets only when necessary
4. **Rotation**: Subscribe to changes for long-running services
5. **Cleanup**: Automatic cleanup via RAII

### Error Handling
```rust
// Handle missing secrets gracefully
let optional_secret = match get_secret(&client, "OPTIONAL_KEY").await {
    Ok(secret) => Some(secret),
    Err(ModuleSecretError::NotFound(_)) => None,
    Err(e) => return Err(e.into()),
};
```

### Type Safety
```rust
// Use typed secrets for validation
let port: Secret<u16> = get_typed_secret(&client, "PORT").await
    .map_err(|e| format!("Invalid port configuration: {}", e))?;

// Validate ranges
let validated_port = port.map(|p| {
    if p == 0 || p > 65535 {
        panic!("Port must be between 1 and 65535");
    }
    p
});
```

### Rotation Handling
```rust
// Keep rotation handlers lightweight
subscribe_secret_rotations(
    client,
    vec!["DATABASE_URL".to_string()],
    |key, new_secret| {
        // Spawn async task for heavy work
        tokio::spawn(async move {
            reconnect_database(new_secret.expose_secret()).await;
        });
    }
);
``` 