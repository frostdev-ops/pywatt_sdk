use crate::secret_client::SecretClient;
use std::sync::Arc;
use std::collections::HashMap;
use tokio::sync::Mutex;
use std::future::Future;
use std::pin::Pin;

#[cfg(feature = "builder")]
use crate::builder::AppStateBuilder;

use crate::message::EncodingFormat;
use crate::message::EncodedMessage;
use crate::tcp_channel::TcpChannel;
use crate::{
    internal_messaging::{InternalMessagingClient, PendingInternalResponses},
    Error,
};

// Import channel types and preferences
use crate::communication::{
    ChannelPreferences, ChannelType, ChannelCapabilities, MessageChannel,
    // Advanced features
    ChannelRouter, RoutingConfig, FailoverManager, FailoverConfig,
    PerformanceMonitoringSystem, 
    SlaConfig, AlertConfig, StreamConfig, PriorityMessageQueue, RequestMultiplexer,
};

// Import IPC channel when available
#[cfg(feature = "ipc_channel")]
use crate::communication::{IpcChannel};

use crate::message::MessageError;

/// Function signature for module-to-module message handlers
pub type ModuleMessageHandler = Arc<dyn Fn(String, uuid::Uuid, EncodedMessage) -> Pin<Box<dyn Future<Output = Result<(), Error>> + Send>> + Send + Sync>;

/// Configuration for the application.
#[derive(Clone, Debug, Default)]
pub struct AppConfig {
    /// Primary message format for encoding outgoing messages
    pub message_format_primary: Option<EncodingFormat>,
    /// Secondary message format for fallback encoding
    pub message_format_secondary: Option<EncodingFormat>,
    /// Timeout for IPC requests in milliseconds
    pub ipc_timeout_ms: Option<u64>,
    /// Whether the module should operate in IPC-only mode (no TCP connections)
    pub ipc_only: bool,
    /// Enable advanced features
    pub enable_advanced_features: bool,
    /// Routing configuration
    pub routing_config: Option<RoutingConfig>,
    /// Failover configuration
    pub failover_config: Option<FailoverConfig>,
    /// SLA configuration for monitoring
    pub sla_config: Option<SlaConfig>,
    /// Alert configuration
    pub alert_config: Option<AlertConfig>,
    /// Streaming configuration
    pub stream_config: Option<StreamConfig>,
}

/// Shared application state for a PyWatt module with independent channel support and advanced features.
///
/// Contains SDK-provided fields (`module_id`, `orchestrator_api`, `secret_client`)
/// plus user-defined state of type `T`, independent communication channels, and
/// advanced features for performance, reliability, and monitoring.
#[derive(Clone)]
pub struct AppState<T> {
    module_id: String,
    orchestrator_api: String,
    secret_client: Arc<SecretClient>,
    /// User-provided application state
    pub user_state: T,
    pub internal_messaging_client: Option<InternalMessagingClient>,
    pub pending_internal_responses: Option<PendingInternalResponses>,
    /// Application configuration
    pub config: Option<AppConfig>,
    
    // Independent communication channels
    /// TCP channel for communication with the orchestrator
    pub tcp_channel: Option<Arc<TcpChannel>>,
    /// IPC channel for communication with the orchestrator (Unix Domain Sockets)
    #[cfg(feature = "ipc_channel")]
    pub ipc_channel: Option<Arc<IpcChannel>>,
    
    // Channel capabilities
    /// Capabilities supported by the TCP channel
    pub tcp_capabilities: ChannelCapabilities,
    /// Capabilities supported by the IPC channel
    pub ipc_capabilities: ChannelCapabilities,
    
    /// Handlers for module-to-module messages, keyed by source module ID
    pub module_message_handlers: Option<Arc<Mutex<HashMap<String, ModuleMessageHandler>>>>,
    
    // Advanced Features
    /// Smart channel routing engine
    pub channel_router: Option<Arc<ChannelRouter>>,
    /// Failover management system
    pub failover_manager: Option<Arc<FailoverManager>>,
    /// Performance monitoring system
    pub performance_monitoring: Option<Arc<PerformanceMonitoringSystem>>,
    /// Priority message queue
    pub priority_queue: Option<Arc<PriorityMessageQueue>>,
    /// Request multiplexer for concurrent operations
    pub request_multiplexer: Option<Arc<RequestMultiplexer>>,
}

