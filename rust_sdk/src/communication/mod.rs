//! All wiring: IPC, TCP, HTTP layers, message encoding.

use std::fmt;
use async_trait::async_trait;

use crate::communication::message::{EncodedMessage, MessageResult};
use crate::communication::tcp_types::ConnectionState;

pub mod message;
pub mod tcp_channel;
pub mod tcp_types;
pub mod ipc;
pub mod ipc_types;
pub mod http_ipc;
pub mod http_tcp;
pub mod ipc_port_negotiation;
pub mod ipc_channel;

// Phase 3 Advanced Features
pub mod routing;
pub mod failover;
pub mod metrics;
pub mod streaming;

/// A trait for channels that can send and receive messages.
///
/// This trait allows for interchangeable use of different communication
/// channels (TCP, Unix Domain Sockets, etc.) with the same interface.
#[async_trait]
pub trait MessageChannel: Send + Sync + fmt::Debug {
    /// Send a message over the channel.
    async fn send(&self, message: EncodedMessage) -> MessageResult<()>;
    
    /// Receive a message from the channel.
    async fn receive(&self) -> MessageResult<EncodedMessage>;
    
    /// Get the current connection state.
    async fn state(&self) -> ConnectionState;
    
    /// Connect or reconnect the channel.
    async fn connect(&self) -> MessageResult<()>;
    
    /// Disconnect the channel.
    async fn disconnect(&self) -> MessageResult<()>;
}

// Re-export PortNegotiationManager for easier access
pub use ipc_port_negotiation::PortNegotiationManager;

// Re-export TcpChannel for easier access
pub use tcp_channel::TcpChannel;

// Re-export IpcChannel when available
#[cfg(feature = "ipc_channel")]
pub use ipc_channel::{IpcChannel, IpcConnectionConfig};

// Channel independence types and traits
use serde::{Serialize, Deserialize};

/// Indicates which type of communication channel to use
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ChannelType {
    /// TCP-based channel
    Tcp,
    /// IPC (Unix Domain Socket) based channel
    Ipc,
}

/// Preferences for channel selection and usage
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChannelPreferences {
    /// Whether to use TCP channel if available
    pub use_tcp: bool,
    /// Whether to use IPC channel if available
    pub use_ipc: bool,
    /// Prefer IPC for local module-to-module communication
    pub prefer_ipc_for_local: bool,
    /// Prefer TCP for cross-host communication
    pub prefer_tcp_for_remote: bool,
    /// Fallback to other channel if preferred fails
    pub enable_fallback: bool,
}

impl Default for ChannelPreferences {
    fn default() -> Self {
        Self {
            use_tcp: true,
            use_ipc: true,
            prefer_ipc_for_local: true,
            prefer_tcp_for_remote: true,
            enable_fallback: true,
        }
    }
}

impl ChannelPreferences {
    /// Create preferences for TCP-only usage
    pub fn tcp_only() -> Self {
        Self {
            use_tcp: true,
            use_ipc: false,
            prefer_ipc_for_local: false,
            prefer_tcp_for_remote: true,
            enable_fallback: false,
        }
    }
    
    /// Create preferences for IPC-only usage
    pub fn ipc_only() -> Self {
        Self {
            use_tcp: false,
            use_ipc: true,
            prefer_ipc_for_local: true,
            prefer_tcp_for_remote: false,
            enable_fallback: false,
        }
    }
    
    /// Create preferences that prefer IPC but allow TCP fallback
    pub fn prefer_ipc() -> Self {
        Self {
            use_tcp: true,
            use_ipc: true,
            prefer_ipc_for_local: true,
            prefer_tcp_for_remote: false,
            enable_fallback: true,
        }
    }
    
    /// Create preferences that prefer TCP but allow IPC fallback
    pub fn prefer_tcp() -> Self {
        Self {
            use_tcp: true,
            use_ipc: true,
            prefer_ipc_for_local: false,
            prefer_tcp_for_remote: true,
            enable_fallback: true,
        }
    }
}

/// Capabilities that a communication channel supports
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChannelCapabilities {
    /// Whether the channel supports module-to-module messaging
    pub module_messaging: bool,
    /// Whether the channel supports HTTP proxying
    pub http_proxy: bool,
    /// Whether the channel supports service calls
    pub service_calls: bool,
    /// Whether the channel supports file transfer (for large payloads)
    pub file_transfer: bool,
    /// Whether the channel supports streaming
    pub streaming: bool,
    /// Whether the channel supports message batching
    pub batching: bool,
    /// Whether the channel supports compression
    pub compression: bool,
    /// Maximum message size supported
    pub max_message_size: Option<usize>,
}

impl Default for ChannelCapabilities {
    fn default() -> Self {
        Self {
            module_messaging: true,
            http_proxy: true,
            service_calls: true,
            file_transfer: false,
            streaming: false,
            batching: false,
            compression: false,
            max_message_size: None,
        }
    }
}

impl ChannelCapabilities {
    /// Standard capabilities for TCP channels
    pub fn tcp_standard() -> Self {
        Self {
            module_messaging: true,
            http_proxy: true,
            service_calls: true,
            file_transfer: true,
            streaming: true,
            batching: true,
            compression: true,
            max_message_size: Some(64 * 1024 * 1024), // 64MB
        }
    }
    
    /// Standard capabilities for IPC channels
    pub fn ipc_standard() -> Self {
        Self {
            module_messaging: true,
            http_proxy: true,
            service_calls: true,
            file_transfer: true,
            streaming: true,
            batching: true,
            compression: true,
            max_message_size: Some(128 * 1024 * 1024), // 128MB (higher for local communication)
        }
    }
    
    /// High-performance capabilities
    pub fn high_performance() -> Self {
        Self {
            module_messaging: true,
            http_proxy: true,
            service_calls: true,
            file_transfer: true,
            streaming: true,
            batching: true,
            compression: true,
            max_message_size: Some(1024 * 1024 * 1024), // 1GB
        }
    }
}

// Re-export advanced features
pub use routing::{
    ChannelRouter, RoutingConfig, RoutingMatrix, RoutingDecision, MessageCharacteristics,
    MessagePriority, MessageType, TargetLocation, ChannelHealth, extract_message_characteristics,
};

pub use failover::{
    FailoverManager, FailoverConfig, CircuitBreaker, CircuitBreakerConfig, CircuitBreakerState,
    CircuitBreakerStats, RetryMechanism, RetryConfig, MessageBatcher, BatchConfig, MessageBatch,
    ConnectionPool, PooledConnection, PoolStats, PerformanceConfig, MessageCompressor,
};

pub use metrics::{
    PerformanceMonitoringSystem, ChannelPerformanceTracker, ChannelMetrics, PoolMetrics,
    SlaConfig, SlaStatus, ComplianceStatus, AlertConfig, PerformanceAlert, AlertType,
    AlertSeverity, PerformanceComparisonReport,
};

pub use streaming::{
    StreamConfig, StreamChunk, StreamMetadata, StreamPriority, StreamAck, FlowControlWindow,
    StreamSender, StreamReceiver, PubSubMessage, Subscription, PriorityMessageQueue,
    RequestMultiplexer,
};