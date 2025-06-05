# IPC Types (`ipc_types`)

The `ipc_types` module defines a set of fundamental data structures and type definitions that are shared and used across various parts of the PyWatt SDK's Inter-Process Communication (IPC) and higher-level communication layers (like `http_ipc` and `http_tcp`). These types ensure consistency in how configuration, requests, and responses are represented.

## Key Data Structures

-   **`ListenAddress`**: An enum that specifies the type of address a module listens on.
    -   `Tcp(SocketAddr)`: For listening on a TCP network address and port.
    -   `Unix(PathBuf)`: For listening on a Unix Domain Socket path.

-   **`TcpChannelConfig`**: Configuration for a TCP-based communication channel.
    -   `address: SocketAddr`: The target TCP address to connect to.
    -   `tls_enabled: bool`: Indicates if TLS security should be used for this channel.
    -   `required: bool`: Specifies if this channel is mandatory for the module's operation.

-   **`IpcChannelConfig`**: Configuration for an IPC channel using Unix Domain Sockets.
    -   `socket_path: PathBuf`: The file system path to the Unix Domain Socket.
    -   `required: bool`: Specifies if this channel is mandatory.

-   **`SecurityLevel`**: An enum defining the security level required or implemented for a communication channel.
    -   `None`: No specific security measures.
    -   `Token`: Authentication based on a shared token.
    -   `Mtls`: Mutual TLS authentication for strong, certificate-based security.

-   **`InitBlob`**: A crucial structure sent from the PyWatt orchestrator to a module during its initialization phase.
    -   `orchestrator_api: String`: Endpoint for the orchestrator's API.
    -   `module_id: String`: Unique identifier for the module.
    -   `env: HashMap<String, String>`: Environment variables or initial configuration settings.
    -   `listen: ListenAddress`: The primary address the orchestrator has assigned or expects the module to listen on (can be legacy, with `tcp_channel` and `ipc_channel` being preferred for new designs).
    -   `tcp_channel: Option<TcpChannelConfig>`: Specific configuration if a TCP channel is to be used.
    -   `ipc_channel: Option<IpcChannelConfig>`: Specific configuration if an IPC channel (Unix socket) is to be used.
    -   `auth_token: Option<String>`: An authentication token, if applicable for `SecurityLevel::Token`.
    -   `security_level: SecurityLevel`: The security level expected for communications.

-   **`AnnounceBlob`**: Information sent from a module back to the orchestrator once the module has successfully started, bound its listener(s), and is ready to operate.
    -   `listen: String`: The actual address (e.g., "127.0.0.1:4102" or "/tmp/socket.sock") the module bound to.
    -   `endpoints: Vec<EndpointAnnounce>`: A list of all HTTP/WebSocket endpoints the module exposes.

-   **`EndpointAnnounce`**: Describes a single endpoint exposed by a module.
    -   `path: String`: The URL path for the endpoint (e.g., "/status").
    -   `methods: Vec<String>`: HTTP methods supported by this endpoint (e.g., "GET", "POST").
    -   `auth: Option<String>`: Optional information about authentication requirements for this specific endpoint.

-   **`GetSecretRequest`**: Used by a module to request a named secret from the orchestrator or a secret management service.
    -   `name: String`: The name of the secret to retrieve.

-   **`GetSecretResponse`**: The response from the orchestrator containing the requested secret.
    -   `name: String`: The name of the secret.
    -   `value: Option<String>`: The secret's value, if found and accessible.
    -   `error: Option<String>`: An error message if the secret could not be retrieved.

-   **`IpcHttpRequest`**: Represents an HTTP request that is being tunneled over an IPC mechanism (rather than directly over TCP).
    -   `request_id: String`: A unique ID for tracking the request.
    -   `method: String`: The HTTP method (e.g., "GET", "POST").
    -   `uri: String`: The request URI (path and query string).
    -   `headers: HashMap<String, String>`: HTTP headers.
    -   `body: Option<Vec<u8>>`: The optional request body as raw bytes.

-   **`IpcHttpResponse`**: Represents an HTTP response to an `IpcHttpRequest`, also tunneled over IPC.
    -   `request_id: String`: Correlates with the `IpcHttpRequest`.
    -   `status_code: u16`: The HTTP status code.
    -   `headers: HashMap<String, String>`: HTTP headers.
    -   `body: Option<Vec<u8>>`: The optional response body as raw bytes.

-   **`EncodedMessage`**: (Imported from `crate::message`) While not defined directly in `ipc_types/mod.rs`, its presence as an import suggests it's a foundational type for messages passed over IPC, likely representing a serialized `Message<T>`.

## Purpose and Usage

The types defined in this module are essential for:
-   **Module Initialization**: `InitBlob` provides modules with all necessary startup configuration from the orchestrator.
-   **Service Discovery**: `AnnounceBlob` and `EndpointAnnounce` allow modules to register their services and endpoints with the orchestrator.
-   **Secure Communication**: `SecurityLevel`, `auth_token`, and channel configurations facilitate secure connections.
-   **Secret Management**: `GetSecretRequest` and `GetSecretResponse` provide a standardized way for modules to access sensitive information.
-   **HTTP-over-IPC**: `IpcHttpRequest` and `IpcHttpResponse` enable using HTTP semantics over non-HTTP IPC channels, which is handled by the `http_ipc` module.

By centralizing these core type definitions, `ipc_types` promotes consistency and interoperability between different components of the PyWatt SDK and modules developed using it.
