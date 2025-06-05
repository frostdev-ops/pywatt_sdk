// Server module
use thiserror::Error;
#[cfg(feature = "ipc_channel")]
use crate::ipc::IpcManager;
use crate::ipc_types::{IpcHttpResponse, IpcPortNegotiation};
use axum::body::Body as AxumBody;
use axum::http::Request as AxumRequest;
use tower::util::ServiceExt;
use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex as StdMutex};
use http_body_util::BodyExt;
use tracing::{info, debug, warn, error};

// Global state to store pre-allocated port from InitBlob
lazy_static::lazy_static! {
    static ref PRE_ALLOCATED_PORT: Arc<StdMutex<Option<u16>>> = Arc::new(StdMutex::new(None));
}

/// Set the pre-allocated port from the InitBlob
pub fn set_pre_allocated_port(port: u16) {
    if let Ok(mut guard) = PRE_ALLOCATED_PORT.lock() {
        *guard = Some(port);
        debug!("Set pre-allocated port: {}", port);
    }
}

/// Get the pre-allocated port if available
pub fn get_pre_allocated_port() -> Option<u16> {
    PRE_ALLOCATED_PORT.lock().ok().and_then(|guard| *guard)
}

/// Errors that may occur during server bootstrap and run.
#[derive(Debug, Error)]
pub enum Error {
    /// IO error during socket operations.
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    /// Error during announcement.
    #[error("Announcement error: {0}")]
    Announce(String),
    
    /// Invalid configuration or state.
    #[error("Configuration error: {0}")]
    Config(String),
    
    /// Server error.
    #[error("Server error: {0}")]
    Server(String),

    /// Other error.
    #[error("Internal error: {0}")]
    Internal(Box<dyn std::error::Error + Send + Sync>),
}

/// Serve the given router over IPC (stdio) by subscribing to HTTP requests and responding via IPC.
#[cfg(feature = "ipc_channel")]
async fn serve_ipc(app: axum::Router) -> Result<(), Error> {
    // Subscribe to HTTP-over-IPC requests
    let manager = IpcManager::new();
    let mut rx = manager.subscribe_http_requests();
    // Treat the Router itself as a Service and clone it for dispatch
    let svc = app.clone();
    while let Ok(ipc_req) = rx.recv().await {
        // Build an Axum request from the IPC data
        let mut builder = AxumRequest::builder()
            .method(ipc_req.method.as_str())
            .uri(&ipc_req.uri);
        for (k, v) in &ipc_req.headers {
            builder = builder.header(k, v);
        }
        let req = builder
            .body(AxumBody::from(ipc_req.body.unwrap_or_default()))
            .map_err(|e| Error::Server(e.to_string()))?;
        // Dispatch to the router
        let resp = svc
            .clone()
            .oneshot(req)
            .await
            .map_err(|e| Error::Server(e.to_string()))?;
        // Convert response into IpcHttpResponse
        let status = resp.status().as_u16();
        let mut headers = HashMap::new();
        for (k, v) in resp.headers() {
            headers.insert(k.to_string(), v.to_str().unwrap_or_default().to_string());
        }
        // Collect full body and extract bytes
        let full = resp.into_body()
            .collect()
            .await
            .map_err(|e| Error::Server(e.to_string()))?;
        let bytes = full.to_bytes();
        let ipc_resp = IpcHttpResponse {
            request_id: ipc_req.request_id.clone(),
            status_code: status,
            headers,
            body: Some(bytes.to_vec()),
        };
        manager.send_http_response(ipc_resp)
            .await
            .map_err(Error::Server)?;
    }
    Ok(())
}

/// Options for serving a module.
#[derive(Debug, Clone)]
pub struct ServeOptions {
    /// Whether to bind an HTTP server (if false, only IPC will be used)
    pub bind_http: bool,
    /// Specific port to request from orchestrator (if None, the orchestrator will assign one)
    pub specific_port: Option<u16>,
    /// Alternative listen address (defaults to 127.0.0.1)
    pub listen_addr: Option<String>,
}

impl Default for ServeOptions {
    fn default() -> Self {
        Self {
            bind_http: true,
            specific_port: None,
            listen_addr: None,
        }
    }
}

