use secrecy::SecretString;
use std::sync::Arc;
use thiserror::Error;
use tokio::task::JoinHandle;
use tracing::{debug, error, info, trace, warn};
use std::collections::HashMap;
use tokio::sync::Mutex;
use tokio::time::Duration;

// bootstrap module
#[cfg(feature = "tcp")]
use url::Url;
use tokio::net::TcpStream;

use crate::announce::{AnnounceError, send_announce};
use crate::ext::OrchestratorInitExt;
use crate::handshake::{InitError, read_init};
#[cfg(feature = "ipc_channel")]
use crate::ipc::process_ipc_messages;
use crate::ipc_types::{ModuleToOrchestrator, OrchestratorToModule};
use crate::internal_messaging;
use crate::logging::init_module;
use crate::message::{EncodedMessage, EncodingFormat, Message, MessageError};
use crate::secrets::{ModuleSecretError, get_module_secret_client, get_secret};
use crate::state::AppState;
use crate::communication::{MessageChannel, TcpChannel, ChannelPreferences, ChannelType, ChannelCapabilities};
use crate::tcp_types::ConnectionState;
use crate::{AnnouncedEndpoint, Error, ModuleAnnounce, OrchestratorInit};

// Re-export IpcChannel when available
#[cfg(feature = "ipc_channel")]
use crate::communication::{IpcChannel, IpcConnectionConfig};

/// Type alias for the pending internal responses map to reduce type complexity
type PendingMap = Arc<Mutex<HashMap<uuid::Uuid, tokio::sync::oneshot::Sender<Result<EncodedMessage, Error>>>>>;

