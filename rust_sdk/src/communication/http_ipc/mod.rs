//! HTTP over IPC utilities for PyWatt modules.
//!
//! This module provides standardized utilities for handling HTTP requests and responses
//! over the PyWatt IPC mechanism. It simplifies the process of routing requests,
//! formatting responses, and handling errors in a consistent way across modules.
//!
//! The improved implementation includes:
//! - Enhanced logging for debugging IPC communication issues
//! - More robust error handling and recovery
//! - Better diagnostics for request/response flow

pub mod result;

use crate::ipc_types::{IpcHttpRequest, IpcHttpResponse};
use crate::communication::ipc_port_negotiation::PortNegotiationManager;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;
use tokio::sync::broadcast;
use tokio::sync::Mutex;
use tracing::{debug, error, info, warn, trace, Level};
use once_cell::sync::Lazy;
// uuid is used in the implementation elsewhere

pub use self::result::*;

// Static channels for HTTP request/response handling with improved capacity
static HTTP_REQUEST_CHANNEL: Lazy<(broadcast::Sender<IpcHttpRequest>, Mutex<Option<broadcast::Receiver<IpcHttpRequest>>>)> = 
    Lazy::new(|| {
        let (tx, rx) = broadcast::channel(256); // Increased capacity
        (tx, Mutex::new(Some(rx)))
    });

static HTTP_RESPONSE_CHANNEL: Lazy<(broadcast::Sender<IpcHttpResponse>, Mutex<Option<broadcast::Receiver<IpcHttpResponse>>>)> = 
    Lazy::new(|| {
        let (tx, rx) = broadcast::channel(256); // Increased capacity
        (tx, Mutex::new(Some(rx)))
    });

/// Detailed metrics for HTTP-IPC performance monitoring
#[derive(Debug, Default)]
pub struct HttpIpcMetrics {
    pub requests_received: std::sync::atomic::AtomicUsize,
    pub responses_sent: std::sync::atomic::AtomicUsize,
    pub errors_encountered: std::sync::atomic::AtomicUsize,
    pub avg_response_time_ms: std::sync::atomic::AtomicUsize,
}

// Global metrics instance
static HTTP_IPC_METRICS: Lazy<HttpIpcMetrics> = Lazy::new(|| HttpIpcMetrics::default());

/// Get reference to the global HTTP IPC metrics
pub fn metrics() -> &'static HttpIpcMetrics {
    &*HTTP_IPC_METRICS
}

/// Subscribe to HTTP requests
pub fn subscribe_http_requests() -> broadcast::Receiver<IpcHttpRequest> {
    let receiver = HTTP_REQUEST_CHANNEL.0.subscribe();
    debug!("New subscriber for HTTP IPC requests (total receivers: {})", 
           HTTP_REQUEST_CHANNEL.0.receiver_count());
    receiver
}

/// Send an HTTP response with enhanced logging and metrics
pub async fn send_http_response(response: IpcHttpResponse) -> std::result::Result<(), crate::Error> {
    debug!("Sending HTTP response - request_id: {}, status: {}", 
           response.request_id, response.status_code);
    
    let body_size = response.body.as_ref().map_or(0, |b| b.len());
    trace!("Response body size: {} bytes", body_size);
    
    if Level::TRACE <= tracing::level_filters::LevelFilter::current() {
        // Log headers at TRACE level
        for (name, value) in &response.headers {
            trace!("Response header: {}: {}", name, value);
        }
    }
    
    // Attempt to send the response, with retry logic
    let mut retry_count = 0;
    let max_retries = 2;
    let mut last_error = None;
    
    while retry_count <= max_retries {
        match HTTP_RESPONSE_CHANNEL.0.send(response.clone()) {
            Ok(_) => {
                // Update metrics
                HTTP_IPC_METRICS.responses_sent.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                debug!("HTTP response sent successfully (request_id: {})", response.request_id);
                return Ok(());
            }
            Err(e) => {
                warn!("Failed to send HTTP response (attempt {}/{}): {}", 
                      retry_count + 1, max_retries + 1, e);
                
                if retry_count == max_retries {
                    error!("Failed to send HTTP response after {} attempts: {}", 
                           max_retries + 1, e);
                    last_error = Some(e);
                    break;
                }
                
                // Short backoff before retry
                tokio::time::sleep(tokio::time::Duration::from_millis(50)).await;
                retry_count += 1;
            }
        }
    }
    
    // If we get here, all retries failed
    HTTP_IPC_METRICS.errors_encountered.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    
    if let Some(error) = last_error {
        Err(crate::Error::Config(crate::error::ConfigError::Invalid(
            format!("Failed to send HTTP response after {} attempts: {}", 
                   max_retries + 1, error)
        )))
    } else {
        Err(crate::Error::Config(crate::error::ConfigError::Invalid(
            "Failed to send HTTP response after all attempts".to_string()
        )))
    }
}

