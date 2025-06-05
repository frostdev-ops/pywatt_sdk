# Registration Service (`pywatt_sdk::services::registration`)

This module implements the PyWatt module registration protocol, enabling modules to communicate their presence, capabilities, and health to an orchestrator over a TCP connection.

## Overview

The registration service handles the lifecycle of a module's interaction with the orchestrator, including:
- Initial registration to announce its existence.
- Unregistration when shutting down.
- Periodic heartbeats to signal health.
- Advertisement of capabilities, such as HTTP endpoints and supported message types.

Communication is performed using `TcpChannel` and messages are serialized (typically as JSON) before transmission.

## Core Functions

### `register_module`

Registers the module with the orchestrator.

- **Purpose**: Establishes a connection with the orchestrator, sends module information, and receives registration confirmation.
- **Arguments**:
    - `config: ConnectionConfig`: TCP connection details for the orchestrator (host, port).
    - `info: ModuleInfo`: Information about the module (name, version, description).
- **Process**:
    1. Connects to the orchestrator using `TcpChannel::connect()`.
    2. Creates a `RegistrationRequest` containing the `ModuleInfo`.
    3. Wraps the request in a `Message` with metadata (including a unique request ID).
    4. Sends the encoded message to the orchestrator.
    5. Awaits a `RegistrationResponse` (with a `DEFAULT_TIMEOUT`).
    6. If successful, stores the `Arc<TcpChannel>` in a global `REGISTRY` (a `Mutex<HashMap<Uuid, Arc<TcpChannel>>>`) keyed by the module's assigned `Uuid`.
- **Returns**: `Result<RegisteredModule, RegistrationError>`.

**Example**:
```rust
use pywatt_sdk::services::registration::{register_module, ModuleInfo};
use pywatt_sdk::tcp_types::ConnectionConfig;
use uuid::Uuid;

async fn register_my_module() {
    let config = ConnectionConfig::new("127.0.0.1".to_string(), 8080);
    let module_info = ModuleInfo::new("MyAwesomeModule", "1.0.0", "Processes awesome data");

    match register_module(config, module_info).await {
        Ok(registered_module) => {
            println!("Module registered successfully: {:?}", registered_module);
            // Now you can use `registered_module` for heartbeats and capability advertisement
        }
        Err(e) => eprintln!("Module registration failed: {}", e),
    }
}
```

### `unregister_module`

Unregisters the module from the orchestrator.

- **Purpose**: Notifies the orchestrator that the module is shutting down.
- **Arguments**: `module: &RegisteredModule`: The module instance obtained from `register_module`.
- **Process**:
    1. Retrieves or establishes a `TcpChannel` to the orchestrator.
    2. Creates an `UnregistrationRequest` with the module's ID and token.
    3. Sends the request and awaits an `UnregistrationResponse`.
    4. If successful, removes the module's `TcpChannel` from the global `REGISTRY`.
- **Returns**: `Result<(), RegistrationError>`.

**Example**:
```rust
use pywatt_sdk::services::registration::{unregister_module, RegisteredModule}; // Assuming RegisteredModule is available

async fn unregister_my_module(registered_module: &RegisteredModule) {
    match unregister_module(registered_module).await {
        Ok(()) => println!("Module unregistered successfully."),
        Err(e) => eprintln!("Unregistration failed: {}", e),
    }
}
```

### `heartbeat`

Sends a health status update to the orchestrator.

- **Purpose**: Informs the orchestrator that the module is still alive and functioning.
- **Arguments**:
    - `module: &RegisteredModule`: The registered module instance.
    - `status: HealthStatus`: The current health status of the module.
    - `details: Option<HashMap<String, String>>`: Optional additional health details.
- **Process**: Sends a `HeartbeatRequest` and awaits a `HeartbeatResponse`.
- **Returns**: `Result<HealthStatus, RegistrationError>` (the orchestrator's perspective on the module's health).

**Example**:
```rust
use pywatt_sdk::services::registration::{heartbeat, HealthStatus, RegisteredModule};
use std::collections::HashMap;

async fn send_heartbeat(registered_module: &RegisteredModule) {
    let mut health_details = HashMap::new();
    health_details.insert("cpu_load".to_string(), "0.75".to_string());

    match heartbeat(registered_module, HealthStatus::Healthy, Some(health_details)).await {
        Ok(status_from_orchestrator) => {
            println!("Heartbeat successful. Orchestrator sees status: {:?}", status_from_orchestrator);
        }
        Err(e) => eprintln!("Heartbeat failed: {}", e),
    }
}
```

### `advertise_capabilities`

Advertises the module's capabilities to the orchestrator.

- **Purpose**: Informs the orchestrator about what the module can do (e.g., HTTP endpoints it serves, message types it handles).
- **Arguments**:
    - `module: &RegisteredModule`: The registered module instance.
    - `capabilities: Capabilities`: A description of the module's capabilities.
- **Process**: Sends a `CapabilitiesRequest` and awaits a `CapabilitiesResponse`.
- **Returns**: `Result<(), RegistrationError>`.

