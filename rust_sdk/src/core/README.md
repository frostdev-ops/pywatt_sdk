# Core Module (`pywatt_sdk::core`)

This module forms the bedrock of the PyWatt SDK, providing the fundamental building blocks and essential services required for developing robust and feature-rich PyWatt modules in Rust. It encompasses critical functionalities such as module initialization and bootstrapping, comprehensive state management, a unified error handling system, configuration loading, and standardized logging.

## Purpose:

The `core` module aims to provide a robust, extensible, and developer-friendly foundation for building PyWatt modules. It abstracts away complex boilerplate associated with module lifecycle management, inter-process communication setup, secret handling, and state synchronization. By offering these pre-built components, it allows developers to concentrate on implementing the unique logic and features of their specific modules, accelerating development and ensuring consistency across the PyWatt ecosystem.

## Key Components:

### 1. `bootstrap.rs`: Module Initialization and Lifecycle Management

This file is central to a module's startup and operational lifecycle. It orchestrates the entire process of bringing a module online and connecting it with the PyWatt orchestrator.

-   **Core Functionality**:
    -   **`bootstrap_module` function**: The primary entry point for module initialization.
        -   **Parameters**:
            -   `secret_keys: Vec<String>`: A list of environment secret names that the module needs to fetch upon startup.
            -   `endpoints: Vec<AnnouncedEndpoint>`: A list of HTTP/WebSocket endpoints that the module exposes, which will be announced to the orchestrator.
            -   `state_builder: F`: A closure that takes the `OrchestratorInit` data and fetched secrets to construct the module-specific user state (`T` in `AppState<T>`).
            -   `channel_preferences: Option<ChannelPreferences>`: Optional configuration to specify preferred communication channels (e.g., TCP, IPC) and their prioritization.
        -   **Process**:
            1.  Initializes logging (via `crate::core::logging::init_module()`) and secret redaction.
            2.  Performs the initial handshake with the orchestrator (using `read_init`).
            3.  Sets up the `SecretClient` (using `get_module_secret_client`) and fetches the initial set of required secrets.
            4.  Builds the `AppState<T>` by invoking the provided `state_builder`.
            5.  Initializes communication channels (TCP via `setup_tcp_channel_from_config`, IPC via `setup_ipc_channel_from_config` if the feature is enabled) based on orchestrator-provided configurations and module preferences.
            6.  Announces the module's presence and its exposed `endpoints` to the orchestrator (using `send_announce`).
            7.  Spawns independent background tasks (`tcp_message_processing_task`, `ipc_message_processing_task`) for each active communication channel to handle incoming messages from the orchestrator.
        -   **Returns**: `Result<(AppState<T>, JoinHandle<()>), BootstrapError>`, providing the initialized application state and a join handle for the main IPC processing loop.
    -   **`bootstrap_module_legacy` function**: A backward-compatible version of `bootstrap_module` that uses default channel preferences.

-   **Message Processing Tasks**:
    -   Functions like `tcp_message_processing_task`, `ipc_message_processing_task`, and the shared `process_orchestrator_message` logic are responsible for continuously listening on their respective channels.
    -   They decode incoming `EncodedMessage`s into `OrchestratorToModule` variants and handle them accordingly:
        -   `OrchestratorToModule::Heartbeat`: Responds with a `ModuleToOrchestrator::HeartbeatAck`.
        -   `OrchestratorToModule::Shutdown`: Signals the module to terminate.
        -   `OrchestratorToModule::RoutedModuleResponse`: Forwards responses from other modules to the correct pending internal request.
        -   `OrchestratorToModule::RoutedModuleMessage`: Delivers messages from other modules to registered handlers within the current module.
        -   `OrchestratorToModule::HttpRequest`: Processes HTTP requests received from the orchestrator (e.g., over TCP as a transport).

-   **Error Handling**:
    -   `BootstrapError` enum: Defines errors specific to the bootstrapping process, such as `Init` (handshake failure), `Secret` (secret client error), `Announce` (announcement failure), `RequiredChannelFailed`, and `NoChannelsAvailable`.

-   **Helper Utilities**:
    -   `setup_tcp_channel_from_config` and `setup_ipc_channel_from_config`: Internal helpers to establish TCP and IPC communication channels based on configuration provided by the orchestrator.
    -   `TcpChannelExt` trait: Extends `TcpChannel` with methods like `is_permanently_closed` and `try_reconnect`.
    -   `AppStateExt<T>` trait: Extends `AppState<T>` with methods to `register_module_message_handler` and `remove_module_message_handler` for module-to-module communication.