impl<T> AppState<T> {
    /// Create a new `AppState` with the given SDK context and user state.
    pub fn new(
        module_id: String,
        orchestrator_api: String,
        secret_client: Arc<SecretClient>,
        user_state: T,
    ) -> Self {
        Self {
            module_id,
            orchestrator_api,
            secret_client,
            user_state,
            internal_messaging_client: None,
            pending_internal_responses: None,
            config: Some(AppConfig::default()),
            tcp_channel: None,
            #[cfg(feature = "ipc_channel")]
            ipc_channel: None,
            tcp_capabilities: ChannelCapabilities::tcp_standard(),
            ipc_capabilities: ChannelCapabilities::ipc_standard(),
            module_message_handlers: Some(Arc::new(Mutex::new(HashMap::new()))),
            channel_router: None,
            failover_manager: None,
            performance_monitoring: None,
            priority_queue: None,
            request_multiplexer: None,
        }
    }

    /// Create a new `AppState` with advanced features enabled.
    pub fn with_advanced_features(
        module_id: String,
        orchestrator_api: String,
        secret_client: Arc<SecretClient>,
        user_state: T,
        config: AppConfig,
    ) -> Self {
        let mut state = Self::new(module_id, orchestrator_api, secret_client, user_state);
        state.config = Some(config.clone());
        
        if config.enable_advanced_features {
            // Initialize smart routing
            if let Some(routing_config) = config.routing_config {
                state.channel_router = Some(Arc::new(ChannelRouter::new(routing_config)));
            } else {
                state.channel_router = Some(Arc::new(ChannelRouter::new(RoutingConfig::default())));
            }
            
            // Initialize failover management
            if let Some(failover_config) = config.failover_config {
                state.failover_manager = Some(Arc::new(FailoverManager::new(failover_config)));
            } else {
                state.failover_manager = Some(Arc::new(FailoverManager::new(FailoverConfig::default())));
            }
            
            // Initialize performance monitoring
            let sla_config = config.sla_config.unwrap_or_default();
            let alert_config = config.alert_config.unwrap_or_default();
            state.performance_monitoring = Some(Arc::new(
                PerformanceMonitoringSystem::new(sla_config, alert_config)
            ));
            
            // Initialize priority queue
            state.priority_queue = Some(Arc::new(PriorityMessageQueue::new(10000))); // Default 10k messages
            
            // Initialize request multiplexer
            state.request_multiplexer = Some(Arc::new(
                RequestMultiplexer::new(std::time::Duration::from_secs(30))
            ));
        }
        
        state
    }

    /// Returns the module's ID.
    pub fn module_id(&self) -> &str {
        &self.module_id
    }

    /// Returns the orchestrator API URL.
    pub fn orchestrator_api(&self) -> &str {
        &self.orchestrator_api
    }

    /// Returns the configured `SecretClient` instance.
    pub fn secret_client(&self) -> &Arc<SecretClient> {
        &self.secret_client
    }

    /// Returns a reference to the custom user state.
    pub fn custom(&self) -> &T {
        &self.user_state
    }

    /// Retrieves a reference to the `InternalMessagingClient` if available.
    pub fn internal_messaging_client(&self) -> Option<&InternalMessagingClient> {
        self.internal_messaging_client.as_ref()
    }

    /// Retrieves a clone of the `PendingInternalResponses` map if available.
    pub fn pending_internal_responses_map(&self) -> Option<PendingInternalResponses> {
        self.pending_internal_responses.as_ref().cloned()
    }

    /// Creates a new `AppStateBuilder` for fluent API construction.
    #[cfg(feature = "builder")]
    pub fn builder() -> AppStateBuilder<T> {
        AppStateBuilder::new()
    }

