---
trigger: always_on
description: 
globs: 
---
# Component: Module Secret Management

## Component Type
Utility / Cursor Rule

## File Path
`.cursor/rules/module_secret_management.mdc`

## Purpose
Defines the standard pattern for secret retrieval, redaction, and rotation in PyWatt modules, using `pywatt_module_utils` to ensure consistency and security.

## Rules
1. **Get Secret Client**
   - Use `get_module_secret_client(&init.orchestrator_api, &init.module_id).await?` to obtain an authenticated `SecretClient`.
2. **Fetch & Register**
   - Call `get_module_secret(&client, "<KEY>").await?` to retrieve a secret.
   - Immediately call `register_secret_for_redaction(&secret)` so any logs are redacted.
3. **Rotation Subscription**
   - Use `subscribe_secret_rotations(client.clone(), keys, callback).await` to listen for secret rotations.
   - In callback, update in-memory state and re-register new secret for redaction.
4. **No Direct Env Vars**
   - Remove any `std::env::var` calls for sensitive keys. Assume secrets come solely via `SecretClient`.

## Usage Example
```rust
use pywatt_module_utils::{get_module_secret_client, get_module_secret, subscribe_secret_rotations};
use secret_client::register_secret_for_redaction;

async fn setup(mut init: OrchestratorInit) -> Result<(), AppError> {
    let client = get_module_secret_client(&init.orchestrator_api, &init.module_id).await?;

    // Fetch & register
    let db_url = get_module_secret(&client, "DATABASE_URL").await?;
    register_secret_for_redaction(&db_url);

    // Subscribe to rotations
    subscribe_secret_rotations(client.clone(), vec!["DATABASE_URL".to_string()], |key, new_val| {
        if key == "DATABASE_URL" {
            update_db_url(&new_val);
            register_secret_for_redaction(&new_val);
        }
    }).await;

    Ok(())
}
```

## Removal of Legacy Vault Code
- **Search**: `rg --ignore-case 'Vault|vault.rs' src/modules`
- **Remove**: Delete or refactor code referencing `VaultClient` or `vault.rs`.

## Cleanup Verification
- After refactoring, run:
  ```bash
  rg 'std::env::var("DATABASE_URL")' -n src/modules
  ```
  Ensuring zero matches.

## Notes & Best Practices
- Always register secrets for redaction immediately.
- Handle rotation in background tasks with minimal blocking.
- Prefer explicit keys list for subscription, avoid subscribing to all secrets.

<context>
This rule defines the standard practices for secret management within modules managed by the PyWatt Orchestrator. Following these practices ensures secure, consistent handling of sensitive information across the application.
</context>

<rules>

1. **Use the `secret_client` Crate**:
   * All modules MUST use the official `secret_client` crate for secret management.
   * Direct environment variable access for secrets is discouraged.
   * Never implement custom secret handling logic that bypasses the standard client.

2. **Proper Initialization**:
   * Initialize the secret client early in the module's startup.
   * Use `secret_client::init()` to get a global client instance.
   * Use `secret_client::init_logging()` to configure proper logging with redaction.

3. **Secret Retrieval and Caching**:
   * Use `get_secret()` to retrieve secrets, which handles caching automatically.
   * Specify appropriate `RequestMode` based on need (default: `CacheThenRemote`).
   * Handle rotation events by subscribing to the rotation channel.

4. **Secret Redaction**:
   * Register ALL secrets for redaction using `register_secret_for_redaction()`.
   * Use `safe_log!` macros for logging that might contain secrets.
   * Use `redact()` when manually handling potential secret-containing strings.

5. **Output Channel Separation**:
   * Never send secrets via stdout except through the secure IPC channel.
   * All debug output containing secrets must go to stderr.
   * Use `safe_log!` or `print_stderr()` for safe logging.

</rules>

<patterns>

## Module Initialization with Secret Client
```rust
use secret_client::{init_logging, init};
use tracing::info;

fn main() {
    // Initialize logging first (directs to stderr with redaction)
    init_logging();
    
    // Get the global secret client instance
    let client = init();
    
    info!("Module started with secret client initialized");
    
    // Continue with module initialization...
}
```

## Secret Retrieval Pattern
```rust
use secret_client::{get_secret, RequestMode, register_secret_for_redaction};
use tracing::info;

async fn setup_database_connection() -> Result<DatabaseClient, Error> {
    // Get the database connection URL
    let db_url = get_secret("DATABASE_URL").await?;
    
    // Register it for redaction
    register_secret_for_redaction(&db_url);
    
    // Now safe to use in logs as it will be automatically redacted
    info!("Connecting to database: {}", db_url.expose_secret());
    
    // Use the secret
    DatabaseClient::connect(db_url.expose_secret()).await
}
```

