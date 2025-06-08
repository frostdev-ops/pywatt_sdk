use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::net::SocketAddr;
use std::path::PathBuf;
use uuid::Uuid;

// Add missing import for EncodedMessage
use crate::message::EncodedMessage;

/// Address to listen on, either TCP or Unix domain socket.
#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(untagged)]
pub enum ListenAddress {
    /// TCP socket address
    Tcp(SocketAddr),
    /// Unix domain socket path
    Unix(PathBuf),
}

/// Configuration for a TCP channel
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct TcpChannelConfig {
    /// TCP socket address to connect to
    pub address: SocketAddr,
    /// Whether TLS is enabled for this channel
    pub tls_enabled: bool,
    /// Whether this channel is required for the module
    pub required: bool,
}

impl TcpChannelConfig {
    /// Create a new TCP channel configuration
    pub fn new(address: SocketAddr) -> Self {
        Self {
            address,
            tls_enabled: false,
            required: false,
        }
    }

    /// Enable or disable TLS for this channel
    pub fn with_tls(mut self, tls_enabled: bool) -> Self {
        self.tls_enabled = tls_enabled;
        self
    }

    /// Set whether this channel is required
    pub fn with_required(mut self, required: bool) -> Self {
        self.required = required;
        self
    }
}

/// Configuration for an IPC channel using Unix Domain Sockets
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct IpcChannelConfig {
    /// Path to the Unix Domain Socket
    pub socket_path: PathBuf,
    /// Whether this channel is required for the module
    pub required: bool,
}

impl IpcChannelConfig {
    /// Create a new IPC channel configuration
    pub fn new<P: Into<PathBuf>>(socket_path: P) -> Self {
        Self {
            socket_path: socket_path.into(),
            required: false,
        }
    }

    /// Set whether this channel is required
    pub fn with_required(mut self, required: bool) -> Self {
        self.required = required;
        self
    }
}

/// Security level for communication channels
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub enum SecurityLevel {
    /// No authentication required
    None,
    /// Basic token authentication
    Token,
    /// Full mutual TLS authentication
    Mtls,
}

/// Sent from Orchestrator -> Module on startup.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct InitBlob {
    pub orchestrator_api: String,
    pub module_id: String,
    /// Any secrets the orchestrator already knows that the module will need immediately
    pub env: HashMap<String, String>,
    /// Listen address assigned by orchestrator (legacy support)
    pub listen: ListenAddress,
    
    // Independent communication channels
    /// TCP channel configuration (optional)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tcp_channel: Option<TcpChannelConfig>,
    /// IPC channel configuration (optional)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ipc_channel: Option<IpcChannelConfig>,
    
    // Security configuration
    /// Authentication token for secure channels
    #[serde(skip_serializing_if = "Option::is_none")]
    pub auth_token: Option<String>,
    /// Security level required for this module
    #[serde(default = "default_security_level")]
    pub security_level: SecurityLevel,
}

fn default_security_level() -> SecurityLevel {
    SecurityLevel::None
}

impl InitBlob {
    /// Create a new InitBlob with basic configuration
    pub fn new(orchestrator_api: String, module_id: String, listen: ListenAddress) -> Self {
        Self {
            orchestrator_api,
            module_id,
            env: HashMap::new(),
            listen,
            tcp_channel: None,
            ipc_channel: None,
            auth_token: None,
            security_level: SecurityLevel::None,
        }
    }

    /// Add environment variables
    pub fn with_env(mut self, env: HashMap<String, String>) -> Self {
        self.env = env;
        self
    }

    /// Add TCP channel configuration
    pub fn with_tcp_channel(mut self, tcp_config: TcpChannelConfig) -> Self {
        self.tcp_channel = Some(tcp_config);
        self
    }

    /// Add IPC channel configuration
    pub fn with_ipc_channel(mut self, ipc_config: IpcChannelConfig) -> Self {
        self.ipc_channel = Some(ipc_config);
        self
    }

    /// Set authentication token
    pub fn with_auth_token(mut self, token: String) -> Self {
        self.auth_token = Some(token);
        self
    }

    /// Set security level
    pub fn with_security_level(mut self, level: SecurityLevel) -> Self {
        self.security_level = level;
        self
    }

    /// Check if the module has any channel configurations
    pub fn has_channels(&self) -> bool {
        self.tcp_channel.is_some() || self.ipc_channel.is_some()
    }

    /// Check if the module has required channels
    pub fn has_required_channels(&self) -> bool {
        self.tcp_channel.as_ref().is_some_and(|c| c.required) ||
        self.ipc_channel.as_ref().is_some_and(|c| c.required)
    }
}

/// Information about a single HTTP/WebSocket endpoint provided by a module.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct EndpointAnnounce {
    pub path: String,
    pub methods: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub auth: Option<String>,
}