/// Request a port from the orchestrator via IPC.
#[cfg(feature = "ipc_channel")]
async fn negotiate_port(specific_port: Option<u16>) -> Result<u16, Error> {
    // CRITICAL FIX: Check for pre-allocated port first
    if let Some(pre_allocated) = get_pre_allocated_port() {
        info!("Using pre-allocated port from InitBlob: {}", pre_allocated);
        return Ok(pre_allocated);
    }
    
    // If no pre-allocated port and specific_port is requested, try to use it
    if let Some(port) = specific_port {
        warn!("No pre-allocated port found, attempting to negotiate specific port: {}", port);
    } else {
        warn!("No pre-allocated port found, attempting to negotiate dynamic port");
    }
    
    let manager = IpcManager::new();
    
    // Create port negotiation request
    let request = IpcPortNegotiation {
        request_id: uuid::Uuid::new_v4().to_string(),
        specific_port,
    };
    
    // Send request to orchestrator
    info!("Requesting port from orchestrator: {:?}", specific_port);
    manager.send_port_negotiation(request)
        .await
        .map_err(|e| Error::Config(format!("Failed to send port request: {}", e)))?;
    
    // Wait for response
    let response = manager.wait_for_port_response()
        .await
        .map_err(|e| Error::Config(format!("Failed to receive port response: {}", e)))?;
    
    if !response.success {
        return Err(Error::Config(response.error_message.unwrap_or_else(|| 
            "Port negotiation failed with no error message".to_string())));
    }
    
    info!("Received port from orchestrator: {}", response.port);
    Ok(response.port)
}

/// Serve the given router with the specified options.
#[cfg(feature = "ipc_channel")]
pub async fn serve_with_options(app: axum::Router, options: ServeOptions) -> Result<(), Error> {
    // If IPC-only mode (no HTTP binding), set environment variables for other SDK components
    if !options.bind_http {
        // Set both variable formats for compatibility
        if std::env::var("IPC_ONLY").is_err() {
            std::env::set_var("IPC_ONLY", "true");
            info!("Set IPC_ONLY=true environment variable for SDK components");
        }
        
        if std::env::var("PYWATT_IPC_ONLY").is_err() {
            std::env::set_var("PYWATT_IPC_ONLY", "true");
            info!("Set PYWATT_IPC_ONLY=true environment variable for SDK components");
        }
    }
    
    // Always set up IPC serving
    let ipc_task = tokio::spawn(serve_ipc(app.clone()));
    
    // If HTTP binding is requested, negotiate a port and start HTTP server
    if options.bind_http {
        // Negotiate port with orchestrator
        let port = negotiate_port(options.specific_port).await?;
        
        // Bind HTTP server
        let listen_addr = options.listen_addr.unwrap_or_else(|| "127.0.0.1".to_string());
        let addr: SocketAddr = format!("{listen_addr}:{port}").parse()
            .map_err(|e| Error::Config(format!("Invalid address or port: {}", e)))?;
        
        info!("Starting HTTP server on {}", addr);
        let listener = tokio::net::TcpListener::bind(&addr).await
            .map_err(|e| Error::Server(e.to_string()))?;
        let server = axum::serve(listener, app.into_make_service());
        
        // Run the server
        tokio::select! {
            result = server => {
                result.map_err(|e| Error::Server(e.to_string()))?;
            }
            result = ipc_task => {
                result.map_err(|e| Error::Internal(Box::new(e)))??;
            }
        }
    } else {
        // Only serve via IPC
        info!("Module serving via IPC only");
        ipc_task.await.map_err(|e| Error::Internal(Box::new(e)))??;
    }
    
    Ok(())
}

#[cfg(not(feature = "ipc_channel"))]
pub async fn serve_with_options(app: axum::Router, options: ServeOptions) -> Result<(), Error> {
    // Without IPC channel, we can only serve HTTP
    let listen_addr = options.listen_addr.unwrap_or_else(|| "127.0.0.1".to_string());
    let port = options.specific_port.unwrap_or(0); // Use ephemeral port if none specified
    let addr: SocketAddr = format!("{listen_addr}:{port}").parse()
        .map_err(|e| Error::Config(format!("Invalid address or port: {}", e)))?;
    
    info!("Starting HTTP server on {}", addr);
    let listener = tokio::net::TcpListener::bind(&addr).await
        .map_err(|e| Error::Server(e.to_string()))?;
    let server = axum::serve(listener, app.into_make_service());
    
    server.await.map_err(|e| Error::Server(e.to_string()))?;
    Ok(())
}

/// Serve the given router, either over IPC (stdio) if the "ipc" feature is enabled,
/// or as an HTTP server on an ephemeral port otherwise.
#[cfg(feature = "ipc_channel")]
pub async fn serve_module(app: axum::Router) -> Result<(), Error> {
    serve_with_options(app, ServeOptions::default()).await
}

#[cfg(not(feature = "ipc_channel"))]
pub async fn serve_module(app: axum::Router) -> Result<(), Error> {
    // Use default options which will create an HTTP server on an ephemeral port
    serve_with_options(app, ServeOptions::default()).await
}