    /// Send a message using the best available channel based on preferences with advanced routing.
    ///
    /// This method automatically selects the appropriate channel based on the target,
    /// channel preferences, message characteristics, and uses the smart routing engine
    /// for optimal performance and reliability.
    pub async fn send_message(
        &self,
        target: &str,
        message: EncodedMessage,
        preferences: Option<ChannelPreferences>,
    ) -> Result<(), Error> {
        // Use advanced routing if available
        if let Some(router) = &self.channel_router {
            let available_channels = self.available_channels();
            let characteristics = crate::communication::extract_message_characteristics(
                &message,
                None, // Could extract from message metadata
                target,
            );
            
            if let Some(routing_decision) = router.route_message(
                &message,
                target,
                characteristics,
                &available_channels,
            ).await {
                tracing::debug!("Using smart routing: {}", routing_decision.reason);
                
                // Try primary channel with failover protection
                let result = self.send_via_channel_with_failover(
                    routing_decision.primary_channel,
                    message.clone(),
                ).await;
                
                // Record routing outcome
                router.record_outcome(
                    routing_decision.primary_channel,
                    result.is_ok(),
                    None, // Could measure actual latency
                ).await;
                
                // Try fallback if primary failed
                if result.is_err() {
                    if let Some(fallback_channel) = routing_decision.fallback_channel {
                        tracing::debug!("Primary channel failed, trying fallback: {:?}", fallback_channel);
                        
                        let fallback_result = self.send_via_channel_with_failover(
                            fallback_channel,
                            message,
                        ).await;
                        
                        router.record_outcome(
                            fallback_channel,
                            fallback_result.is_ok(),
                            None,
                        ).await;
                        
                        return fallback_result;
                    }
                }
                
                return result;
            }
        }
        
        // Fallback to basic routing
        self.send_message_basic(target, message, preferences).await
    }
    
    /// Send a message with failover protection
    async fn send_via_channel_with_failover(
        &self,
        channel_type: ChannelType,
        message: EncodedMessage,
    ) -> Result<(), Error> {
        // Use failover manager if available
        if let Some(failover_manager) = &self.failover_manager {
            let start_time = std::time::Instant::now();
            
            let result = failover_manager.execute_with_failover(
                channel_type,
                || async {
                    self.send_message_via_channel(channel_type, message.clone()).await
                        .map_err(|e| MessageError::InvalidFormat(e.to_string()))
                },
            ).await;
            
            let latency = start_time.elapsed();
            
            // Record metrics if monitoring is enabled
            if let Some(monitoring) = &self.performance_monitoring {
                let tracker = monitoring.get_tracker(channel_type).await;
                
                match &result {
                    Ok(_) => tracker.record_message_sent(message.data().len() as u64, latency),
                    Err(_) => tracker.record_failure(),
                }
            }
            
            result.map_err(|e| Error::Config(crate::core::error::ConfigError::Invalid(e.to_string())))
        } else {
            // Direct send without failover
            self.send_message_via_channel(channel_type, message).await
        }
    }
    
    /// Basic message sending without advanced features (fallback)
    async fn send_message_basic(
        &self,
        target: &str,
        message: EncodedMessage,
        preferences: Option<ChannelPreferences>,
    ) -> Result<(), Error> {
        let prefs = preferences.unwrap_or_default();
        
        // For local communication, prefer IPC if available and preferred
        if prefs.prefer_ipc_for_local {
            #[cfg(feature = "ipc_channel")]
            if let Some(ipc) = &self.ipc_channel {
                match ipc.send(message.clone()).await {
                    Ok(()) => {
                        tracing::debug!("Message sent successfully via IPC channel to {}", target);
                        return Ok(());
                    }
                    Err(e) => {
                        tracing::warn!("IPC send failed for target {}, trying TCP: {}", target, e);
                        if !prefs.enable_fallback {
                            return Err(Error::Config(crate::core::error::ConfigError::Invalid(format!("IPC send failed: {}", e))));
                        }
                    }
                }
            }
        }
        
        // Try TCP channel (either as preference or fallback)
        if let Some(tcp) = &self.tcp_channel {
            match tcp.send(message.clone()).await {
                Ok(()) => {
                    tracing::debug!("Message sent successfully via TCP channel to {}", target);
                    return Ok(());
                }
                Err(e) => {
                    tracing::warn!("TCP send failed for target {}: {}", target, e);
                    
                    // If TCP was preferred and we haven't tried IPC yet, try it now
                    if prefs.prefer_tcp_for_remote && prefs.enable_fallback {
                        #[cfg(feature = "ipc_channel")]
                        if let Some(ipc) = &self.ipc_channel {
                            match ipc.send(message).await {
                                Ok(()) => {
                                    tracing::debug!("Message sent successfully via IPC channel (fallback) to {}", target);
                                    return Ok(());
                                }
                                Err(ipc_e) => {
                                    tracing::error!("Both TCP and IPC send failed for target {}: TCP: {}, IPC: {}", target, e, ipc_e);
                                    return Err(Error::Config(crate::core::error::ConfigError::Invalid(format!("All channels failed: TCP: {}, IPC: {}", e, ipc_e))));
                                }
                            }
                        }
                    }
                    
                    return Err(Error::Config(crate::core::error::ConfigError::Invalid(format!("TCP send failed: {}", e))));
                }
            }
        }
        
        // No channels available
        tracing::error!("No available channels for sending message to {}", target);
        Err(Error::Config(crate::core::error::ConfigError::Invalid("No channels available for communication".to_string())))
    }
    