/// Sent from Module -> Orchestrator once the module has bound its listener.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct AnnounceBlob {
    /// The socket address the server actually bound to (e.g. "127.0.0.1:4102").
    pub listen: String,
    /// All endpoints exposed by the module.
    pub endpoints: Vec<EndpointAnnounce>,
}

/// Sent from Module -> Orchestrator to fetch a secret.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct GetSecretRequest {
    /// Name of the secret.
    pub name: String,
}

/// Sent from Orchestrator -> Module in response to `GetSecret` **or** proactively as part of a
/// rotation flow.  When used for rotation the `rotation_id` field will be `Some(..)` so the module
/// can acknowledge receipt.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct SecretValueResponse {
    pub name: String,
    pub value: String,
    /// Identifier used when this message is part of a rotation batch.  `None` means this was a
    /// regular on-demand secret fetch.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rotation_id: Option<String>,
}

/// Batched notification that a group of secrets have been rotated.  The module should invalidate
/// any cached values for the listed keys and call `get_secret` again.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct RotatedNotification {
    pub keys: Vec<String>,
    pub rotation_id: String,
}

/// Sent from Module -> Orchestrator after processing a rotation batch.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct RotationAckRequest {
    pub rotation_id: String,
    pub status: String, // typically "success" or "error"
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>, // optional human-readable context
}

/// Type of service that can be provided by modules.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum ServiceType {
    /// Database service
    Database,
    /// Cache service
    Cache,
    /// JWT authentication service
    Jwt,
    /// Custom service type defined by modules
    Custom(String),
}

impl ServiceType {
    /// Create a custom service type.
    pub fn custom(name: impl Into<String>) -> Self {
        Self::Custom(name.into())
    }
}

impl std::fmt::Display for ServiceType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ServiceType::Database => write!(f, "database"),
            ServiceType::Cache => write!(f, "cache"),
            ServiceType::Jwt => write!(f, "jwt"),
            ServiceType::Custom(name) => write!(f, "custom:{}", name),
        }
    }
}

/// Request to register as a service provider.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegisterServiceProviderRequest {
    /// Type of service being provided
    pub service_type: ServiceType,
    /// Human-readable name for the service
    pub name: String,
    /// Optional version of the service
    pub version: Option<String>,
    /// Network address where the service can be reached
    pub address: String,
    /// Optional metadata about the service
    pub metadata: Option<HashMap<String, String>>,
}

/// Response to service provider registration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegisterServiceProviderResponse {
    /// Whether the registration was successful
    pub success: bool,
    /// Unique provider ID if successful
    pub provider_id: Option<String>,
    /// Error message if unsuccessful
    pub error: Option<String>,
}

/// Request to discover service providers.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiscoverServiceProvidersRequest {
    /// Type of service to discover
    pub service_type: ServiceType,
    /// Whether to return all providers or just the first healthy one
    pub all_providers: Option<bool>,
}

/// Information about a discovered service provider.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceProviderInfo {
    /// Unique provider ID
    pub provider_id: String,
    /// Module ID that provides this service
    pub module_id: String,
    /// Type of service provided
    pub service_type: ServiceType,
    /// Human-readable name for the service
    pub name: String,
    /// Optional version of the service
    pub version: Option<String>,
    /// Network address where the service can be reached
    pub address: String,
    /// Metadata about the service
    pub metadata: HashMap<String, String>,
    /// Whether the provider is currently healthy
    pub is_healthy: bool,
}

/// Response to service provider discovery.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiscoverServiceProvidersResponse {
    /// Whether the discovery was successful
    pub success: bool,
    /// List of discovered service providers
    pub providers: Vec<ServiceProviderInfo>,
    /// Error message if unsuccessful
    pub error: Option<String>,
}

/// Request a service connection from the orchestrator
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceRequest {
    /// Identifier for the service
    pub id: String,
    /// Type of service
    pub service_type: ServiceType,
    /// Optional configuration override
    pub config: Option<serde_json::Value>,
}

/// Response to a service request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceResponse {
    /// ID from the request
    pub id: String,
    /// Type of service
    pub service_type: ServiceType,
    /// Whether the request was successful
    pub success: bool,
    /// Error message if unsuccessful
    pub error: Option<String>,
    /// Unique ID for the connection
    pub connection_id: Option<String>,
}

/// Perform an operation on a service
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceOperation {
    /// ID of the connection to use
    pub connection_id: String,
    /// Type of service
    pub service_type: ServiceType,
    /// Name of the operation
    pub operation: String,
    /// Parameters for the operation
    pub params: serde_json::Value,
}

/// Result of a service operation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceOperationResult {
    /// Whether the operation was successful
    pub success: bool,
    /// Result data if successful
    pub result: Option<serde_json::Value>,
    /// Error message if unsuccessful
    pub error: Option<String>,
}

/// HTTP request from orchestrator to module
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct IpcHttpRequest {
    pub request_id: String,
    pub method: String,
    pub uri: String,
    pub headers: HashMap<String, String>,
    pub body: Option<Vec<u8>>,
}