### 2. `state.rs`: Application State Management

This file defines the structures responsible for holding and managing the shared state of a PyWatt module.

-   **`AppConfig` Struct**:
    -   Holds various application-level configurations.
    -   **Fields include**:
        -   `message_format_primary: Option<EncodingFormat>`: Preferred encoding for outgoing messages (e.g., JSON, Bincode).
        -   `message_format_secondary: Option<EncodingFormat>`: Fallback encoding format.
        -   `ipc_timeout_ms: Option<u64>`: Timeout for IPC requests.
        -   `ipc_only: bool`: If true, the module operates only via IPC, without TCP.
        -   `enable_advanced_features: bool`: A flag to enable/disable advanced SDK features.
        -   Configurations for advanced features: `routing_config`, `failover_config`, `sla_config`, `alert_config`, `stream_config`.

-   **`AppState<T>` Struct**:
    -   The central struct for shared application state, generic over `T` (user-defined state).
    -   **Core Fields**:
        -   `module_id: String`: The unique identifier for the module.
        -   `orchestrator_api: String`: The base URL for the orchestrator's API.
        -   `secret_client: Arc<SecretClient>`: An Arc-wrapped client for interacting with the secret management system.
        -   `user_state: T`: The module-specific custom state.
        -   `config: Option<AppConfig>`: The application's configuration.
    -   **Communication Fields**:
        -   `internal_messaging_client: Option<InternalMessagingClient>`: Client for sending messages to other modules.
        -   `pending_internal_responses: Option<PendingInternalResponses>`: Stores handlers for responses to internal messages.
        -   `tcp_channel: Option<Arc<TcpChannel>>`: The TCP communication channel to the orchestrator.
        -   `ipc_channel: Option<Arc<IpcChannel>>` (feature-gated): The IPC communication channel.
        -   `tcp_capabilities`, `ipc_capabilities: ChannelCapabilities`: Describe features supported by each channel.
        -   `module_message_handlers: Option<Arc<Mutex<HashMap<String, ModuleMessageHandler>>>>`: Stores handlers for incoming module-to-module messages, keyed by source module ID.
    -   **Advanced Feature Components** (typically initialized if `enable_advanced_features` is true):
        -   `channel_router: Option<Arc<ChannelRouter>>`: Smart routing engine for selecting optimal communication channels.
        -   `failover_manager: Option<Arc<FailoverManager>>`: Manages automatic failover between channels.
        -   `performance_monitoring: Option<Arc<PerformanceMonitoringSystem>>`: Collects and reports on channel performance and SLA compliance.
        -   `priority_queue: Option<Arc<PriorityMessageQueue>>`: A queue for prioritizing outgoing messages.
        -   `request_multiplexer: Option<Arc<RequestMultiplexer>>`: Manages concurrent requests and responses.
    -   **Key Methods**:
        -   `new(...)`: Basic constructor.
        -   `with_advanced_features(...)`: Constructor that also initializes advanced feature components based on `AppConfig`.
        -   Accessors for core fields like `module_id()`, `orchestrator_api()`, `secret_client()`, `custom()` (for user_state).
        -   `send_message(...)`: Sends an `EncodedMessage` using the best available channel, potentially leveraging the `ChannelRouter` and `FailoverManager`.
        -   `send_message_via_channel(...)`: Sends a message via a specifically chosen `ChannelType`.
        -   `send_request(...)`: Sends a request and awaits a response, potentially using the `RequestMultiplexer`.
        -   Channel introspection: `available_channels()`, `channel_capabilities()`, `has_channel()`, `channel_health()`, `recommend_channel()`.
        -   Performance and Routing: `get_performance_metrics()`, `get_sla_status()`, `update_routing_matrix()`, `get_routing_matrix()`.
        -   `set_advanced_features_enabled()`: Allows toggling advanced features at runtime.

-   **`ModuleMessageHandler` Type Alias**:
    -   Defines the signature for functions that handle messages received directly from other modules: `Arc<dyn Fn(String, uuid::Uuid, EncodedMessage) -> Pin<Box<dyn Future<Output = Result<(), Error>> + Send>> + Send + Sync>`.

### 3. `error.rs`: Unified Error Handling

This file establishes a consistent and comprehensive error handling strategy for the SDK.

