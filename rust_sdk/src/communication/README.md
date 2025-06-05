# PyWatt SDK: Communication Module

The `communication` module is a cornerstone of the PyWatt Rust SDK, providing a comprehensive suite of tools for establishing and managing inter-process communication (IPC) and network connections between PyWatt modules and the orchestrator. It handles message passing, various transport channels, HTTP protocol support over these channels, and essential utilities like failover, metrics, and routing.

## Core Concepts

- **Message-Oriented**: Communication is primarily based on structured messages, defined in `message.rs`.
- **Channel Abstraction**: The `MessageChannel` trait (in `mod.rs`) allows for different underlying communication mechanisms (e.g., TCP, IPC) to be used interchangeably.
- **Asynchronous Operations**: Leverages Rust's `async/await` for non-blocking I/O and efficient concurrency.

## Top-Level Modules

- **`mod.rs`**: The main entry point for the communication module.
    - Defines the central **`MessageChannel` trait**, which abstracts over different communication channel implementations. This trait requires methods like `send(EncodedMessage)`, `receive() -> EncodedMessage`, `state() -> ConnectionState`, `connect()`, and `disconnect()`.
    - Introduces **`ChannelType`** (enum for `Tcp` or `Ipc`), **`ChannelPreferences`** (struct to configure channel usage, e.g., `tcp_only()`, `prefer_ipc()`, `enable_fallback`), and **`ChannelCapabilities`** (struct detailing features like `module_messaging`, `http_proxy`, `streaming`, `max_message_size`, with presets like `tcp_standard()` and `ipc_standard()`).
    - Re-exports key components from other files, including `PortNegotiationManager`, `TcpChannel`, and `IpcChannel` (when the `ipc_channel` feature is enabled).

- **`message.rs`**: Defines standardized structures for message encoding and decoding.
    - **`Message<T>`**: A generic wrapper for typed message content, including metadata.
    - **`EncodedMessage`**: Represents a message that has been serialized (e.g., into JSON or Bincode) and is ready for transmission, often containing a payload as `Vec<u8>`.
    - **`MessageMetadata`**: Contains common message attributes like `message_id`, `correlation_id`, `timestamp`, and `content_type`.
    - Ensures consistent data exchange and error handling (`MessageResult<T>`, `MessageError`) across communication links. Supports various encoding formats.

- **`ipc.rs`**: Manages core Inter-Process Communication (IPC) with the PyWatt orchestrator, primarily using stdin for input and stdout for output.
    - **`IpcManager`**: A central struct (though often used via its associated functions) for handling communication. It doesn't manage socket connections itself but processes messages.
    - **Message Processing**: The `process_ipc_messages()` function reads lines from stdin, parses them as `OrchestratorToModule` messages (e.g., `SecretResponse`, `ShutdownCommand`, `IpcHttpRequest`, `IpcPortNegotiationResponse`), and acts accordingly. For example, it delegates secret handling to `SecretClient` and broadcasts `IpcHttpRequest` messages.
    - **Outgoing Requests**: The `send_request()` function serializes a request (e.g., `ServiceRequest`, `GetSecretRequest`) into a `ModuleToOrchestrator` message, sends it over stdout, and uses a `oneshot` channel to await a response correlated by a request ID.
    - **Global Channels**: Utilizes global static `lazy_static` variables for managing:
        - `IPC_CHANNEL`: For queuing outgoing requests to be written to stdout.
        - `STDOUT_WRITER`: A `tokio::sync::Mutex` around `io::Stdout` to serialize writes.
        - `HTTP_CHANNEL`: For broadcasting `IpcHttpRequest` received from the orchestrator to internal subscribers (like `HttpIpcRouter`).
    - **Port Negotiation**: Interacts with `PortNegotiationManager` for requesting ports, though some `IpcManager` methods related to this are for backward compatibility as the manager handles direct communication.

- **`ipc_channel.rs`**: Implements the `MessageChannel` trait for IPC using Unix Domain Sockets. This is a primary mechanism for local, efficient communication between a module and the orchestrator if a dedicated socket path is provided via `InitBlob`.
    - **`IpcChannel`**: The main struct, holding an `IpcConnectionConfig`, an `Arc<Mutex<Option<UnixStream>>>` for the socket, and connection state.
    - **`IpcConnectionConfig`**: Configures the socket path, connection timeout, and `ReconnectPolicy` (e.g., `None`, `FixedInterval`, `ExponentialBackoff`).
    - **Connection Handling**: Manages connecting to the Unix Domain Socket, with methods like `connect_with_retry()` and `try_connect()`.
    - **Message Framing**: Implements `send` and `receive` by writing and reading length-prefixed messages to/from the `UnixStream` to ensure proper message delineation.