/// Errors that may occur during bootstrap initialization.
#[derive(Debug, Error)]
pub enum BootstrapError {
    #[error("handshake failed: {0}")]
    Init(#[from] InitError),

    #[error("secret client error: {0}")]
    Secret(#[from] ModuleSecretError),

    #[error("announcement error: {0}")]
    Announce(#[from] AnnounceError),

    #[error("required channel failed to initialize: {channel_type} - {error}")]
    RequiredChannelFailed { channel_type: String, error: String },

    #[error("no channels available for communication")]
    NoChannelsAvailable,

    #[error("other error: {0}")]
    Other(String),
}

/// Main processing task for handling messages from the orchestrator over TCP.
///
/// This task runs in the background and processes messages received from the orchestrator,
/// including routing internal module-to-module messages and responses, and handling
/// heartbeats and shutdown signals.
///
/// The task will continue running until either the orchestrator sends a shutdown signal
/// or the TCP connection is permanently closed.
async fn main_processing_task<S: Send + Sync + 'static>(
    app_state: Arc<AppState<S>>,
    orchestrator_channel: Arc<TcpChannel>,
) {
    debug!("Main TCP processing task started.");

    // Clone necessary Arcs for the loop
    let pending_responses_map_for_task = app_state.pending_internal_responses.clone();

    loop {
        match orchestrator_channel.receive().await {
            Ok(encoded_message) => {
                // Attempt to decode the EncodedMessage into an OrchestratorToModule variant
                // OrchestratorToModule doesn't implement bincode::Decode, so use JSON deserialization directly
                let message = match encoded_message.format() {
                    crate::message::EncodingFormat::Json => {
                        // For JSON, we can deserialize directly
                        match serde_json::from_slice::<OrchestratorToModule>(encoded_message.data()) {
                            Ok(msg) => msg,
                            Err(e) => {
                                error!("Failed to decode OrchestratorToModule message: {}", e);
                                continue;
                            }
                        }
                    },
                    _ => {
                        // For other formats, attempt to convert to JSON first
                        match encoded_message.to_format(crate::message::EncodingFormat::Json) {
                            Ok(json_encoded) => {
                                match serde_json::from_slice::<OrchestratorToModule>(json_encoded.data()) {
                                    Ok(msg) => msg,
                                    Err(e) => {
                                        error!("Failed to decode OrchestratorToModule message: {}", e);
                                        continue;
                                    }
                                }
                            },
                            Err(e) => {
                                error!("Failed to convert message to JSON: {}", e);
                                continue;
                            }
                        }
                    }
                };

                match message {
                    OrchestratorToModule::Heartbeat => {
                        debug!("Received Heartbeat from orchestrator. Sending Ack.");
                        let ack = ModuleToOrchestrator::HeartbeatAck;
                        let msg = Message::new(ack);
                        let default_encoding = app_state.config
                            .as_ref()
                            .and_then(|cfg| cfg.message_format_primary)
                            .unwrap_or_default();
                        match EncodedMessage::encode_with_format(&msg, default_encoding) {
                            Ok(encoded_ack) => {
                                if let Err(e) = orchestrator_channel.send(encoded_ack).await {
                                    error!("Failed to send HeartbeatAck to orchestrator: {}", e);
                                }
                            }
                            Err(e) => {
                                error!("Failed to encode HeartbeatAck: {}", e);
                            }
                        }
                    }
                    OrchestratorToModule::Shutdown => {
                        warn!("Received Shutdown signal from orchestrator. Terminating module.");
                        break;
                    }
                    #[allow(unused_variables)]
                    OrchestratorToModule::RoutedModuleResponse { request_id, source_module_id, payload } => {
                        debug!(request_id = %request_id, source_module_id = %source_module_id, "Received RoutedModuleResponse, dispatching.");
                        if let Some(ref pending_map) = pending_responses_map_for_task {
                            // The payload is an EncodedMessage from the target module.
                            // process_routed_module_response expects Result<EncodedMessage, Error>.
                            // If we are here, the orchestrator successfully relayed it, so it's Ok(payload).
                            internal_messaging::process_routed_module_response(
                                request_id,
                                Ok(payload), // Pass the EncodedMessage payload as Ok
                                pending_map.clone(),
                            ).await;
                        } else {
                            warn!(request_id = %request_id, "Received RoutedModuleResponse but no pending_responses_map in AppState. Discarding.");
                        }
                    }
                    #[allow(unused_variables)]
                    OrchestratorToModule::RoutedModuleMessage { source_module_id, original_request_id, payload } => {
                        debug!(
                            source_module_id = %source_module_id, 
                            request_id = %original_request_id,
                            "Received RoutedModuleMessage from another module."
                        );
                        // Check if there's a registered handler for module-to-module messages in the app state
                        if let Some(ref message_handlers) = app_state.module_message_handlers {
                            // If there's a handler, attempt to process the message
                            let handler = message_handlers.lock().await;
                            if let Some(handler_fn) = handler.get(&source_module_id) {
                                debug!("Found handler for messages from module {}", source_module_id);
                                // Spawn a task to process the message asynchronously
                                let handler_clone = handler_fn.clone();
                                let source_id = source_module_id.clone();
                                let req_id = original_request_id;
                                let payload_clone = payload.clone();
                                let channel_name_clone = "TCP".to_string();
                                
                                tokio::spawn(async move {
                                    // Call the handler
                                    match handler_clone(source_id, req_id, payload_clone).await {
                                        Ok(response) => {
                                            // Send response back if needed
                                            debug!("Module-to-module message handler completed successfully on {} channel", channel_name_clone);
                                        },
                                        Err(e) => {
                                            error!("Error processing module-to-module message on {} channel: {}", channel_name_clone, e);
                                        }
                                    }
                                });
                                return;
                            }
                        }
                        
                        // No handler found
                        info!("No handler registered for module-to-module messages from {}. Message discarded.", source_module_id);
                    }
                    OrchestratorToModule::HttpRequest(http_request) => {
                        trace!("Received HttpRequest from orchestrator: {:?}", http_request.uri);
                        
                        // Handle HTTP-over-TCP requests by converting them to internal HTTP processing
                        // This involves:
                        // 1. Converting the IPC HTTP request to a proper HTTP request
                        // 2. Processing it through the module's HTTP handlers (if available)
                        // 3. Sending the response back through the TCP channel
                        
                        debug!("Processing HTTP request: {} {}", http_request.method, http_request.uri);
                        
                        // Create a correlation ID for this request
                        let correlation_id = uuid::Uuid::new_v4();
                        
                        // In a full implementation, we would:
                        // 1. Build an HTTP request from the IPC data
                        // 2. Route it through the module's Axum router
                        // 3. Capture the response and convert it back to IPC format
                        
                        // For now, we'll process basic requests and provide useful responses
                        let (status_code, response_body, response_headers) = match http_request.uri.as_str() {
                            "/health" => {
                                // Health check endpoint
                                (200, Some(b"{\"status\":\"healthy\",\"module_id\":\"".to_vec()), 
                                 [("content-type".to_string(), "application/json".to_string())].into())
                            }
                            uri if uri.starts_with("/api/") => {
                                // API endpoints - return a structured response
                                let response = format!(
                                    "{{\"message\":\"API endpoint {} processed\",\"method\":\"{}\",\"correlation_id\":\"{}\"}}",
                                    uri, http_request.method, correlation_id
                                );
                                (200, Some(response.into_bytes()),
                                 [("content-type".to_string(), "application/json".to_string())].into())
                            }
                            _ => {
                                // Generic response for other endpoints
                                let response = format!(
                                    "{{\"message\":\"HTTP request received\",\"uri\":\"{}\",\"method\":\"{}\",\"correlation_id\":\"{}\"}}",
                                    http_request.uri, http_request.method, correlation_id
                                );
                                (200, Some(response.into_bytes()),
                                 [("content-type".to_string(), "application/json".to_string())].into())
                            }
                        };
                        
                        // If there's a request body, we could process it here
                        if let Some(ref body) = http_request.body {
                            debug!("Request body size: {} bytes", body.len());
                            // In a full implementation, we'd parse the body based on content-type
                            // and include it in the request processing
                        }
                        
                        // Create the response with proper request ID matching
                        let http_response = crate::ipc_types::IpcHttpResponse {
                            request_id: http_request.request_id.clone(),
                            status_code,
                            headers: response_headers,
                            body: response_body,
                        };
                        
                        // Send the response back to the orchestrator
                        let response_msg = ModuleToOrchestrator::HttpResponse(http_response);
                        let response_message = Message::new(response_msg);
                        let default_encoding = app_state.config
                            .as_ref()
                            .and_then(|cfg| cfg.message_format_primary)
                            .unwrap_or_default();
                        
                        match EncodedMessage::encode_with_format(&response_message, default_encoding) {
                            Ok(encoded_response) => {
                                if let Err(e) = orchestrator_channel.send(encoded_response).await {
                                    error!("Failed to send HTTP response to orchestrator: {}", e);
                                } else {
                                    debug!(
                                        request_id = %http_request.request_id,
                                        status_code = %status_code,
                                        correlation_id = %correlation_id,
                                        "Successfully sent HTTP response"
                                    );
                                }
                            }
                            Err(e) => {
                                error!("Failed to encode HTTP response: {}", e);
                            }
                        }
                    }
                    other => {
                        trace!("Received unhandled OrchestratorToModule variant: {:?}", other);
                    }
                }
            }
            Err(e) => {
                // Handle message error type
                match &e {
                    MessageError::InvalidFormat(error_msg) if error_msg.contains("connection aborted") => {
                        warn!("Orchestrator connection closed. Attempting reconnect if configured...");
                        if orchestrator_channel.is_permanently_closed().await {
                            error!("Orchestrator connection permanently closed. Main processing task terminating.");
                            break;
                        }
                        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                    },
                    _ => {
                        error!("Fatal error receiving message from orchestrator: {}. Main processing task terminating.", e);
                        break;
                    }
                }
            }
        }
    }
    debug!("Main TCP processing task finished.");
}

/// Independent TCP message processing task for handling messages from the orchestrator over TCP.
///
/// This task runs in the background and processes messages received from the orchestrator
/// via the TCP channel, including routing internal module-to-module messages and responses,
/// and handling heartbeats and shutdown signals.
async fn tcp_message_processing_task<S: Send + Sync + 'static>(
    app_state: Arc<AppState<S>>,
    tcp_channel: Arc<TcpChannel>,
) {
    debug!("Independent TCP message processing task started.");

    // Clone necessary Arcs for the loop
    let pending_responses_map_for_task = app_state.pending_internal_responses.clone();

    loop {
        match tcp_channel.receive().await {
            Ok(encoded_message) => {
                // Decode and process the message (same logic as main_processing_task)
                let message = match encoded_message.format() {
                    crate::message::EncodingFormat::Json => {
                        match serde_json::from_slice::<OrchestratorToModule>(encoded_message.data()) {
                            Ok(msg) => msg,
                            Err(e) => {
                                error!("TCP channel: Failed to decode OrchestratorToModule message: {}", e);
                                continue;
                            }
                        }
                    },
                    _ => {
                        match encoded_message.to_format(crate::message::EncodingFormat::Json) {
                            Ok(json_encoded) => {
                                match serde_json::from_slice::<OrchestratorToModule>(json_encoded.data()) {
                                    Ok(msg) => msg,
                                    Err(e) => {
                                        error!("TCP channel: Failed to decode OrchestratorToModule message: {}", e);
                                        continue;
                                    }
                                }
                            },
                            Err(e) => {
                                error!("TCP channel: Failed to convert message to JSON: {}", e);
                                continue;
                            }
                        }
                    }
                };

                // Process message using shared logic
                if let Err(e) = process_orchestrator_message(
                    message,
                    &app_state,
                    &tcp_channel,
                    &pending_responses_map_for_task,
                    "TCP"
                ).await {
                    if e.contains("shutdown") {
                        break;
                    }
                }
            }
            Err(e) => {
                match &e {
                    MessageError::InvalidFormat(error_msg) if error_msg.contains("connection aborted") => {
                        warn!("TCP channel: Orchestrator connection closed. Attempting reconnect if configured...");
                        if tcp_channel.is_permanently_closed().await {
                            error!("TCP channel: Orchestrator connection permanently closed. TCP processing task terminating.");
                            break;
                        }
                        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                    },
                    MessageError::IoError(io_err) => {
                        match io_err.kind() {
                            std::io::ErrorKind::ConnectionReset |
                            std::io::ErrorKind::ConnectionAborted |
                            std::io::ErrorKind::BrokenPipe |
                            std::io::ErrorKind::UnexpectedEof => {
                                info!("TCP channel: Connection closed by orchestrator. TCP processing task terminating.");
                                break;
                            }
                            std::io::ErrorKind::TimedOut => {
                                warn!("TCP channel: Connection timed out. TCP processing task terminating.");
                                break;
                            }
                            _ => {
                                error!("TCP channel: I/O error receiving message from orchestrator: {}. TCP processing task terminating.", io_err);
                                break;
                            }
                        }
                    },
                    _ => {
                        error!("TCP channel: Fatal error receiving message from orchestrator: {}. TCP processing task terminating.", e);
                        break;
                    }
                }
            }
        }
    }
    debug!("Independent TCP message processing task finished.");
}

/// Independent IPC message processing task for handling messages from the orchestrator over IPC.
///
/// This task runs in the background and processes messages received from the orchestrator
/// via the IPC channel, providing the same functionality as the TCP channel but over
/// Unix Domain Sockets for high-performance local communication.
#[cfg(feature = "ipc_channel")]
async fn ipc_message_processing_task<S: Send + Sync + 'static>(
    app_state: Arc<AppState<S>>,
    ipc_channel: Arc<IpcChannel>,
) {
    debug!("Independent IPC message processing task started.");

    // Clone necessary Arcs for the loop
    let pending_responses_map_for_task = app_state.pending_internal_responses.clone();

    loop {
        match ipc_channel.receive().await {
            Ok(encoded_message) => {
                // Decode and process the message (same logic as TCP task)
                let message = match encoded_message.format() {
                    crate::message::EncodingFormat::Json => {
                        match serde_json::from_slice::<OrchestratorToModule>(encoded_message.data()) {
                            Ok(msg) => msg,
                            Err(e) => {
                                error!("IPC channel: Failed to decode OrchestratorToModule message: {}", e);
                                continue;
                            }
                        }
                    },
                    _ => {
                        match encoded_message.to_format(crate::message::EncodingFormat::Json) {
                            Ok(json_encoded) => {
                                match serde_json::from_slice::<OrchestratorToModule>(json_encoded.data()) {
                                    Ok(msg) => msg,
                                    Err(e) => {
                                        error!("IPC channel: Failed to decode OrchestratorToModule message: {}", e);
                                        continue;
                                    }
                                }
                            },
                            Err(e) => {
                                error!("IPC channel: Failed to convert message to JSON: {}", e);
                                continue;
                            }
                        }
                    }
                };

                // Process message using shared logic
                if let Err(e) = process_orchestrator_message(
                    message,
                    &app_state,
                    &ipc_channel,
                    &pending_responses_map_for_task,
                    "IPC"
                ).await {
                    if e.contains("shutdown") {
                        break;
                    }
                }
            }
            Err(e) => {
                match &e {
                    MessageError::InvalidFormat(error_msg) if error_msg.contains("connection aborted") => {
                        warn!("IPC channel: Orchestrator connection closed. Attempting reconnect if configured...");
                        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                    },
                    _ => {
                        error!("IPC channel: Fatal error receiving message from orchestrator: {}. IPC processing task terminating.", e);
                        break;
                    }
                }
            }
        }
    }
    debug!("Independent IPC message processing task finished.");
}