    /// Send a message using a specific channel type.
    ///
    /// This method allows explicit channel selection when the caller knows
    /// which channel they want to use, bypassing the automatic selection logic.
    pub async fn send_message_via_channel(
        &self,
        channel_type: ChannelType,
        message: EncodedMessage,
    ) -> Result<(), Error> {
        match channel_type {
            ChannelType::Tcp => {
                if let Some(tcp) = &self.tcp_channel {
                    tcp.send(message).await
                        .map_err(|e| Error::Config(crate::core::error::ConfigError::Invalid(format!("TCP channel error: {}", e))))
                } else {
                    Err(Error::Config(crate::core::error::ConfigError::Invalid("TCP channel not available".to_string())))
                }
            }
            ChannelType::Ipc => {
                #[cfg(feature = "ipc_channel")]
                {
                    if let Some(ipc) = &self.ipc_channel {
                        ipc.send(message).await
                            .map_err(|e| Error::Config(crate::core::error::ConfigError::Invalid(format!("IPC channel error: {}", e))))
                    } else {
                        Err(Error::Config(crate::core::error::ConfigError::Invalid("IPC channel not available".to_string())))
                    }
                }
                #[cfg(not(feature = "ipc_channel"))]
                {
                    Err(Error::Config(crate::core::error::ConfigError::Invalid("IPC channel not compiled in".to_string())))
                }
            }
        }
    }
    
    /// Send a request and wait for response using request multiplexing
    pub async fn send_request(
        &self,
        target: &str,
        request: EncodedMessage,
        preferences: Option<ChannelPreferences>,
    ) -> Result<EncodedMessage, Error> {
        if let Some(multiplexer) = &self.request_multiplexer {
            // Get the appropriate channel
            let channel_type = self.recommend_channel(target, preferences).unwrap_or(ChannelType::Tcp);
            let channel = self.get_channel_arc(channel_type).ok_or_else(|| {
                Error::Config(crate::core::error::ConfigError::Invalid("No suitable channel available".to_string()))
            })?;
            
            multiplexer.send_request(request, channel).await
                .map_err(|e| Error::Config(crate::core::error::ConfigError::Invalid(e.to_string())))
        } else {
            Err(Error::Config(crate::core::error::ConfigError::Invalid("Request multiplexing not enabled".to_string())))
        }
    }
    
    /// Get channel as Arc<dyn MessageChannel> for advanced features
    fn get_channel_arc(&self, channel_type: ChannelType) -> Option<Arc<dyn MessageChannel>> {
        match channel_type {
            ChannelType::Tcp => {
                self.tcp_channel.as_ref().map(|tcp| tcp.clone() as Arc<dyn MessageChannel>)
            }
            ChannelType::Ipc => {
                #[cfg(feature = "ipc_channel")]
                {
                    self.ipc_channel.as_ref().map(|ipc| ipc.clone() as Arc<dyn MessageChannel>)
                }
                #[cfg(not(feature = "ipc_channel"))]
                {
                    None
                }
            }
        }
    }
    
