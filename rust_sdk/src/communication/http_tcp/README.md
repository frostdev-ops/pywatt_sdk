# HTTP-over-TCP Communication (`http_tcp`)

This module provides the building blocks for enabling HTTP communication directly over TCP connections within the PyWatt SDK. It allows modules to act as HTTP clients, making requests to other services, or as HTTP servers, exposing APIs over TCP.

## Key Components

### 1. `mod.rs`
This is the main entry point for the `http_tcp` module.
- **Purpose**: It aggregates and re-exports the core functionalities from `client.rs` and `router.rs`.
- **Core Structures**:
    - `HttpTcpRequest`: Represents an HTTP request to be sent or received over TCP. It includes fields for `request_id`, `method`, `uri`, `headers`, and an optional `body`. Provides helper methods for accessing headers, query parameters, and the request path.
    - `HttpTcpResponse`: Represents an HTTP response received or to be sent over TCP. It includes `request_id` (to correlate with the request), `status_code`, `headers`, and an optional `body`. Offers methods for checking success/error status codes and accessing the body as a string or JSON.
    - `ApiResponse<T>`: A generic structure for standardizing JSON API responses, containing `status`, optional `data`, and an optional `message`.
- **Helper Functions**: Provides utility functions for creating common `HttpTcpResponse` instances, such as `json_response()`, `success()`, `error_response()`, and `not_found()`.

### 2. `client.rs`
This file implements the client-side logic for making HTTP requests over TCP.
- **`HttpTcpClient`**: The primary struct for initiating outbound HTTP requests. (While the struct itself isn't explicitly detailed in the provided snippet, its role is inferred from the context of a client module and the `RequestBuilder`).
- **`RequestBuilder`**: A builder pattern implementation for constructing `HttpTcpRequest` objects fluently.
    - Allows setting the HTTP `method` and `uri`.
    - Methods for adding `header()`, `headers()`, `query()` parameters, and `queries()`.
    - Supports setting the request `body()` directly or as `json()` (which also sets the `Content-Type` header).
    - Configuration for `timeout()` and `retries()` for the request.
    - Internally builds the full URI with query parameters and constructs the `HttpTcpRequest`.
    - The `send()` method executes the request over the associated `TcpChannel`, handling connection checks, message wrapping, sending, receiving the response, and deserialization. It incorporates timeout and retry logic.
- **`HttpClientError`**: An enum defining errors specific to the HTTP/TCP client, such as `ConnectionError`, `Timeout`, `ResponseError` (with status and message), `SerializationError`, `IoError`, and `SdkError`.
- **`HttpClientResult<T>`**: A type alias for `Result<T, HttpClientError>`.

### 3. `router.rs`
This file implements the server-side logic for routing and handling incoming HTTP requests over TCP.
- **`HttpTcpRouter<S>`**: A generic router that allows modules to define routes and associate them with handler functions. The `S` type parameter typically represents shared application state.
    - `route()`: Method to add a new route, specifying the HTTP method, path, and an asynchronous handler function.
    - `not_found_handler()`: Allows setting a custom handler for requests that don't match any defined routes.
    - `methods()`: A convenience method to register the same handler for multiple HTTP methods on a given path.
    - `handle_request()`: The core method that takes an incoming `HttpTcpRequest` and the shared state, finds the matching route, executes its handler, and returns an `HttpTcpResponse`. If no route matches, it uses the `not_found_handler` or a default "Not Found" response.
- **`HandlerFn<S>`**: A type alias for the asynchronous handler functions, which take an `HttpTcpRequest` and an `Arc<S>` (shared state) and return an `HttpTcpResult<HttpTcpResponse>`.
- **`Route<S>`**: A struct representing a single route, containing the `method`, `path`, and `handler`.
- **`HttpTcpError`**: An enum for errors specific to the HTTP/TCP router and server operations (can differ from client-side errors). Includes variants like `InvalidRequest`, `NotFound`, `Internal`, `Sdk`, `Json`, `Io`, `Timeout`.
- **`HttpTcpResult<T>`**: A type alias for `Result<T, HttpTcpError>`.
- **`start_http_server()`**: A crucial function that likely initializes the TCP listener, integrates with the `HttpTcpRouter` to process incoming connections and requests, and manages the server lifecycle. It's also responsible for advertising the module's capabilities (endpoints) and starting a heartbeat loop for health monitoring.

## Usage Flow

- **Client-Side**:
    1. Obtain an instance of `TcpChannel`.
    2. Use `HttpTcpClient::new(channel)` (or similar constructor not shown but implied) to create a client.
    3. Construct a request using `client.get(uri)`, `client.post(uri)`, etc., which returns a `RequestBuilder`.
    4. Configure the request using the `RequestBuilder` methods (headers, body, timeout).
    5. Call `send()` on the builder to execute the request and receive an `HttpTcpResponse`.

- **Server-Side**:
    1. Create an instance of `HttpTcpRouter<S>`.
    2. Define routes using `router.route(...)` or `router.methods(...)`, providing handler functions.
    3. Optionally, set a custom `router.not_found_handler(...)`.
    4. Call `start_http_server()` with the router, connection configuration, and module registration details to start listening for and handling requests.

This module facilitates robust HTTP communication over TCP, forming a vital part of the PyWatt SDK's networking capabilities.