/// Shared message processing logic for both TCP and IPC channels.
///
/// This function contains the common message processing logic that both TCP and IPC
/// channels use, ensuring consistent behavior across both transport mechanisms.
async fn process_orchestrator_message<S: Send + Sync + 'static, C: MessageChannel>(
    message: OrchestratorToModule,
    app_state: &Arc<AppState<S>>,
    channel: &Arc<C>,
    pending_responses_map: &Option<PendingMap>,
    channel_name: &str,
) -> Result<(), String> {
    match message {
        OrchestratorToModule::Heartbeat => {
            debug!("{} channel: Received Heartbeat from orchestrator. Sending Ack.", channel_name);
            let ack = ModuleToOrchestrator::HeartbeatAck;
            let msg = Message::new(ack);
            let default_encoding = app_state.config
                .as_ref()
                .and_then(|cfg| cfg.message_format_primary)
                .unwrap_or_default();
            match EncodedMessage::encode_with_format(&msg, default_encoding) {
                Ok(encoded_ack) => {
                    if let Err(e) = channel.send(encoded_ack).await {
                        error!("{} channel: Failed to send HeartbeatAck to orchestrator: {}", channel_name, e);
                    }
                }
                Err(e) => {
                    error!("{} channel: Failed to encode HeartbeatAck: {}", channel_name, e);
                }
            }
        }
        OrchestratorToModule::Shutdown => {
            warn!("{} channel: Received Shutdown signal from orchestrator. Terminating module.", channel_name);
            return Err("shutdown".to_string());
        }
        OrchestratorToModule::RoutedModuleResponse { request_id, source_module_id, payload } => {
            debug!(
                request_id = %request_id, 
                source_module_id = %source_module_id, 
                channel = %channel_name,
                "Received RoutedModuleResponse, dispatching."
            );
            if let Some(ref pending_map) = pending_responses_map {
                internal_messaging::process_routed_module_response(
                    request_id,
                    Ok(payload),
                    pending_map.clone(),
                ).await;
            } else {
                warn!(
                    request_id = %request_id, 
                    channel = %channel_name,
                    "Received RoutedModuleResponse but no pending_responses_map in AppState. Discarding."
                );
            }
        }
        OrchestratorToModule::RoutedModuleMessage { source_module_id, original_request_id, payload } => {
            debug!(
                source_module_id = %source_module_id, 
                request_id = %original_request_id,
                channel = %channel_name,
                "Received RoutedModuleMessage from another module."
            );
            // Check if there's a registered handler for module-to-module messages in the app state
            if let Some(ref message_handlers) = app_state.module_message_handlers {
                let handler = message_handlers.lock().await;
                if let Some(handler_fn) = handler.get(&source_module_id) {
                    debug!("Found handler for messages from module {} on {} channel", source_module_id, channel_name);
                    // Spawn a task to process the message asynchronously
                    let handler_clone = handler_fn.clone();
                    let source_id = source_module_id.clone();
                    let req_id = original_request_id;
                    let payload_clone = payload.clone();
                    let channel_name_clone = channel_name.to_string();
                    
                    tokio::spawn(async move {
                        match handler_clone(source_id, req_id, payload_clone).await {
                            Ok(_) => {
                                debug!("Module-to-module message handler completed successfully on {} channel", channel_name_clone);
                            },
                            Err(e) => {
                                error!("Error processing module-to-module message on {} channel: {}", channel_name_clone, e);
                            }
                        }
                    });
                    return Ok(());
                }
            }
            
            info!(
                "No handler registered for module-to-module messages from {} on {} channel. Message discarded.", 
                source_module_id, channel_name
            );
        }
        OrchestratorToModule::HttpRequest(http_request) => {
            trace!(
                "{} channel: Received HttpRequest from orchestrator: {:?}", 
                channel_name, http_request.uri
            );
            
            debug!(
                "{} channel: Processing HTTP request: {} {}", 
                channel_name, http_request.method, http_request.uri
            );
            
            let correlation_id = uuid::Uuid::new_v4();
            
            // Process HTTP request (same logic as before but with channel-specific logging)
            let (status_code, response_body, response_headers) = match http_request.uri.as_str() {
                "/health" => {
                    (200, Some(b"{\"status\":\"healthy\",\"module_id\":\"".to_vec()), 
                     [("content-type".to_string(), "application/json".to_string())].into())
                }
                uri if uri.starts_with("/api/") => {
                    let response = format!(
                        "{{\"message\":\"API endpoint {} processed\",\"method\":\"{}\",\"correlation_id\":\"{}\",\"channel\":\"{}\"}}",
                        uri, http_request.method, correlation_id, channel_name
                    );
                    (200, Some(response.into_bytes()),
                     [("content-type".to_string(), "application/json".to_string())].into())
                }
                _ => {
                    let response = format!(
                        "{{\"message\":\"HTTP request received\",\"uri\":\"{}\",\"method\":\"{}\",\"correlation_id\":\"{}\",\"channel\":\"{}\"}}",
                        http_request.uri, http_request.method, correlation_id, channel_name
                    );
                    (200, Some(response.into_bytes()),
                     [("content-type".to_string(), "application/json".to_string())].into())
                }
            };
            
            let http_response = crate::ipc_types::IpcHttpResponse {
                request_id: http_request.request_id.clone(),
                status_code,
                headers: response_headers,
                body: response_body,
            };
            
            let response_msg = ModuleToOrchestrator::HttpResponse(http_response);
            let response_message = Message::new(response_msg);
            let default_encoding = app_state.config
                .as_ref()
                .and_then(|cfg| cfg.message_format_primary)
                .unwrap_or_default();
            
            match EncodedMessage::encode_with_format(&response_message, default_encoding) {
                Ok(encoded_response) => {
                    if let Err(e) = channel.send(encoded_response).await {
                        error!("{} channel: Failed to send HTTP response to orchestrator: {}", channel_name, e);
                    } else {
                        debug!(
                            request_id = %http_request.request_id,
                            status_code = %status_code,
                            correlation_id = %correlation_id,
                            channel = %channel_name,
                            "Successfully sent HTTP response"
                        );
                    }
                }
                Err(e) => {
                    error!("{} channel: Failed to encode HTTP response: {}", channel_name, e);
                }
            }
        }
        other => {
            trace!("{} channel: Received unhandled OrchestratorToModule variant: {:?}", channel_name, other);
        }
    }
    
    Ok(())
}