- **`tcp_channel.rs`**: Implements the `MessageChannel` trait for TCP-based communication.
    - **`TcpChannel`**: The main struct, holding `TcpConnectionConfig`, an `Arc<Mutex<Option<TcpStream>>>` (or a TLS equivalent), and connection state.
    - Manages TCP connections, including TLS security options (`TlsConfig`) and automatic reconnection logic based on `ReconnectPolicy`.
    - Implements `send` and `receive` by writing/reading length-prefixed messages.

- **`tcp_types.rs`**: Contains type definitions specific to TCP communication.
    - **`TcpConnectionConfig`**: Defines target address, TLS settings, timeout, and `ReconnectPolicy`.
    - **`ReconnectPolicy`**: Enum for different reconnection strategies (None, FixedInterval, ExponentialBackoff).
    - **`ConnectionState`**: Enum representing the current state of a connection (e.g., `Disconnected`, `Connecting`, `Connected`, `Failed`).
    - **`NetworkError`**: Custom error type for network-related issues.

- **`failover.rs`**: Implements advanced failover mechanisms to enhance communication reliability.
    - **`CircuitBreaker`**: A key component that monitors communication health. It tracks failures and successes, and can "open" to prevent further requests to an unhealthy service for a period, then transition to "half-open" to test recovery, and finally "close" on success. Configurable with thresholds and reset durations.
    - Includes retry strategies and performance optimizations for handling transient network issues.

- **`metrics.rs`**: Provides `ChannelMetrics` for collecting and monitoring performance metrics of communication channels.
    - Tracks latency (e.g., average, p95, p99), throughput (messages/sec, bytes/sec), error rates, and connection status.
    - Useful for Service Level Agreement (SLA) monitoring and identifying performance bottlenecks.

- **`routing.rs`**: Implements intelligent message routing capabilities, especially relevant if a module has multiple available communication channels.
    - **`RoutingMatrix`**: Allows defining channel preferences based on `MessageCharacteristics` (e.g., size, type, priority) and current channel performance data (from `ChannelMetrics`).
    - **`ChannelRouter`**: Uses the `RoutingMatrix` to make a `RoutingDecision` on which channel to use for an outgoing message.
    - Supports dynamic routing adjustments based on changing network conditions.

- **`streaming.rs`**: Supports efficient streaming of large data payloads over communication channels.
    - **`StreamConfig`**: Configuration for stream behavior (chunk size, flow control).
    - Handles chunked message transmission, ensuring large messages don't block channels or exceed size limits.
    - Implements flow control mechanisms to prevent overwhelming receivers.
    - Can support various message patterns like publish/subscribe and request multiplexing over streams.

- **`ipc_port_negotiation.rs`**: Provides utilities for modules to dynamically request and allocate network ports from the orchestrator, typically for exposing HTTP servers.
    - **`PortNegotiationManager`**: The primary struct for managing port requests.
    - **Mechanism**: Sends `IpcPortNegotiation` requests (as part of `ModuleToOrchestrator` messages via stdout) to the orchestrator and listens for `IpcPortNegotiationResponse` messages (via stdin, processed by `IpcManager` and relayed, or directly if this manager evolves to handle stdin).
    - **Features**:
        - Requesting a specific port or any available port.
        - Timeout handling and retry logic for requests.
        - **Circuit Breaker**: Implements a circuit breaker (`CircuitBreakerState`, `CircuitBreakerStatus`) to handle persistent failures in communicating with the orchestrator for port allocation.
        - **Fallback Ports**: If the circuit breaker is open or communication repeatedly fails, it can generate a port from a predefined fallback range to allow the module to start, albeit with a potentially unadvertised port.
    - **State Management**: Uses global `lazy_static` variables to store the currently allocated port (`ALLOCATED_PORT`), response channels (`PORT_RESPONSE_CHANNEL`), negotiation state (`PORT_NEGOTIATION_STATE`), and circuit breaker status (`CIRCUIT_BREAKER`).

## Subdirectories

(The descriptions for subdirectories `ipc_types`, `http_ipc`, and `http_tcp` will remain largely the same as they were recently updated and are quite detailed.)