    /// Get the available channel types.
    ///
    /// Returns a vector of channel types that are currently available and connected.
    pub fn available_channels(&self) -> Vec<ChannelType> {
        let mut channels = Vec::new();
        
        if self.tcp_channel.is_some() {
            channels.push(ChannelType::Tcp);
        }
        
        #[cfg(feature = "ipc_channel")]
        if self.ipc_channel.is_some() {
            channels.push(ChannelType::Ipc);
        }
        
        channels
    }
    
    /// Get the capabilities of a specific channel.
    ///
    /// Returns the capabilities supported by the specified channel type,
    /// or None if the channel is not available.
    pub fn channel_capabilities(&self, channel_type: ChannelType) -> Option<&ChannelCapabilities> {
        match channel_type {
            ChannelType::Tcp => {
                if self.tcp_channel.is_some() {
                    Some(&self.tcp_capabilities)
                } else {
                    None
                }
            }
            ChannelType::Ipc => {
                #[cfg(feature = "ipc_channel")]
                {
                    if self.ipc_channel.is_some() {
                        Some(&self.ipc_capabilities)
                    } else {
                        None
                    }
                }
                #[cfg(not(feature = "ipc_channel"))]
                {
                    None
                }
            }
        }
    }
    
    /// Check if a specific channel type is available.
    ///
    /// Returns true if the specified channel type is configured and available.
    pub fn has_channel(&self, channel_type: ChannelType) -> bool {
        match channel_type {
            ChannelType::Tcp => self.tcp_channel.is_some(),
            ChannelType::Ipc => {
                #[cfg(feature = "ipc_channel")]
                {
                    self.ipc_channel.is_some()
                }
                #[cfg(not(feature = "ipc_channel"))]
                {
                    false
                }
            }
        }
    }
    
    /// Get channel health status.
    ///
    /// Returns a map of channel types to their current connection status.
    pub async fn channel_health(&self) -> HashMap<ChannelType, bool> {
        let mut health = HashMap::new();
        
        if let Some(tcp) = &self.tcp_channel {
            use crate::communication::MessageChannel;
            use crate::tcp_types::ConnectionState;
            let is_healthy = matches!(tcp.state().await, ConnectionState::Connected);
            health.insert(ChannelType::Tcp, is_healthy);
        }
        
        #[cfg(feature = "ipc_channel")]
        if let Some(ipc) = &self.ipc_channel {
            use crate::communication::MessageChannel;
            use crate::tcp_types::ConnectionState;
            let is_healthy = matches!(ipc.state().await, ConnectionState::Connected);
            health.insert(ChannelType::Ipc, is_healthy);
        }
        
        health
    }
    
    /// Get recommended channel for a target.
    ///
    /// Returns the recommended channel type for communicating with a specific target,
    /// based on channel preferences and availability.
    pub fn recommend_channel(&self, target: &str, preferences: Option<ChannelPreferences>) -> Option<ChannelType> {
        let prefs = preferences.unwrap_or_default();
        let available = self.available_channels();
        
        if available.is_empty() {
            return None;
        }
        
        // Check if target appears to be local (heuristic)
        let is_local_target = target.starts_with("127.0.0.1") || 
                             target.starts_with("localhost") ||
                             target.starts_with("unix://") ||
                             !target.contains(':');
        
        // Apply preferences based on target type
        if is_local_target && prefs.prefer_ipc_for_local {
            if available.contains(&ChannelType::Ipc) {
                return Some(ChannelType::Ipc);
            } else if prefs.enable_fallback && available.contains(&ChannelType::Tcp) {
                return Some(ChannelType::Tcp);
            }
        } else if !is_local_target && prefs.prefer_tcp_for_remote {
            if available.contains(&ChannelType::Tcp) {
                return Some(ChannelType::Tcp);
            } else if prefs.enable_fallback && available.contains(&ChannelType::Ipc) {
                return Some(ChannelType::Ipc);
            }
        }
        
        // Fallback to first available channel
        available.first().copied()
    }
    
    /// Get performance metrics for all channels
    pub async fn get_performance_metrics(&self) -> Result<HashMap<ChannelType, crate::communication::ChannelMetrics>, Error> {
        if let Some(monitoring) = &self.performance_monitoring {
            Ok(monitoring.get_all_metrics().await)
        } else {
            Err(Error::Config(crate::core::error::ConfigError::Invalid("Performance monitoring not enabled".to_string())))
        }
    }
    