## Handling Secret Rotation
```rust
use secret_client::{init, RequestMode};
use tokio::spawn;
use tracing::info;

fn setup_rotation_handler() {
    let client = init();
    
    // Subscribe to rotation events
    let mut rotation_rx = client.subscribe_to_rotations();
    
    // Handle rotation in a background task
    spawn(async move {
        while let Ok(rotated_keys) = rotation_rx.recv().await {
            info!("Received rotation for keys: {:?}", rotated_keys);
            
            // Refresh secrets if needed
            for key in rotated_keys {
                if key == "DATABASE_URL" {
                    // Force refresh from remote
                    if let Ok(new_url) = client.get_secret(&key, RequestMode::ForceRemote).await {
                        // Update connections as needed
                        reconnect_database(new_url).await;
                    }
                }
            }
        }
    });
}
```

</patterns>

<examples>

## Complete Module Example
```rust
use secret_client::{init_logging, init, get_secret, register_secret_for_redaction, safe_log};
use secrecy::ExposeSecret;
use serde::{Serialize, Deserialize};
use tokio::spawn;
use tracing::{info, error};

// Module initialization data
#[derive(Deserialize)]
struct OrchestratorInit {
    orchestrator_api: String,
    module_id: String,
    // No env field - will use secret_client instead
}

// Module registration
#[derive(Serialize)]
struct ModuleRegistration {
    listen: String,
    endpoints: Vec<EndpointInfo>,
}

#[derive(Serialize)]
struct EndpointInfo {
    path: String,
    methods: Vec<String>,
    auth: Option<String>,
}

#[tokio::main]
async fn main() {
    // 1. Initialize logging (correct stderr output)
    init_logging();
    
    // 2. Get secret client
    let client = init();
    
    // 3. Setup rotation handling
    setup_rotation_handler(client.clone());
    
    // 4. Read handshake from orchestrator
    // ... handshake code ...
    
    // 5. Get necessary secrets
    match get_secret("DATABASE_URL").await {
        Ok(db_url) => {
            // Register for redaction
            register_secret_for_redaction(&db_url);
            
            // Connect to database
            info!("Connecting to database");
            // Safe, as secret will be redacted
            let result = connect_db(db_url.expose_secret()).await;
        }
        Err(e) => {
            error!("Failed to get database URL: {}", e);
            std::process::exit(1);
        }
    }
    
    // 6. Announce back to orchestrator
    let registration = ModuleRegistration {
        listen: "127.0.0.1:8080".to_string(),
        endpoints: vec![
            EndpointInfo {
                path: "/health".to_string(),
                methods: vec!["GET".to_string()],
                auth: None,
            }
        ],
    };
    
    // Send using the safe_log macro to ensure it goes to stdout
    if let Ok(json) = serde_json::to_string(&registration) {
        safe_log!(info, "{}", json);
    }
    
    // ... rest of module code ...
}

fn setup_rotation_handler(client: Arc<SecretClient>) {
    // Subscribe to rotation events
    let mut rotation_rx = client.subscribe_to_rotations();
    
    // Handle rotation in a background task
    spawn(async move {
        while let Ok(rotated_keys) = rotation_rx.recv().await {
            info!("Received rotation for keys: {:?}", rotated_keys);
            
            // Refresh secrets if needed
            for key in rotated_keys {
                if key == "DATABASE_URL" {
                    // Handle rotation...
                }
            }
        }
    });
}
```

## Incorrect Secret Management (What Not To Do)
```rust
// INCORRECT: Accessing environment variables directly
fn get_db_connection() -> Result<DbConn, Error> {
    // BAD: Bypasses secret client and rotation capability
    let db_url = std::env::var("DATABASE_URL")?;
    // BAD: No automatic redaction in logs
    println!("Connecting to {}", db_url);
    // ... connect to DB
}

// INCORRECT: Logging secrets without redaction
async fn log_connection_details(client: &Client) {
    // BAD: Secret exposed in logs without redaction
    let api_key = client.get_secret("API_KEY").await?;
    info!("Using API key: {}", api_key.expose_secret());
}
```

</examples>

<consequences>
- Using direct environment access bypasses secret rotation capabilities
- Failing to use `secret_client` and its redaction features may expose sensitive information in logs
- Improper stdout/stderr usage can break the IPC protocol with the orchestrator
- Lack of proper secret rotation handling can result in using stale credentials
</consequences>

<related>
- `module_stdio_usage`: Defines standard usage of stdout/stderr for proper orchestrator communication
- `secret_client`: Client library for module secret management
- `secret_provider`: Server-side library for orchestrator secret management
</related> 