/// HTTP response from module to orchestrator
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct IpcHttpResponse {
    pub request_id: String,
    pub status_code: u16,
    pub headers: HashMap<String, String>,
    pub body: Option<Vec<u8>>,
}

/// Port negotiation request from module to orchestrator
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct IpcPortNegotiation {
    /// Unique ID for this port request
    pub request_id: String,
    /// Optional specific port that the module wants to use
    pub specific_port: Option<u16>,
}

/// Port negotiation response from orchestrator to module
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct IpcPortNegotiationResponse {
    /// The request_id from the original request
    pub request_id: String,
    /// Whether the port allocation was successful
    pub success: bool,
    /// The allocated port number
    pub port: u16,
    /// Error message if port allocation failed
    pub error_message: Option<String>,
}

/// Messages sent **from** a module **to** the orchestrator. These map 1-to-1 with what the legacy
/// `secret_client` library called `ClientRequest` but we keep that alias as well.
#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(tag = "op")]
pub enum ModuleToOrchestrator {
    #[serde(rename = "announce")]
    Announce(AnnounceBlob),
    #[serde(rename = "get_secret")]
    GetSecret(GetSecretRequest),
    #[serde(rename = "rotation_ack")]
    RotationAck(RotationAckRequest),
    #[serde(rename = "register_service_provider")]
    RegisterServiceProvider(RegisterServiceProviderRequest),
    #[serde(rename = "discover_service_providers")]
    DiscoverServiceProviders(DiscoverServiceProvidersRequest),
    #[serde(rename = "service_request")]
    ServiceRequest(ServiceRequest),
    #[serde(rename = "service_operation")]
    ServiceOperation(ServiceOperation),
    #[serde(rename = "http_response")]
    HttpResponse(IpcHttpResponse),
    #[serde(rename = "port_request")]
    PortRequest(IpcPortNegotiation),
    /// Message from a module intended for another module, to be routed by the orchestrator.
    #[serde(rename = "route_to_module")]
    RouteToModule {
        /// The unique identifier of the target module.
        target_module_id: String,
        /// A string identifying the target service or endpoint within the target module.
        target_endpoint: String,
        /// The unique ID for this request, used for correlating responses.
        request_id: Uuid,
        /// The actual payload, encoded using the module's preferred format.
        payload: EncodedMessage,
    },
    /// Acknowledge receipt of a heartbeat from the orchestrator
    #[serde(rename = "heartbeat_ack")]
    HeartbeatAck,
}

/// Messages sent **from** the orchestrator **to** a module.  This replaces the old
/// `ServerResponse` from `secret_client`.
#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(tag = "op")]
pub enum OrchestratorToModule {
    #[serde(rename = "init")]
    Init(InitBlob),
    #[serde(rename = "secret")]
    Secret(SecretValueResponse),
    #[serde(rename = "rotated")]
    Rotated(RotatedNotification),
    /// Instructs module to shutdown gracefully
    #[serde(rename = "shutdown")]
    Shutdown,
    #[serde(rename = "register_service_provider_response")]
    RegisterServiceProviderResponse(RegisterServiceProviderResponse),
    #[serde(rename = "discover_service_providers_response")]
    DiscoverServiceProvidersResponse(DiscoverServiceProvidersResponse),
    #[serde(rename = "service_response")]
    ServiceResponse(ServiceResponse),
    #[serde(rename = "service_operation_result")]
    ServiceOperationResult(ServiceOperationResult),
    #[serde(rename = "http_request")]
    HttpRequest(IpcHttpRequest),
    /// Response to a port negotiation request
    #[serde(rename = "port_response")]
    PortResponse(IpcPortNegotiationResponse),
    /// A message routed from another module via the orchestrator.
    #[serde(rename = "routed_module_message")]
    RoutedModuleMessage {
        /// The unique identifier of the module that sent the original message.
        source_module_id: String,
        /// The unique ID of the original request, to be echoed in the response by the handling module.
        original_request_id: Uuid,
        /// The actual payload, encoded using the sender module's preferred format.
        payload: EncodedMessage,
    },
    /// A response to a `RouteToModule` request, routed back by the orchestrator.
    #[serde(rename = "routed_module_response")]
    RoutedModuleResponse {
        /// The unique identifier of the module that is sending this response (the one that handled the request).
        source_module_id: String,
        /// The unique ID of the original request this response corresponds to.
        request_id: Uuid,
        /// The actual payload of the response, encoded. This should ideally be a Result<ActualResponse, ApplicationError>.
        payload: EncodedMessage,
    },
    /// Heartbeat message to check module health
    #[serde(rename = "heartbeat")]
    Heartbeat,
}

// ----- Legacy aliases to ease incremental migration -----

// Concise aliases preferred by module code to avoid deep type names
pub type Init = InitBlob;
pub type Announce = AnnounceBlob;
pub type Endpoint = EndpointAnnounce;

pub use ModuleToOrchestrator as ClientRequest;
pub use OrchestratorToModule as ServerResponse;
 