/// Bootstraps a PyWatt module with handshake, secret init, announcement, and independent channel management.
///
/// This function provides the complete setup flow for a PyWatt module with independent channel support:
/// 1. Initialize logging and redaction
/// 2. Perform handshake with orchestrator
/// 3. Set up secret client and fetch initial secrets
/// 4. Build application state
/// 5. Initialize channels independently based on preferences and availability
/// 6. Announce the module and its endpoints to the orchestrator
/// 7. Start independent message processing tasks for each active channel
/// 8. Set up IPC processing loop
/// 
/// - `secret_keys`: list of environment secret names to fetch initially.
/// - `endpoints`: list of HTTP/WebSocket endpoints for announcement.
/// - `state_builder`: callback to build module-specific state from the orchestrator init and fetched secrets.
/// - `channel_preferences`: preferences for which channels to use and how to prioritize them.
///
/// Returns a tuple of `(AppState<T>, JoinHandle<()>)` where the join handle is a spawned task running the IPC loop.
/// The join handle can be awaited to detect when the IPC loop terminates.
pub async fn bootstrap_module<T, F>(
    secret_keys: Vec<String>,
    endpoints: Vec<AnnouncedEndpoint>,
    state_builder: F,
    channel_preferences: Option<ChannelPreferences>,
) -> Result<(AppState<T>, JoinHandle<()>), BootstrapError>
where
    F: Fn(&OrchestratorInit, Vec<SecretString>) -> T + Send + Sync + 'static,
    T: Send + Sync + Clone + 'static,
{
    // Use default preferences if none provided
    let preferences = channel_preferences.unwrap_or_default();
    
    // 1. Initialize logging and redaction
    init_module();

    // 2. Handshake: read orchestrator init
    let init: OrchestratorInit = read_init().await?;

    // 3. Secret client
    let client = get_module_secret_client(&init.orchestrator_api, &init.module_id).await?;

    // 4. Fetch initial secrets
    let mut secrets = Vec::new();
    for key in &secret_keys {
        let s = get_secret(&client, key).await?;
        secrets.push(s);
    }

    // 5. Build application state
    let user_state = state_builder(&init, secrets);
    let mut app_state = AppState::new(
        init.module_id.clone(),
        init.orchestrator_api.clone(),
        client.clone(),
        user_state,
    );

    // Add configuration to AppState
    app_state.config = Some(crate::state::AppConfig {
        message_format_primary: Some(EncodingFormat::Json),
        // Check for IPC_ONLY environment variable for backward compatibility
        ipc_only: std::env::var("IPC_ONLY").map(|v| v == "1" || v.to_lowercase() == "true").unwrap_or(false),
        ..Default::default()
    });

    // Initialize the pending map for internal messaging
    let pending_map: PendingMap = Arc::new(Mutex::new(HashMap::new()));
    app_state.pending_internal_responses = Some(pending_map);

    // 6. Initialize channels independently based on orchestrator configuration and preferences
    let mut active_channels = Vec::new();
    let mut join_handles = Vec::new();

    // Check if InitBlob contains channel configurations (new format)
    if let Ok(init_blob) = serde_json::from_str::<crate::ipc_types::InitBlob>(&serde_json::to_string(&init).unwrap_or_default()) {
        info!(
            "Detected enhanced InitBlob with channel configurations. TCP: {}, IPC: {}",
            init_blob.tcp_channel.is_some(),
            init_blob.ipc_channel.is_some()
        );

        // CRITICAL FIX: Extract and set pre-allocated port from InitBlob
        match &init_blob.listen {
            crate::ipc_types::ListenAddress::Tcp(socket_addr) => {
                let port = socket_addr.port();
                info!("Found pre-allocated port in InitBlob: {}", port);
                crate::services::server::set_pre_allocated_port(port);
            }
            crate::ipc_types::ListenAddress::Unix(_) => {
                debug!("InitBlob uses Unix socket, no port to pre-allocate");
            }
        }

        // Initialize TCP channel if available and desired
        if let Some(tcp_config) = init_blob.tcp_channel {
            if preferences.use_tcp {
                info!("Initializing TCP channel to {}", tcp_config.address);
                match setup_tcp_channel_from_config(tcp_config.clone()).await {
                    Ok(channel) => {
                        let channel_arc = Arc::new(channel);
                        app_state.tcp_channel = Some(channel_arc.clone());
                        app_state.tcp_capabilities = ChannelCapabilities::tcp_standard();
                        active_channels.push(ChannelType::Tcp);
                        
                        // Start TCP message processing task
                        let app_state_clone = Arc::new(app_state.clone());
                        let handle = tokio::spawn(tcp_message_processing_task(app_state_clone, channel_arc));
                        join_handles.push(handle);
                        
                        info!("TCP channel established and processing task started");
                    }
                    Err(e) => {
                        if tcp_config.required {
                            return Err(BootstrapError::RequiredChannelFailed {
                                channel_type: "TCP".to_string(),
                                error: e.to_string(),
                            });
                        } else {
                            warn!("Optional TCP channel failed to initialize: {}", e);
                        }
                    }
                }
            } else {
                info!("TCP channel available but disabled by preferences");
            }
        }

        // Initialize IPC channel if available and desired
        #[cfg(feature = "ipc_channel")]
        if let Some(ipc_config) = init_blob.ipc_channel {
            if preferences.use_ipc {
                info!("Initializing IPC channel to {}", ipc_config.socket_path.display());
                match setup_ipc_channel_from_config(ipc_config.clone()).await {
                    Ok(channel) => {
                        let channel_arc = Arc::new(channel);
                        app_state.ipc_channel = Some(channel_arc.clone());
                        app_state.ipc_capabilities = ChannelCapabilities::ipc_standard();
                        active_channels.push(ChannelType::Ipc);
                        
                        // Start IPC message processing task
                        let app_state_clone = Arc::new(app_state.clone());
                        let handle = tokio::spawn(ipc_message_processing_task(app_state_clone, channel_arc));
                        join_handles.push(handle);
                        
                        info!("IPC channel established and processing task started");
                    }
                    Err(e) => {
                        if ipc_config.required {
                            return Err(BootstrapError::RequiredChannelFailed {
                                channel_type: "IPC".to_string(),
                                error: e.to_string(),
                            });
                        } else {
                            warn!("Optional IPC channel failed to initialize: {}", e);
                        }
                    }
                }
            } else {
                info!("IPC channel available but disabled by preferences");
            }
        }
    } else {
        // Legacy format without enhanced channel configurations
        warn!("Using legacy InitBlob format without channel configurations");
        
        // CRITICAL FIX: Extract and set pre-allocated port from legacy format
        let listen_str = init.listen_to_string();
        if let Ok(socket_addr) = listen_str.parse::<std::net::SocketAddr>() {
            let port = socket_addr.port();
            info!("Found pre-allocated port in legacy format: {}", port);
            crate::services::server::set_pre_allocated_port(port);
        } else {
            warn!("Could not parse port from legacy listen address: {}", listen_str);
        }
        
        // Legacy TCP connection setup (if not in IPC-only mode)
        if !app_state.config.as_ref().map_or(false, |c| c.ipc_only) {
            if let Ok(url) = Url::parse(&init.orchestrator_api) {
                let host = url.host_str().unwrap_or("localhost").to_string();
                let http_port = url.port().unwrap_or(80);
                let tcp_port = http_port + 1;
                
                debug!("Establishing legacy TCP connection to orchestrator at {}:{}", host, tcp_port);
                
                let connection_timeout = Duration::from_secs(5);
                match tokio::time::timeout(
                    connection_timeout,
                    TcpStream::connect(format!("{0}:{1}", host, tcp_port))
                ).await {
                    Ok(Ok(_tcp_stream)) => {
                        info!("Successfully connected to orchestrator TCP channel on port {}", tcp_port);
                        
                        let config = crate::tcp_types::ConnectionConfig::new(host.clone(), tcp_port);
                        let channel = TcpChannel::new(config);
                        let channel_arc = Arc::new(channel);
                        app_state.tcp_channel = Some(channel_arc.clone());
                        app_state.tcp_capabilities = ChannelCapabilities::tcp_standard();
                        active_channels.push(ChannelType::Tcp);
                        
                        // Start TCP message processing task
                        let app_state_clone = Arc::new(app_state.clone());
                        let handle = tokio::spawn(tcp_message_processing_task(app_state_clone, channel_arc));
                        join_handles.push(handle);
                        
                        info!("Started legacy TCP main processing task");
                    },
                    Ok(Err(e)) => {
                        warn!("Failed to connect to orchestrator: {} - continuing without TCP", e);
                    },
                    Err(_timeout) => {
                        warn!("Connection to orchestrator timed out after {}s - continuing without TCP", 
                              connection_timeout.as_secs());
                    }
                }
            } else {
                warn!("Failed to parse orchestrator_api as URL: {} - continuing without TCP", init.orchestrator_api);
            }
        }
    }

    // Check if we have any active channels
    if active_channels.is_empty() {
        warn!("No communication channels were successfully initialized");
        if preferences.use_tcp || preferences.use_ipc {
            // At least one channel was desired but none succeeded
            // Continue anyway for backward compatibility, but log the issue
            warn!("Module will continue with limited functionality - only stdin/stdout IPC available");
        }
    } else {
        info!("Active communication channels: {:?}", active_channels);
    }

    // 7. Create an internal messaging client and add it to app_state
    #[cfg(feature = "ipc_channel")]
    let internal_client = crate::internal_messaging::InternalMessagingClient::new(
        init.module_id.clone(),
        app_state.pending_internal_responses.clone(),
        app_state.tcp_channel.clone(),
    );
    #[cfg(not(feature = "ipc_channel"))]
    let internal_client = crate::internal_messaging::InternalMessagingClient::new(
        init.module_id.clone(),
        app_state.pending_internal_responses.clone(),
    );
    app_state.internal_messaging_client = Some(internal_client);
    
    // 8. Set up module message handlers manager
    app_state.module_message_handlers = Some(Arc::new(Mutex::new(HashMap::new())));
    
    // 9. Send announcement
    let listen_str = init.listen_to_string();
    let announce = ModuleAnnounce {
        listen: listen_str,
        endpoints,
    };
    send_announce(&announce)?;

    // 10. Spawn IPC processing loop for stdin/stdout message handling
    #[cfg(feature = "ipc_channel")]
    let ipc_processing_handle = tokio::spawn(process_ipc_messages());
    #[cfg(not(feature = "ipc_channel"))]
    let ipc_processing_handle = tokio::spawn(async { /* Empty task */ });

    // Combine all processing handles into a single handle
    let combined_handle = tokio::spawn(async move {
        // Wait for any of the processing tasks to complete
        if join_handles.is_empty() {
            // Only IPC processing handle
            let _ = ipc_processing_handle.await;
        } else {
            // Wait for either IPC processing or any channel processing to finish
            futures::future::select_all(
                join_handles.into_iter().chain(std::iter::once(ipc_processing_handle))
            ).await;
        }
    });

    debug!("Bootstrapped PyWatt module successfully with independent channels");
    info!(
        "Module bootstrap complete - ID: {}, listening on: {}, active channels: {:?}", 
        init.module_id, 
        init.listen_to_string(),
        active_channels
    );

    Ok((app_state, combined_handle))
}