/// Standard response data structure for API responses.
#[derive(Debug, Serialize, Deserialize)]
pub struct ApiResponse<T> {
    /// Status of the response (success, error)
    pub status: String,
    /// Optional data payload
    pub data: Option<T>,
    /// Optional message for additional context
    pub message: Option<String>,
}

/// Handler function type for route handlers
pub type HandlerFn<S> = Arc<
    dyn Fn(
            IpcHttpRequest,
            Arc<S>,
        ) -> Pin<Box<dyn Future<Output = HttpResult<IpcHttpResponse>> + Send>>
        + Send
        + Sync,
>;

/// A route entry in the router
#[derive(Clone)]
struct Route<S> {
    method: String,
    path: String,
    handler: HandlerFn<S>,
}

/// HTTP IPC Router for handling requests
#[derive(Clone)]
pub struct HttpIpcRouter<S: Send + Sync + Clone + 'static> {
    routes: Arc<Vec<Route<S>>>,
    not_found_handler: Option<HandlerFn<S>>,
    middleware: Vec<Arc<dyn Fn(IpcHttpRequest) -> Pin<Box<dyn Future<Output = IpcHttpRequest> + Send>> + Send + Sync>>,
}

impl<S: Send + Sync + Clone + 'static> Default for HttpIpcRouter<S> {
    fn default() -> Self {
        Self::new()
    }
}