**Example**:
```rust
use pywatt_sdk::services::registration::{advertise_capabilities, Capabilities, Endpoint, RegisteredModule};

async fn advertise(registered_module: &RegisteredModule) {
    let caps = Capabilities::new()
        .with_http_endpoint("/api/v1/data", vec!["GET", "POST"])
        .with_message_type("process_image_request");
    // You can also add custom capabilities:
    // .with_capability("custom_feature_enabled", true).unwrap();

    match advertise_capabilities(registered_module, caps).await {
        Ok(()) => println!("Capabilities advertised successfully."),
        Err(e) => eprintln!("Failed to advertise capabilities: {}", e),
    }
}
```

### `start_heartbeat_loop`

Spawns a background Tokio task to send heartbeats periodically.

- **Purpose**: Automates the process of sending regular health updates.
- **Arguments**:
    - `module: RegisteredModule`: The registered module instance (consumed).
    - `interval: Duration`: The time interval between heartbeats.
    - `status_provider: F`: A closure `FnMut() -> (HealthStatus, Option<HashMap<String, String>>)` that returns the current health status and details for each heartbeat.
- **Returns**: `tokio::task::JoinHandle<()>` for the spawned task.

**Example**:
```rust
use pywatt_sdk::services::registration::{start_heartbeat_loop, HealthStatus, RegisteredModule};
use std::time::Duration;
use std::collections::HashMap;

fn setup_automatic_heartbeat(registered_module: RegisteredModule) {
    let heartbeat_interval = Duration::from_secs(30);

    let _heartbeat_task_handle = start_heartbeat_loop(
        registered_module, // Consumes the module
        heartbeat_interval,
        move || {
            // This closure will be called before each heartbeat
            // Implement logic here to determine the module's current health
            let current_status = HealthStatus::Healthy; // Example
            let mut current_details = HashMap::new();
            current_details.insert("queue_size".to_string(), "10".to_string());
            (current_status, Some(current_details))
        },
    );
    println!("Heartbeat loop started.");
    // The handle can be used to await or abort the task if needed.
}
```

## Data Models (`models.rs`)

This module defines the structures used for registration communication:

- **`ModuleInfo`**: Basic information about the module.
  - Fields: `name: String`, `version: String`, `description: String`, `id: Option<Uuid>`, `metadata: Option<HashMap<String, String>>`.
  - Builders: `new(name, version, description)`, `with_id(uuid)`, `with_metadata(key, value)`.
  ```rust
  use pywatt_sdk::services::registration::ModuleInfo;
  use uuid::Uuid;
  let info = ModuleInfo::new("MyMod", "1.0", "My test module")
      .with_id(Uuid::new_v4())
      .with_metadata("author", "PyWatt Team");
  ```

- **`Endpoint`**: Describes an HTTP endpoint provided by the module.
  - Fields: `path: String`, `methods: Vec<String>`, `auth: Option<String>`, `metadata: Option<HashMap<String, String>>`.
  - Builders: `new(path, methods)`, `with_auth(auth_scheme)`, `with_metadata(key, value)`.
  ```rust
  use pywatt_sdk::services::registration::Endpoint;
  let endpoint = Endpoint::new("/api/users", vec!["GET", "POST"])
      .with_auth("BearerToken");
  ```

- **`Capabilities`**: A collection of module's capabilities.
  - Fields: `endpoints: Vec<Endpoint>`, `message_types: Option<Vec<String>>`, `additional_capabilities: Option<HashMap<String, serde_json::Value>>`.
  - Builders: `new()`, `with_http_endpoint(path, methods)`, `with_message_type(type_name)`, `with_capability(key, value)`.
  ```rust
  use pywatt_sdk::services::registration::Capabilities;
  let caps = Capabilities::new()
      .with_http_endpoint("/status", vec!["GET"])
      .with_message_type("user_update_event");
  ```

- **`HealthStatus`**: Enum representing module health.
  - Variants: `Healthy`, `Degraded`, `Unhealthy`.

- **`RegisteredModule`**: Information about the module after successful registration.
  - Fields include: `id: Uuid`, `token: String`, `orchestrator_host: String`, `orchestrator_port: u16`, and the original `ModuleInfo`.

- **Request/Response Structs**: Each communication step has corresponding request and response structs (e.g., `RegistrationRequest`, `RegistrationResponse`, `HeartbeatRequest`, `HeartbeatResponse`, etc.), primarily used internally for serialization/deserialization.

## Error Handling

Operations within this module return `Result<T, RegistrationError>`. The `RegistrationError` enum covers various failure scenarios:

- `ConnectionError(String)`: Failed to establish TCP connection.
- `SerializationError(String)`: Failed to serialize/deserialize messages.
- `ChannelError(String)`: Error during message send/receive on the `TcpChannel`.
- `Timeout(Duration)`: Operation timed out waiting for a response.
- `Rejected(String)`: Orchestrator rejected the request (e.g., invalid token, module name taken).
- `ModuleNotFound(Uuid)`: Orchestrator could not find the specified module ID (relevant for operations after initial registration).
- `InvalidToken(String)`: The provided module token is invalid.
- **Capabilities**: List of `endpoints`, optional `message_types`, and `additional_capabilities`.
- **HealthStatus**: `Healthy`, `Degraded`, or `Unhealthy`.

## Internal Details

- Uses a `once_cell::sync::Lazy<Mutex<Registry>>` to manage active `TcpChannel` connections keyed by `Uuid`.
- Default timeout for all operations is 30 seconds (`DEFAULT_TIMEOUT`).
- Errors are defined in `RegistrationError`, covering connection, serialization, channel, timeout, and rejection cases.

## See Also

- [services README](../README.md)