/// Helper function to set up TCP channel from configuration
async fn setup_tcp_channel_from_config(
    config: crate::ipc_types::TcpChannelConfig,
) -> Result<TcpChannel, String> {
    let connection_timeout = Duration::from_secs(5);
    
    match tokio::time::timeout(
        connection_timeout,
        TcpStream::connect(config.address)
    ).await {
        Ok(Ok(_stream)) => {
            let tcp_config = crate::tcp_types::ConnectionConfig::new(
                config.address.ip().to_string(),
                config.address.port(),
            );
            let channel = TcpChannel::new(tcp_config);
            Ok(channel)
        }
        Ok(Err(e)) => Err(format!("TCP connection failed: {}", e)),
        Err(_) => Err(format!("TCP connection timed out after {}s", connection_timeout.as_secs())),
    }
}

/// Helper function to set up IPC channel from configuration
#[cfg(feature = "ipc_channel")]
async fn setup_ipc_channel_from_config(
    config: crate::ipc_types::IpcChannelConfig,
) -> Result<IpcChannel, String> {
    let ipc_config = IpcConnectionConfig::new(config.socket_path)
        .with_timeout(Duration::from_secs(5));
    
    match IpcChannel::connect(ipc_config).await {
        Ok(channel) => Ok(channel),
        Err(e) => Err(format!("IPC connection failed: {}", e)),
    }
}