impl<S: Send + Sync + Clone + 'static> HttpIpcRouter<S> {
    /// Create a new router.
    pub fn new() -> Self {
        Self {
            routes: Arc::new(Vec::new()),
            not_found_handler: None,
            middleware: Vec::new(),
        }
    }

    /// Add a route to the router
    pub fn route<F, Fut>(mut self, method: &str, path: &str, handler: F) -> Self
    where
        F: Fn(IpcHttpRequest, Arc<S>) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = HttpResult<IpcHttpResponse>> + Send + 'static,
    {
        let handler = Arc::new(move |req, state| {
            let fut = handler(req, state);
            Box::pin(fut) as Pin<Box<dyn Future<Output = HttpResult<IpcHttpResponse>> + Send>>
        });

        let mut routes = (*self.routes).clone();
        routes.push(Route {
            method: method.to_uppercase(),
            path: path.to_string(),
            handler,
        });
        self.routes = Arc::new(routes);
        debug!("Added route: {} {}", method.to_uppercase(), path);

        self
    }

    /// Add middleware to process requests before they reach handlers
    pub fn middleware<F, Fut>(mut self, middleware_fn: F) -> Self
    where
        F: Fn(IpcHttpRequest) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = IpcHttpRequest> + Send + 'static,
    {
        let middleware = Arc::new(move |req: IpcHttpRequest| {
            let fut = middleware_fn(req);
            Box::pin(fut) as Pin<Box<dyn Future<Output = IpcHttpRequest> + Send>>
        });

        self.middleware.push(middleware);
        debug!("Added middleware to router");

        self
    }

    /// Set a custom not-found handler
    pub fn not_found_handler<F, Fut>(mut self, handler: F) -> Self
    where
        F: Fn(IpcHttpRequest, Arc<S>) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = HttpResult<IpcHttpResponse>> + Send + 'static,
    {
        let handler = Arc::new(move |req, state| {
            let fut = handler(req, state);
            Box::pin(fut) as Pin<Box<dyn Future<Output = HttpResult<IpcHttpResponse>> + Send>>
        });

        self.not_found_handler = Some(handler);
        debug!("Custom not-found handler set");

        self
    }

    /// Match a request to a route handler
    pub async fn handle_request(&self, mut request: IpcHttpRequest, state: Arc<S>) -> IpcHttpResponse {
        let start_time = std::time::Instant::now();
        info!(
            "HTTP_IPC_ROUTER: Processing request - ID: {}, Method: {}, URI: {}",
            request.request_id, request.method, request.uri
        );
        
        // Process request through middleware chain
        for middleware in &self.middleware {
            request = middleware(request).await;
        }
        
        let method = request.method.to_uppercase();
        let path = request
            .uri
            .split('?')
            .next()
            .unwrap_or(&request.uri)
            .to_string();

        debug!("Routing request: {} {} (request_id: {})", method, path, request.request_id);

        // Find matching route
        let routes_count = self.routes.len();
        if routes_count > 10 {
            debug!("Searching through {} routes for match", routes_count);
        }
        
        for route in self.routes.as_ref() {
            if route.method == method && route.path == path {
                debug!("Found matching route: {} {}", route.method, route.path);

                // Call the handler
                let handler_result = match (route.handler)(request.clone(), state.clone()).await {
                    Ok(response) => {
                        // Record success metrics
                        let elapsed = start_time.elapsed();
                        let elapsed_ms = elapsed.as_millis() as usize;
                        
                        // Update running average of response time
                        let current_avg = HTTP_IPC_METRICS.avg_response_time_ms.load(std::sync::atomic::Ordering::Relaxed);
                        let count = HTTP_IPC_METRICS.responses_sent.load(std::sync::atomic::Ordering::Relaxed);
                        let new_avg = if count == 0 {
                            elapsed_ms
                        } else {
                            // Simple running average calculation
                            ((current_avg * count) + elapsed_ms) / (count + 1)
                        };
                        HTTP_IPC_METRICS.avg_response_time_ms.store(new_avg, std::sync::atomic::Ordering::Relaxed);
                        
                        debug!("Handler completed in {}ms (request_id: {})", elapsed_ms, request.request_id);
                        Ok(response)
                    },
                    Err(err) => {
                        error!("Handler error for {} {}: {} (request_id: {})", 
                               method, path, err, request.request_id);
                        // Record error metric
                        HTTP_IPC_METRICS.errors_encountered.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                        Err(err)
                    }
                };
                
                match handler_result {
                    Ok(mut response) => {
                        response.request_id = request.request_id;
                        return response;
                    }
                    Err(err) => {
                        return result::error_to_response(err, &request.request_id);
                    }
                }
            }
        }

        // No route found, use not_found_handler if available
        if let Some(handler) = &self.not_found_handler {
            match handler(request.clone(), state).await {
                Ok(mut response) => {
                    let request_id = request.request_id.clone();
                    response.request_id = request_id.clone();
                    info!("Not found handler completed for {} {} (request_id: {})", 
                          method, path, request_id);
                    response
                }
                Err(err) => {
                    error!("Not found handler error: {} (request_id: {})", 
                           err, request.request_id);
                    // Record error metric
                    HTTP_IPC_METRICS.errors_encountered.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    result::error_to_response(err, &request.request_id)
                }
            }
        } else {
            // Default not found response
            let response = ApiResponse::<()> {
                status: "error".to_string(),
                data: None,
                message: Some(format!("Endpoint not found: {} {}", method, path)),
            };

            warn!("No route found for {} {} (request_id: {})", 
                  method, path, request.request_id);

            let body = match serde_json::to_vec(&response) {
                Ok(body) => Some(body),
                Err(e) => {
                    error!("Failed to serialize not found response: {} (request_id: {})", 
                           e, request.request_id);
                    Some(format!("{{\"status\":\"error\",\"message\":\"Endpoint not found: {} {}\"}}", 
                              method, path).into_bytes())
                }
            };

            let mut headers = HashMap::new();
            headers.insert("Content-Type".to_string(), "application/json".to_string());

            IpcHttpResponse {
                request_id: request.request_id,
                status_code: 404,
                headers,
                body,
            }
        }
    }
}

/// HTTP IPC server configuration
#[derive(Clone)]
pub struct HttpIpcServerConfig {
    /// Maximum number of concurrent requests to process
    pub max_concurrent_requests: usize,
    
    /// Whether to log full request details (including headers and body) at trace level
    pub trace_requests: bool,
    
    /// Optional function to log request IDs for correlation
    pub request_id_logger: Option<Arc<dyn Fn(&str) + Send + Sync>>,
}

// Manual Debug implementation for HttpIpcServerConfig since dyn Fn doesn't implement Debug
impl std::fmt::Debug for HttpIpcServerConfig {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("HttpIpcServerConfig")
            .field("max_concurrent_requests", &self.max_concurrent_requests)
            .field("trace_requests", &self.trace_requests)
            .field("request_id_logger", &if self.request_id_logger.is_some() { "Some(...)" } else { "None" })
            .finish()
    }
}

impl Default for HttpIpcServerConfig {
    fn default() -> Self {
        Self {
            max_concurrent_requests: 100,
            trace_requests: false,
            request_id_logger: None,
        }
    }
}

