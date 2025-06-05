# HTTP-over-IPC Communication (`http_ipc`)

The `http_ipc` module enables PyWatt modules to handle HTTP-style requests and responses that are tunneled over an existing Inter-Process Communication (IPC) channel, such as a Unix Domain Socket. This is distinct from `http_tcp` which handles HTTP directly over TCP. This approach is useful when the primary communication with the orchestrator or other local modules is already established via IPC, and HTTP semantics are desired for structuring those interactions.

The documentation below refers to `improved_mod.rs` and `improved_result.rs` as they contain enhancements over the original `mod.rs` and `result.rs`.

## Key Components

### 1. `improved_mod.rs` (Preferred over `mod.rs`)
This file provides the core routing and message handling logic for HTTP-over-IPC.
- **Purpose**: To receive `IpcHttpRequest` objects from an IPC channel, route them to appropriate handlers, and send back `IpcHttpResponse` objects over the same or a related IPC channel.
- **`HttpIpcRouter<S>`**: A generic router for HTTP requests received via IPC.
    - `route()`: Adds a route, mapping an HTTP method and path to a specific asynchronous handler function.
    - `not_found_handler()`: Allows defining a custom handler for requests that don't match any routes.
    - `middleware()`: Supports adding middleware that can process or modify requests before they reach the handlers.
    - `handle_request()`: Processes an incoming `IpcHttpRequest`, applies middleware, finds the matching handler, executes it, and generates an `IpcHttpResponse`.
- **`HandlerFn<S>`**: A type alias for asynchronous handler functions. These functions take an `IpcHttpRequest` and shared state `Arc<S>`, returning an `HttpResult<IpcHttpResponse>`.
- **`ApiResponse<T>`**: A standard generic structure for JSON API responses, containing `status`, optional `data`, and an optional `message`. This helps maintain consistency in response formats.
- **Broadcast Channels**:
    - `HTTP_REQUEST_CHANNEL`: A `tokio::sync::broadcast` channel used to distribute incoming `IpcHttpRequest` messages to one or more subscribers (e.g., the router).
    - `HTTP_RESPONSE_CHANNEL`: A `tokio::sync::broadcast` channel for sending `IpcHttpResponse` messages back, potentially to a component that forwards them over the actual IPC socket.
    - These channels have increased capacity and are initialized lazily using `once_cell::sync::Lazy`.
- **`HttpIpcMetrics`**: A struct for collecting performance metrics related to HTTP-over-IPC, such as `requests_received`, `responses_sent`, `errors_encountered`, and `avg_response_time_ms`. A global instance (`HTTP_IPC_METRICS`) is provided.
- **Key Functions**:
    - `subscribe_http_requests()`: Allows components (like the router) to subscribe to the `HTTP_REQUEST_CHANNEL` to receive incoming HTTP requests.
    - `send_http_response()`: Sends an `IpcHttpResponse` through the `HTTP_RESPONSE_CHANNEL`. This function includes enhanced logging, metrics updates, and retry logic with backoff for improved reliability.

### 2. `improved_result.rs` (Preferred over `result.rs`)
This file defines the error types and result helpers for the HTTP-over-IPC system.
- **`HttpIpcError`**: A comprehensive enum for errors that can occur within the HTTP-over-IPC layer. Variants include:
    - `InvalidRequest`, `NotFound`, `Unauthorized`, `Forbidden`, `Internal`
    - `Sdk(crate::Error)`: For wrapping general SDK errors.
    - `Json(serde_json::Error)`: For JSON serialization/deserialization issues.
    - `Timeout`, `IpcCommunication`, `Other`.
    - It includes `From` implementations for `std::io::Error` and `tokio::time::error::Elapsed`.
- **`HttpResult<T>`**: A type alias for `std::result::Result<T, HttpIpcError>`.
- **Helper Functions**:
    - `parse_json_body()`: Safely parses a JSON request body from `Option<Vec<u8>>`. Includes detailed error reporting and trace logging of the raw JSON body (for small bodies) to aid debugging.
    - `json_response()`: Constructs an `IpcHttpResponse` with a JSON body from a serializable type `T`. It sets the `Content-Type` header to `application/json` and includes correlation headers like `X-Request-ID`.
    - `success()`, `created()`, `accepted()`: Convenience functions that use `json_response()` to create success responses with common HTTP status codes (200, 201, 202).
    - `error_response()`: Creates an `IpcHttpResponse` for error scenarios. It uses the `ApiResponse` structure to format the error message and can include an `X-Error-Code` header.

## Usage Flow

1.  A component (e.g., an IPC message listener in `ipc_channel.rs` or `ipc.rs`) receives raw messages from an IPC socket.
2.  If a message is identified as an HTTP request, it's deserialized into an `IpcHttpRequest` (defined in `ipc_types`).
3.  This `IpcHttpRequest` is then typically sent to the `HTTP_REQUEST_CHANNEL`.
4.  An `HttpIpcRouter` instance, subscribed to `HTTP_REQUEST_CHANNEL` via `subscribe_http_requests()`, receives the request.
5.  The router processes the request, applies any middleware, and dispatches it to the appropriate handler function based on its method and path.
6.  The handler function processes the request (potentially using `parse_json_body()` and shared state) and returns an `HttpResult<IpcHttpResponse>`. Helper functions like `success()` or `error_response()` are used to create the `IpcHttpResponse`.
7.  The `HttpIpcRouter` (or the component calling it) then uses `send_http_response()` to send the `IpcHttpResponse` to the `HTTP_RESPONSE_CHANNEL`.
8.  Another component, subscribed to `HTTP_RESPONSE_CHANNEL`, picks up the response, serializes it, and sends it back over the original IPC socket.

This module effectively bridges the gap between raw IPC messaging and the structured, familiar paradigm of HTTP, complete with routing, standardized responses, and error handling.