-   **`Error` Enum**:
    -   The primary, unified error type for the SDK. It uses `thiserror::Error` for easy derivation of `std::error::Error`.
    -   **Variants consolidate errors from various SDK components**:
        -   `Bootstrap(#[from] BootstrapError)`: Errors during module startup.
        -   `Init(#[from] InitError)`: Handshake errors.
        -   `Secret(#[from] ModuleSecretError)`: Secret management errors.
        -   `Announce(#[from] AnnounceError)`: Module announcement errors.
        -   `Axum(#[from] HyperError)`: Errors from the underlying HTTP library (Hyper, via Axum).
        -   `Config(#[from] ConfigError)`: Configuration-related errors.
        -   `Metrics(#[from] MetricsError)` (feature-gated): Metrics collection or reporting errors.
        -   `Database(#[from] DatabaseError)` (feature-gated): Database interaction errors.
        -   `Cache(#[from] CacheError)` (feature-gated): Caching operation errors.
        -   `Io(#[from] io::Error)`: Standard I/O errors.
        -   `ModelManager(#[from] ModelManagerError)` (feature-gated): Errors from the model manager component.
        -   `Network(#[from] NetworkError)`: Low-level network communication errors.
        -   `Registration(#[from] RegistrationError)`: Module registration errors.
        -   `HttpTcp(#[from] HttpTcpError)`: Errors specific to HTTP-over-TCP communication.
        -   `Server(#[from] ServerError)`: Errors from the SDK's internal server components.
        -   `StringError(String)`: A general-purpose error variant for simple string-based errors.
    -   Implements `From<String>` to allow easy conversion of string errors into `Error::StringError`.

-   **`Result<T>` Type Alias**:
    -   A convenience alias: `pub type Result<T> = std::result::Result<T, Error>;`.

-   **Specific Error Enums**:
    -   `MetricsError` (feature-gated): Defines errors like `Encode` (Prometheus encoding error) and `ResponseBuild` (HTTP response construction error for metrics).
    -   `ConfigError`: Defines errors like `MissingEnvVar(String)` and `Invalid(String)` for configuration issues. Implements `From<&str>` for easy conversion.

### 4. `logging.rs`: Standardized Logging Utilities

Provides utilities for setting up consistent, structured logging across PyWatt modules.

-   **`init_module()` function**:
    -   **Crucial First Step**: This function **must** be the first call in a module's `main()` function, before any other SDK operations, logging, or secret access.
    -   **Functionality**: It initializes the global `tracing` subscriber. Internally, it delegates to `crate::secret_client::init_logging()`.
    -   **Features**:
        -   Sets up logging to output in JSON format to `stderr`.
        -   Integrates with `RUST_LOG` environment variable for log level filtering.
        -   Automatically redacts any secrets that have been registered with the `SecretClient` via `register_secret_for_redaction`, preventing accidental exposure of sensitive data in logs.

-   **Re-exports**:
    -   `safe_log!`: Re-exports a macro (likely defined elsewhere in the `pywatt_sdk` crate, possibly in `pywatt_macros`) designed for logging potentially sensitive information in a way that ensures it's processed by the redaction layer if necessary.

### 5. `config.rs`: SDK Configuration (Placeholder)

This file is designated for defining SDK-level and potentially module-specific static configuration structures.

-   **Current Status**: As of the last review, this file primarily contains a module-level documentation comment indicating its intended purpose: `//! SDK configuration module. Configuration for the PyWatt SDK. Define structures like AppConfig and loading logic here.`
-   **Intended Use**: This would be the place to define structs that are deserialized from configuration files (e.g., TOML, YAML) or environment variables, providing static settings for the SDK's behavior or for the module itself. Note that `AppConfig` is currently defined in `state.rs` but could conceptually fit here or be part of a larger configuration structure defined here.

### 6. `mod.rs`: Core Module Declaration

This is the standard Rust module declaration file for the `pywatt_sdk::core` module.

-   **Functionality**:
    -   It contains `pub mod` statements for each of the submodules within `core`:
        -   `pub mod bootstrap;`
        -   `pub mod state;`
        -   `pub mod error;`
        -   `pub mod config;`
        -   `pub mod logging;`
    -   This makes the public items (structs, enums, functions, traits) from these submodules accessible under the `pywatt_sdk::core` namespace (e.g., `pywatt_sdk::core::bootstrap::bootstrap_module`, `pywatt_sdk::core::state::AppState`).
    -   Includes a module-level documentation comment: `//! Fundamental SDK building blocks: init, state, errors, config, logging.`