### 1. `ipc_types`
This directory contains fundamental data structures and type definitions used throughout the IPC and communication layers.
- **`ipc_types/mod.rs`**: Defines crucial shared types:
    - `ListenAddress`: Enum specifying whether a module listens on a TCP socket or a Unix domain socket.
    - `TcpChannelConfig`, `IpcChannelConfig`: Configuration structures for TCP and IPC channels, respectively.
    - `SecurityLevel`: Enum defining security requirements (None, Token, mTLS).
    - `InitBlob`: Data sent from the orchestrator to a module upon initialization, containing essential configuration like module ID, API endpoints, and channel settings.
    - `AnnounceBlob`: Data sent from a module to the orchestrator after it has successfully started and bound to its listen address, detailing its exposed endpoints.
    - `EndpointAnnounce`: Describes a single HTTP/WebSocket endpoint provided by a module.
    - `GetSecretRequest`, `GetSecretResponse`: Structures for requesting and receiving secrets.
    - `IpcHttpRequest`, `IpcHttpResponse`: Core structures representing HTTP requests and responses when tunneled over an IPC mechanism.
    - `IpcPortNegotiation`, `IpcPortNegotiationResponse`: Structures for the port negotiation protocol.

### 2. `http_ipc`
This subdirectory provides utilities for handling HTTP semantics (requests, responses, routing) specifically over the established IPC channels (like Unix Domain Sockets).
- **`http_ipc/improved_mod.rs`** (preferred over `mod.rs`):
    - Implements an `HttpIpcRouter` for routing HTTP requests received via IPC to appropriate handlers within the module.
    - Defines `ApiResponse<T>` as a standard structure for JSON API responses.
    - Manages `HTTP_REQUEST_CHANNEL` and `HTTP_RESPONSE_CHANNEL` (broadcast channels) for decoupling HTTP request reception and response sending over IPC.
    - Includes `HttpIpcMetrics` for monitoring performance of HTTP-over-IPC interactions.
    - Provides `subscribe_http_requests()` and `send_http_response()` for interacting with the HTTP-IPC layer.
- **`http_ipc/improved_result.rs`** (preferred over `result.rs`):
    - Defines `HttpIpcError`, a specialized error enum for issues arising in the HTTP-over-IPC layer.
    - Provides `HttpResult<T>`, a type alias for `Result<T, HttpIpcError>`.
    - Offers helper functions like `parse_json_body()` for safe deserialization of request bodies and `json_response()`, `success()`, `error_response()` for constructing standardized `IpcHttpResponse` objects.

### 3. `http_tcp`
This subdirectory focuses on enabling HTTP communication directly over TCP connections, allowing modules to act as HTTP clients or servers using TCP as the transport.
- **`http_tcp/mod.rs`**:
    - Serves as the entry point for the `http_tcp` module.
    - Re-exports key components like `HttpTcpRouter` and `HttpTcpClient`.
    - Defines `HttpTcpRequest` and `HttpTcpResponse` structures, which are similar to their IPC counterparts but tailored for direct TCP transport. These include methods for header manipulation, body access, and query parameter parsing.
    - Also defines an `ApiResponse<T>` structure (similar to the one in `http_ipc`) and helper functions for creating JSON responses (`json_response`, `success`, `error_response`, `not_found`, etc.).
- **`http_tcp/client.rs`**:
    - Implements `HttpTcpClient`, a client for making outbound HTTP requests to other services or modules over TCP.
    - Provides a `RequestBuilder` for fluently constructing HTTP requests (setting method, URI, headers, body, timeout, retries).
    - Defines `HttpClientError` for errors specific to the HTTP/TCP client operations and `HttpClientResult<T>`.
- **`http_tcp/router.rs`**:
    - Implements `HttpTcpRouter`, enabling a module to define HTTP routes and handlers for incoming requests over a TCP connection. This allows a module to expose an HTTP API directly via TCP.
    - Defines `HttpTcpError` (can be different from client errors), `HttpTcpResult<T>`, `HandlerFn` (type for route handlers), and `Route<S>` (struct for a route entry).
    - Includes the `start_http_server` function, which likely uses the router to listen for and process HTTP requests on a TCP socket, integrating with module registration and health checks.

## Usage

Modules will typically interact with this `communication` module by:
1.  Initializing one or more `MessageChannel` implementations (e.g., `TcpChannel`, `IpcChannel`) based on the `InitBlob` received from the orchestrator.
2.  Using these channels to send and receive `Message<T>` instances (often as `EncodedMessage`).
3.  If exposing an HTTP API, using `HttpIpcRouter` (for IPC-based HTTP, receiving requests via `IpcManager`) or `HttpTcpRouter` (for direct TCP-based HTTP, using `start_http_server` which leverages `PortNegotiationManager`).
4.  If acting as an HTTP client, using `HttpTcpClient` to make requests.
5.  Leveraging utilities for metrics, failover, streaming, and port negotiation as needed.

This module aims to provide robust, flexible, and performant communication capabilities essential for the distributed nature of PyWatt applications.