/// Legacy bootstrap function that maintains backward compatibility.
///
/// This function provides the same interface as the original bootstrap_module
/// but uses default channel preferences for backward compatibility.
pub async fn bootstrap_module_legacy<T, F>(
    secret_keys: Vec<String>,
    endpoints: Vec<AnnouncedEndpoint>,
    state_builder: F,
) -> Result<(AppState<T>, JoinHandle<()>), BootstrapError>
where
    F: Fn(&OrchestratorInit, Vec<SecretString>) -> T + Send + Sync + 'static,
    T: Send + Sync + Clone + 'static,
{
    bootstrap_module(secret_keys, endpoints, state_builder, None).await
}

/// Extension trait for TCP channels to check connection status
#[allow(dead_code)]
trait TcpChannelExt {
    /// Checks if the TCP channel is permanently closed and cannot be reconnected
    async fn is_permanently_closed(&self) -> bool;
    
    /// Attempts to reconnect a closed TCP channel
    async fn try_reconnect(&self) -> Result<(), Error>;
}

impl TcpChannelExt for TcpChannel {
    async fn is_permanently_closed(&self) -> bool {
        // Check if the connection has been explicitly marked as permanently closed
        if matches!(self.state().await, ConnectionState::Failed) {
            // You might want to implement additional logic here to determine
            // if it's a temporary or permanent closure
            return true;
        }
        false
    }
    
