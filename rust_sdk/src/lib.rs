//! PyWatt SDK library root

pub mod core;
pub mod communication;
pub mod services;
pub mod security;
pub mod data;
mod internal; // private helpers

pub mod build;

// Legacy root re-exports for backward compatibility
pub use crate::communication::ipc_types::{Endpoint as AnnouncedEndpoint, Announce as ModuleAnnounce, Init as OrchestratorInit};
pub use crate::core::bootstrap::{BootstrapError, bootstrap_module};
pub use crate::core::error::{Error, Result};
pub use crate::core::state::AppState;
pub use crate::services::announce::{AnnounceError, send_announce};
pub use crate::security::handshake::{InitError, read_init};
pub use crate::services::server::serve_module;

// Core modules
pub use crate::core::bootstrap;
pub use crate::core::error;
pub use crate::core::state;
pub use crate::core::config;
pub use crate::core::logging;

// Communication modules
pub use crate::communication::message;
pub use crate::communication::tcp_channel;
pub use crate::communication::tcp_types;
#[cfg(feature = "ipc_channel")]
pub use crate::communication::ipc;
pub use crate::communication::ipc_types;
pub use crate::communication::http_ipc;
pub use crate::communication::http_tcp;
pub use crate::communication::{MessageChannel, TcpChannel};

// Services modules
pub use crate::services::registration;
pub use crate::services::announce;
pub use crate::services::model_manager;
pub use crate::services::server;

// Security modules
pub use crate::security::secrets;
pub use crate::security::secret_client;
pub use crate::security::secret_provider;
#[cfg(feature = "jwt_auth")]
pub use crate::security::jwt_auth;
pub use crate::security::handshake;

// Re-export typed_secret at crate root for backward compatibility
pub use crate::security::secrets::typed_secret;

// Data modules
#[cfg(feature = "database")]
pub use crate::data::database;
#[cfg(feature = "cache")]
pub use crate::data::cache;

// Internal modules for backward compatibility
pub use crate::internal::builder;
pub use crate::internal::ext;
pub use crate::internal::internal_messaging;
pub use crate::internal::macros;
pub use crate::internal::utils;

// Export the module macro at crate root
#[cfg(feature = "proc_macros")]
pub use crate::internal::macros::module;

// Create a pywatt module alias for backward compatibility
#[cfg(feature = "proc_macros")]
pub mod pywatt {
    pub use crate::internal::macros::module;
}

/// Prelude module that re-exports the most commonly used types and functions.
///
/// This is intended to provide a convenient way to import all the essential
/// types and functions with a single `use pywatt_sdk::prelude::*` statement.
pub mod prelude {
    // Core types and functions
    pub use crate::bootstrap_module;
    pub use crate::core::error::{Error, Result};
    pub use crate::core::state::AppState;
    pub use crate::core::logging::init_module;
    
    // Build information
    pub use crate::build::{BuildInfo, get_build_info};
    
    // Communication types
    pub use crate::communication::message::{
        EncodedMessage, EncodedStream, EncodingFormat, Message, 
        MessageError, MessageMetadata, MessageResult,
    };
    pub use crate::communication::{MessageChannel, TcpChannel};
    pub use crate::communication::tcp_types::{
        ConnectionConfig, ConnectionState, NetworkError, 
        NetworkResult, ReconnectPolicy, TlsConfig,
    };
    pub use crate::communication::ipc_types::{
        ListenAddress, ModuleToOrchestrator, OrchestratorToModule,
        ServiceType, ServiceProviderInfo,
    };
    
    // IPC functions (conditionally)
    #[cfg(feature = "ipc_channel")]
    pub use crate::communication::ipc::process_ipc_messages;
    #[cfg(feature = "ipc_channel")]
    pub use crate::communication::ipc::IpcManager;
    
    // HTTP IPC utilities
    pub use crate::communication::http_ipc::{
        ApiResponse, HttpIpcRouter, error_response, json_response,
        not_found, parse_json_body, success,
    };
    #[cfg(feature = "ipc_channel")]
    pub use crate::communication::http_ipc::{
        send_http_response, subscribe_http_requests,
    };
    
    // HTTP TCP utilities
    pub use crate::communication::http_tcp::{
        ApiResponse as HttpTcpApiResponse, HttpTcpClient, HttpTcpRequest, 
        HttpTcpResponse, HttpTcpRouter, serve as serve_http_tcp,
    };
    
    // Services
    pub use crate::services::registration::{
        Capabilities, Endpoint, HealthStatus, ModuleInfo, RegisteredModule,
        RegistrationError, advertise_capabilities, heartbeat, register_module,
        start_heartbeat_loop, unregister_module,
    };
    pub use crate::services::announce::{AnnounceError, send_announce};
    pub use crate::services::server::{serve_module, ServeOptions, serve_module_full, serve_module_with_lifecycle};
    
    // Security
    pub use crate::security::handshake::{InitError, read_init};
    pub use crate::security::secrets::{
        get_module_secret_client, get_secret, get_secrets, 
        subscribe_secret_rotations,
    };
    pub use crate::security::secrets::typed_secret::{Secret, TypedSecretError, get_typed_secret};
    pub use crate::security::secret_client::{SecretClient, SecretError, RequestMode};
    
    // Feature-gated APIs
    #[cfg(feature = "database")]
    pub use crate::data::database::{
        DatabaseConfig, DatabaseConnection, DatabaseError, DatabaseResult,
        DatabaseRow, DatabaseTransaction, DatabaseType, DatabaseValue,
        create_database_connection,
    };
    
    #[cfg(feature = "cache")]
    pub use crate::data::cache::{
        CacheConfig, CacheError, CacheResult, CacheService, CacheStats,
        CacheType, create_cache_service,
    };
    
    #[cfg(feature = "jwt_auth")]
    pub use crate::security::jwt_auth::{JwtAuthLayer, RouterJwtExt};

    // Core aliases re-exported at crate root
    pub use crate::{AnnouncedEndpoint, ModuleAnnounce, OrchestratorInit};
    
    // Export the module macro in prelude too
    #[cfg(feature = "proc_macros")]
    pub use crate::module;
    
    // Compatibility types
    pub use crate::{ChannelPreferences, SecurityLevel};
}

// Compatibility types for modules
#[derive(Debug, Clone)]
pub struct ChannelPreferences {
    pub use_tcp: bool,
    pub use_ipc: bool,
    pub prefer_ipc_for_local: bool,
    pub prefer_tcp_for_remote: bool,
}

#[derive(Debug, Clone)]
pub enum SecurityLevel {
    Low,
    Medium,
    High,
}