    /// Get SLA compliance status for all channels
    pub async fn get_sla_status(&self) -> Result<HashMap<ChannelType, crate::communication::SlaStatus>, Error> {
        if let Some(monitoring) = &self.performance_monitoring {
            Ok(monitoring.get_all_sla_status().await)
        } else {
            Err(Error::Config(crate::core::error::ConfigError::Invalid("Performance monitoring not enabled".to_string())))
        }
    }
    
    /// Get performance comparison report
    pub async fn get_performance_comparison(&self) -> Result<crate::communication::PerformanceComparisonReport, Error> {
        if let Some(monitoring) = &self.performance_monitoring {
            Ok(monitoring.get_performance_comparison().await)
        } else {
            Err(Error::Config(crate::core::error::ConfigError::Invalid("Performance monitoring not enabled".to_string())))
        }
    }
    
    /// Update routing matrix for smart routing
    pub fn update_routing_matrix(&self, matrix: crate::communication::RoutingMatrix) -> Result<(), Error> {
        if let Some(router) = &self.channel_router {
            router.update_routing_matrix(matrix);
            Ok(())
        } else {
            Err(Error::Config(crate::core::error::ConfigError::Invalid("Smart routing not enabled".to_string())))
        }
    }
    
    /// Get current routing matrix
    pub fn get_routing_matrix(&self) -> Result<crate::communication::RoutingMatrix, Error> {
        if let Some(router) = &self.channel_router {
            Ok(router.get_routing_matrix())
        } else {
            Err(Error::Config(crate::core::error::ConfigError::Invalid("Smart routing not enabled".to_string())))
        }
    }
    
    /// Get statistics about pending requests
    pub async fn get_request_stats(&self) -> Result<(usize, Vec<uuid::Uuid>), Error> {
        if let Some(multiplexer) = &self.request_multiplexer {
            Ok(multiplexer.get_stats().await)
        } else {
            Err(Error::Config(crate::core::error::ConfigError::Invalid("Request multiplexing not enabled".to_string())))
        }
    }
    
    /// Enable or disable advanced features at runtime
    pub fn set_advanced_features_enabled(&mut self, enabled: bool) {
        if let Some(config) = &mut self.config {
            config.enable_advanced_features = enabled;
        }
        
        if !enabled {
            // Disable advanced features
            self.channel_router = None;
            self.failover_manager = None;
            self.performance_monitoring = None;
            self.priority_queue = None;
            self.request_multiplexer = None;
        } else if self.channel_router.is_none() {
            // Re-enable advanced features with default configuration
            self.channel_router = Some(Arc::new(ChannelRouter::new(RoutingConfig::default())));
            self.failover_manager = Some(Arc::new(FailoverManager::new(FailoverConfig::default())));
            self.performance_monitoring = Some(Arc::new(
                PerformanceMonitoringSystem::new(SlaConfig::default(), AlertConfig::default())
            ));
            self.priority_queue = Some(Arc::new(PriorityMessageQueue::new(10000)));
            self.request_multiplexer = Some(Arc::new(
                RequestMultiplexer::new(std::time::Duration::from_secs(30))
            ));
        }
    }
}

impl<T: std::fmt::Debug> std::fmt::Debug for AppState<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let mut debug_struct = f.debug_struct("AppState");
        debug_struct
            .field("module_id", &self.module_id)
            .field("orchestrator_api", &self.orchestrator_api)
            .field("user_state", &self.user_state)
            .field("config", &self.config)
            .field("tcp_channel", &self.tcp_channel);
        
        #[cfg(feature = "ipc_channel")]
        debug_struct.field("ipc_channel", &self.ipc_channel);
        
        debug_struct
            .field("tcp_capabilities", &self.tcp_capabilities)
            .field("ipc_capabilities", &self.ipc_capabilities)
            .field("internal_messaging_client", &self.internal_messaging_client)
            .field("pending_internal_responses", &"<pending_responses>")
            .field("module_message_handlers", &"<message_handlers>")
            .field("advanced_features_enabled", &self.channel_router.is_some())
            .finish()
    }
}