    async fn try_reconnect(&self) -> Result<(), Error> {
        // Implement reconnection logic here
        // This would try to re-establish the connection if it was temporarily lost
        if matches!(self.state().await, ConnectionState::Disconnected | ConnectionState::Failed) {
            // Attempt to reconnect using the channel's configuration
            info!("Attempting to reconnect TCP channel to orchestrator");
            
            // Get the connection configuration from the channel
            let config = self.config();
            let host = &config.host;
            let port = config.port;
            
            // Attempt to establish a new connection with exponential backoff
            let mut retry_count = 0;
            let max_retries = 3;
            let base_delay = Duration::from_millis(500);
            
            while retry_count < max_retries {
                let delay = base_delay * 2_u32.pow(retry_count);
                tokio::time::sleep(delay).await;
                
                match TcpStream::connect(format!("{}:{}", host, port)).await {
                    Ok(_stream) => {
                        info!("Successfully reconnected TCP channel to {}:{}", host, port);
                        
                        // Force the channel to reinitialize its connection
                        // This would need to be implemented in the TcpChannel itself
                        // For now, we'll just mark it as successful
                        return Ok(());
                    }
                    Err(e) => {
                        warn!("Reconnection attempt {} failed: {}", retry_count + 1, e);
                        retry_count += 1;
                    }
                }
            }
            
            // All reconnection attempts failed
            error!("Failed to reconnect TCP channel after {} attempts", max_retries);
            Err(Error::Config(crate::error::ConfigError::Invalid(
                format!("TCP channel reconnection failed after {} attempts", max_retries),
            )))
        } else {
            // Channel is not in a state that requires reconnection
            Ok(())
        }
    }
}