/// Serve a module with comprehensive lifecycle management as described in the MODULE_CREATION_GUIDE.
///
/// This function implements the complete module lifecycle:
/// 1. Initialize logging
/// 2. Perform handshake with orchestrator
/// 3. Fetch initial secrets
/// 4. Build user state
/// 5. Build router
/// 6. Announce endpoints
/// 7. Start IPC processing
/// 8. Serve the module
///
/// # Arguments
/// * `secret_keys` - List of secret keys to fetch at startup
/// * `endpoints` - List of endpoints to announce to the orchestrator
/// * `state_builder` - Function that builds user state from init and secrets
/// * `router_builder` - Function that builds the Axum router from app state
///
/// # Example
/// ```rust,no_run
/// use pywatt_sdk::prelude::*;
/// use axum::{Router, routing::get};
/// use secrecy::SecretString;
///
/// #[derive(Clone)]
/// struct MyState { db_url: String }
///
/// #[tokio::main]
/// async fn main() -> Result<(), Box<dyn std::error::Error>> {
///     let secret_keys = vec!["DATABASE_URL".to_string()];
///     let endpoints = vec![
///         EndpointAnnounce {
///             path: "/status".to_string(),
///             methods: vec!["GET".to_string()],
///             auth: None,
///         }
///     ];
///     
///     let state_builder = |init: &OrchestratorInit, secrets: Vec<SecretString>| MyState {
///         db_url: secrets.get(0).map(|s| s.expose_secret().clone()).unwrap_or_default()
///     };
///     
///     let router_builder = |app_state: AppState<MyState>| {
///         Router::new()
///             .route("/status", get(|| async { "OK" }))
///             .layer(Extension(app_state))
///     };
///     
///     serve_module_full(secret_keys, endpoints, state_builder, router_builder).await?;
///     Ok(())
/// }
/// ```
pub async fn serve_module_full<T, F, R>(
    secret_keys: Vec<String>,
    endpoints: Vec<crate::AnnouncedEndpoint>,
    state_builder: F,
    router_builder: R,
) -> Result<(), Error>
where
    F: Fn(&crate::OrchestratorInit, Vec<secrecy::SecretString>) -> T + Send + Sync + 'static,
    R: Fn(crate::AppState<T>) -> axum::Router + Send + Sync + 'static,
    T: Send + Sync + Clone + 'static,
{
    use crate::core::bootstrap::bootstrap_module;
    
    // Bootstrap the module to get AppState and IPC handle
    let (app_state, ipc_handle) = bootstrap_module(
        secret_keys,
        endpoints,
        state_builder,
        None, // Use default channel preferences
    ).await.map_err(|e| Error::Server(e.to_string()))?;
    
    // Build the router using the provided builder function
    let router = router_builder(app_state);
    
    // Start the HTTP server with shutdown handling
    let serve_task = tokio::spawn(serve_module(router));
    
    // Wait for either the server to complete or the IPC handle (which handles shutdown)
    tokio::select! {
        result = serve_task => {
            match result {
                Ok(Ok(())) => {
                    info!("HTTP server completed successfully");
                }
                Ok(Err(e)) => {
                    error!("HTTP server error: {}", e);
                    return Err(e);
                }
                Err(e) => {
                    error!("HTTP server task panicked: {}", e);
                    return Err(Error::Internal(Box::new(e)));
                }
            }
        }
        result = ipc_handle => {
            match result {
                Ok(()) => {
                    info!("IPC processing completed (shutdown signal received)");
                }
                Err(e) => {
                    warn!("IPC processing task ended with error: {}", e);
                }
            }
        }
    }
    
    info!("Module shutting down gracefully");
    Ok(())
}

/// Alias for backward compatibility and to match the MODULE_CREATION_GUIDE exactly.
/// 
/// This is the function signature described in the guide:
/// ```rust,no_run
/// serve_module(secret_keys, endpoints, state_builder, router_builder).await?;
/// ```
pub async fn serve_module_with_lifecycle<T, F, R>(
    secret_keys: Vec<String>,
    endpoints: Vec<crate::AnnouncedEndpoint>,
    state_builder: F,
    router_builder: R,
) -> Result<(), Error>
where
    F: Fn(&crate::OrchestratorInit, Vec<secrecy::SecretString>) -> T + Send + Sync + 'static,
    R: Fn(crate::AppState<T>) -> axum::Router + Send + Sync + 'static,
    T: Send + Sync + Clone + 'static,
{
    serve_module_full(secret_keys, endpoints, state_builder, router_builder).await
}