/// Start the HTTP IPC server with the given router and state
pub async fn start_http_ipc_server<S>(
    router: HttpIpcRouter<S>,
    state: S,
    shutdown_signal: Option<broadcast::Receiver<()>>,
    config: Option<HttpIpcServerConfig>,
) -> std::result::Result<(), crate::Error>
where
    S: Send + Sync + Clone + 'static,
{
    let server_config = config.unwrap_or_default();
    
    info!("Starting HTTP IPC server (max_concurrent_requests: {})", 
          server_config.max_concurrent_requests);
    
    // Subscribe to HTTP requests
    let mut rx = subscribe_http_requests();
    
    // Set up a semaphore to limit concurrency
    let semaphore = Arc::new(tokio::sync::Semaphore::new(server_config.max_concurrent_requests));
    
    // Clone state for the server task
    let state = Arc::new(state);
    
    // Create a task to process HTTP requests
    let server_task = tokio::spawn(async move {
        info!("HTTP IPC server task started");
        
        // Log allocated port if available (from port negotiation)
        if let Some(port) = PortNegotiationManager::get_allocated_port() {
            info!("HTTP IPC server using allocated port: {}", port);
        } else {
            info!("HTTP IPC server running in pure IPC mode (no TCP port allocated)");
        }
        
        loop {
            match rx.recv().await {
                Ok(request) => {
                    // Update metrics
                    HTTP_IPC_METRICS.requests_received.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    
                    // Log the incoming request
                    info!("HTTP IPC server received request - ID: {}, Method: {}, URI: {}", 
                          request.request_id, request.method, request.uri);
                    
                    // Detailed request logging at trace level if enabled
                    if server_config.trace_requests && Level::TRACE <= tracing::level_filters::LevelFilter::current() {
                        trace!("Request headers: {:?}", request.headers);
                        if let Some(body) = &request.body {
                            if body.len() < 1024 {
                                // For small bodies, try to log as string if possible
                                match std::str::from_utf8(body) {
                                    Ok(body_str) => trace!("Request body (string): {}", body_str),
                                    Err(_) => trace!("Request body (bytes): {:?}", body),
                                }
                            } else {
                                trace!("Request body size: {} bytes", body.len());
                            }
                        } else {
                            trace!("Request has no body");
                        }
                    }
                    
                    // Log request ID if a logger is provided
                    if let Some(id_logger) = &server_config.request_id_logger {
                        id_logger(&request.request_id);
                    }
                    
                    // Acquire a permit from the semaphore to limit concurrency
                    let permit = match semaphore.clone().acquire_owned().await {
                        Ok(permit) => permit,
                        Err(e) => {
                            error!("Failed to acquire semaphore permit: {}", e);
                            continue;
                        }
                    };
                    
                    // Clone the router and state for the handler task
                    let router = router.clone();
                    let state = Arc::clone(&state);
                    let request_id = request.request_id.clone(); // For logging
                    
                    // Spawn a task to handle the request
                    tokio::spawn(async move {
                        debug!("Processing request in handler task (request_id: {})", request_id);
                        
                        // Handle the request and get the response
                        let response = router.handle_request(request, state).await;
                        
                        // Send the response
                        if let Err(e) = send_http_response(response).await {
                            error!("Failed to send HTTP response: {} (request_id: {})", 
                                   e, request_id);
                        }
                        
                        // Permit is automatically dropped when task completes, releasing the semaphore
                        drop(permit);
                        debug!("Handler task completed (request_id: {})", request_id);
                    });
                }
                Err(e) => {
                    match e {
                        broadcast::error::RecvError::Closed => {
                            error!("HTTP request channel closed. Shutting down HTTP IPC server.");
                            break;
                        }
                        broadcast::error::RecvError::Lagged(count) => {
                            warn!("HTTP IPC server lagged behind by {} messages. Consider increasing channel capacity.", count);
                            // Re-subscribe to continue processing
                            rx = subscribe_http_requests();
                        }
                    }
                }
            }
        }
    });
    
    // If a shutdown signal is provided, wait for it
    if let Some(mut shutdown_rx) = shutdown_signal {
        tokio::select! {
            _ = shutdown_rx.recv() => {
                info!("Received shutdown signal. Shutting down HTTP IPC server.");
            }
            _ = server_task => {
                info!("HTTP IPC server task completed unexpectedly.");
            }
        }
    } else {
        // Otherwise, just wait for the server task to complete
        server_task.await.map_err(|e| {
            crate::Error::Config(crate::error::ConfigError::Invalid(
                format!("HTTP IPC server task failed: {}", e)
            ))
        })?;
    }
    
    info!("HTTP IPC server stopped.");
    Ok(())
}