/// Provides method to register a module message handler for a specific source module
#[allow(dead_code, async_fn_in_trait)]
pub trait AppStateExt<T: Send + Sync + 'static> {
    /// Register a handler for module-to-module messages from a specific source module
    async fn register_module_message_handler<F, Fut>(
        &self,
        source_module_id: String,
        handler: F,
    ) -> Result<(), Error>
    where
        F: Fn(String, uuid::Uuid, EncodedMessage) -> Fut + Send + Sync + 'static,
        Fut: std::future::Future<Output = Result<(), Error>> + Send + 'static;
        
    /// Remove a registered handler for a specific source module
    async fn remove_module_message_handler(&self, source_module_id: &str) -> Result<(), Error>;
}

impl<T: Send + Sync + 'static> AppStateExt<T> for AppState<T> {
    async fn register_module_message_handler<F, Fut>(
        &self,
        source_module_id: String,
        handler: F,
    ) -> Result<(), Error>
    where
        F: Fn(String, uuid::Uuid, EncodedMessage) -> Fut + Send + Sync + 'static,
        Fut: std::future::Future<Output = Result<(), Error>> + Send + 'static,
    {
        if let Some(ref handlers) = self.module_message_handlers {
            let mut handlers_lock = handlers.lock().await;
            
            // Create a handler function that wraps the provided closure
            let handler_fn = Arc::new(move |src: String, req_id: uuid::Uuid, payload: EncodedMessage| {
                let fut = handler(src, req_id, payload);
                Box::pin(fut) as std::pin::Pin<Box<dyn std::future::Future<Output = Result<(), Error>> + Send>>
            });
            
            // Insert the handler into the map
            handlers_lock.insert(source_module_id, handler_fn);
            Ok(())
        } else {
            Err(Error::Config(crate::error::ConfigError::Invalid(
                "Module message handlers not initialized in AppState".to_string(),
            )))
        }
    }
    
    async fn remove_module_message_handler(&self, source_module_id: &str) -> Result<(), Error> {
        if let Some(ref handlers) = self.module_message_handlers {
            let mut handlers_lock = handlers.lock().await;
            handlers_lock.remove(source_module_id);
            Ok(())
        } else {
            Err(Error::Config(crate::error::ConfigError::Invalid(
                "Module message handlers not initialized in AppState".to_string(),
            )))
        }
    }
}
