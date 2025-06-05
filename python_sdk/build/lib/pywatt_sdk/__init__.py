"""PyWatt SDK for Python.

This is the main entry point for the PyWatt SDK, providing all the necessary
components for building PyWatt modules in Python.

Phase 3 Features:
- Advanced communication with intelligent routing and failover
- Streaming support for large data transfers
- Performance monitoring and SLA tracking
- CLI scaffolder for project generation
- Production-ready optimizations
"""

# Core components
from .core import (
    PyWattSDKError,
    BootstrapError,
    HandshakeError,
    SecretError,
    AnnouncementError,
    ConfigError,
    NetworkError,
    Result,
    init_module,
    safe_log,
    AppState,
    AppConfig,
    Config,
)

# Communication components (Phase 1)
from .communication import (
    InitBlob,
    AnnounceBlob,
    EndpointAnnounce,
    read_init,
    send_announce,
    process_ipc_messages,
)

# Phase 2 Communication components
try:
    from .communication import (
        MessageChannel,
        TcpChannel,
        IpcChannel,
        Message,
        EncodedMessage,
        EncodingFormat,
        ChannelType,
        ChannelPreferences,
        ChannelCapabilities,
        ConnectionConfig,
        IpcConnectionConfig,
    )
    _PHASE2_COMMUNICATION = True
except ImportError:
    _PHASE2_COMMUNICATION = False

# Phase 3 Advanced Communication components
try:
    from .communication import (
        # Routing
        ChannelRouter,
        RoutingMatrix,
        RoutingDecision,
        RoutingConfig,
        MessageCharacteristics,
        MessagePriority,
        MessageType,
        TargetLocation,
        extract_message_characteristics,
        
        # Failover
        FailoverManager,
        FailoverConfig,
        CircuitBreaker,
        CircuitBreakerConfig,
        CircuitBreakerState,
        RetryMechanism,
        RetryConfig,
        MessageBatcher,
        BatchConfig,
        ConnectionPool,
        MessageCompressor,
        PerformanceConfig,
        
        # Streaming
        StreamSender,
        StreamReceiver,
        StreamConfig,
        StreamMetadata,
        StreamPriority,
        PubSubMessage,
        Subscription,
        PriorityMessageQueue,
        RequestMultiplexer,
        
        # Metrics
        PerformanceMonitoringSystem,
        ChannelPerformanceTracker,
        ChannelMetrics,
        SlaConfig,
        SlaStatus,
        AlertConfig,
        PerformanceAlert,
        AlertType,
        AlertSeverity,
        PerformanceComparisonReport,
    )
    _PHASE3_COMMUNICATION = True
except ImportError:
    _PHASE3_COMMUNICATION = False

# Phase 2 Services
try:
    from .services import (
        # ModuleRegistrationClient,  # Not implemented yet
        ModuleInfo,
        Endpoint,
        Capabilities,
        HealthStatus,
        ServiceDiscoveryClient,
        ServiceType,
        ServiceProviderInfo,
    )
    _PHASE2_SERVICES = True
except ImportError:
    _PHASE2_SERVICES = False

# Phase 2 Data layer
try:
    from .data import (
        DatabaseConnection,
        DatabaseTransaction,
        DatabaseRow,
        DatabaseType,
        DatabaseConfig,
        create_database_connection,
        CacheService,
        CacheType,
        CacheConfig,
        create_cache_service,
    )
    _PHASE2_DATA = True
except ImportError:
    _PHASE2_DATA = False

# Security components (Phase 1)
from .security import (
    SecretClient,
    RequestMode,
    get_module_secret_client,
    get_secret,
    get_secrets,
    subscribe_secret_rotations,
    Secret,
    get_typed_secret,
    get_string_secret,
    get_bool_secret,
    get_int_secret,
    get_float_secret,
)

# Phase 2 Security components
try:
    from .security import (
        JwtAuthMiddleware,
        JwtConfig,
        JwtClaims,
        JwtError,
        create_jwt_middleware,
        validate_jwt_token,
        extract_jwt_claims,
        SecretManager,
        SecretConfig,
        create_secret_manager,
    )
    _PHASE2_SECURITY = True
except ImportError:
    _PHASE2_SECURITY = False

# Phase 2 Internal messaging
try:
    from .internal import (
        InternalMessagingClient,
        InternalMessagingError,
        create_messaging_client,
    )
    _PHASE2_INTERNAL = True
except ImportError:
    _PHASE2_INTERNAL = False

# Module decorator and utilities
from .module import pywatt_module, AnnouncedEndpoint

# Build information (Phase 2)
try:
    from .build import (
        get_build_info,
        get_build_info_dict,
        get_version_info,
        BuildInfo,
        GIT_HASH,
        BUILD_TIME_UTC,
        PYTHON_VERSION,
    )
    _BUILD_INFO_AVAILABLE = True
except ImportError:
    _BUILD_INFO_AVAILABLE = False

# Router discovery (Phase 2)
try:
    from .services.router_discovery import (
        announce_from_router,
        discover_endpoints,
        discover_endpoints_advanced,
        DiscoveredEndpoint,
    )
    _ROUTER_DISCOVERY_AVAILABLE = True
except ImportError:
    _ROUTER_DISCOVERY_AVAILABLE = False

# Server functionality (Phase 3)
try:
    from .services.server import (
        ServeOptions,
        ServerManager,
        FastAPIServerManager,
        FlaskServerManager,
        get_server_manager,
        set_pre_allocated_port,
        get_pre_allocated_port,
        negotiate_port,
        serve_module,
        serve_with_options,
        serve_module_full,
        serve_module_with_lifecycle,
    )
    _SERVER_AVAILABLE = True
except ImportError:
    _SERVER_AVAILABLE = False

# Bootstrap functionality (Phase 3)
try:
    from .core.bootstrap import (
        bootstrap_module,
        bootstrap_module_legacy,
        BootstrapResult,
        AppStateExt,
    )
    _BOOTSTRAP_AVAILABLE = True
except ImportError:
    _BOOTSTRAP_AVAILABLE = False

# Version information
__version__ = "0.3.0"  # Updated for Phase 3
__author__ = "PyWatt Team"
__email__ = "team@pywatt.io"

# Build __all__ dynamically based on available features
__all__ = [
    # Core
    "PyWattSDKError",
    "BootstrapError",
    "HandshakeError", 
    "SecretError",
    "AnnouncementError",
    "ConfigError",
    "NetworkError",
    "Result",
    "init_module",
    "safe_log",
    "AppState",
    "AppConfig",
    "Config",
    
    # Communication (Phase 1)
    "InitBlob",
    "AnnounceBlob",
    "EndpointAnnounce",
    "read_init",
    "send_announce",
    "process_ipc_messages",
    
    # Security (Phase 1)
    "SecretClient",
    "RequestMode",
    "get_module_secret_client",
    "get_secret",
    "get_secrets",
    "subscribe_secret_rotations",
    "Secret",
    "get_typed_secret",
    "get_string_secret",
    "get_bool_secret",
    "get_int_secret",
    "get_float_secret",
    
    # Module decorator
    "pywatt_module",
    "AnnouncedEndpoint",
    
    # Version
    "__version__",
]

# Add Phase 2 exports if available
if _PHASE2_COMMUNICATION:
    __all__.extend([
        "MessageChannel",
        "TcpChannel",
        "IpcChannel",
        "Message",
        "EncodedMessage",
        "EncodingFormat",
        "ChannelType",
        "ChannelPreferences",
        "ChannelCapabilities",
        "ConnectionConfig",
        "IpcConnectionConfig",
    ])

if _PHASE2_SERVICES:
    __all__.extend([
        "ModuleInfo",
        "Endpoint",
        "Capabilities",
        "HealthStatus",
        "ServiceDiscoveryClient",
        "ServiceType",
        "ServiceProviderInfo",
    ])

if _PHASE2_DATA:
    __all__.extend([
        "DatabaseConnection",
        "DatabaseTransaction",
        "DatabaseRow",
        "DatabaseType",
        "DatabaseConfig",
        "create_database_connection",
        "CacheService",
        "CacheType",
        "CacheConfig",
        "create_cache_service",
    ])

if _PHASE2_SECURITY:
    __all__.extend([
        "JwtAuthMiddleware",
        "JwtConfig",
        "JwtClaims",
        "JwtError",
        "create_jwt_middleware",
        "validate_jwt_token",
        "extract_jwt_claims",
        "SecretManager",
        "SecretConfig",
        "create_secret_manager",
    ])

if _PHASE2_INTERNAL:
    __all__.extend([
        "InternalMessagingClient",
        "InternalMessagingError",
        "create_messaging_client",
    ])

# Add Phase 3 exports if available
if _PHASE3_COMMUNICATION:
    __all__.extend([
        # Routing
        "ChannelRouter",
        "RoutingMatrix",
        "RoutingDecision",
        "RoutingConfig",
        "MessageCharacteristics",
        "MessagePriority",
        "MessageType",
        "TargetLocation",
        "extract_message_characteristics",
        
        # Failover
        "FailoverManager",
        "FailoverConfig",
        "CircuitBreaker",
        "CircuitBreakerConfig",
        "CircuitBreakerState",
        "RetryMechanism",
        "RetryConfig",
        "MessageBatcher",
        "BatchConfig",
        "ConnectionPool",
        "MessageCompressor",
        "PerformanceConfig",
        
        # Streaming
        "StreamSender",
        "StreamReceiver",
        "StreamConfig",
        "StreamMetadata",
        "StreamPriority",
        "PubSubMessage",
        "Subscription",
        "PriorityMessageQueue",
        "RequestMultiplexer",
        
        # Metrics
        "PerformanceMonitoringSystem",
        "ChannelPerformanceTracker",
        "ChannelMetrics",
        "SlaConfig",
        "SlaStatus",
        "AlertConfig",
        "PerformanceAlert",
        "AlertType",
        "AlertSeverity",
        "PerformanceComparisonReport",
    ])

# Add build information exports if available
if _BUILD_INFO_AVAILABLE:
    __all__.extend([
        "get_build_info",
        "get_build_info_dict", 
        "get_version_info",
        "BuildInfo",
        "GIT_HASH",
        "BUILD_TIME_UTC",
        "PYTHON_VERSION",
    ])

# Add router discovery exports if available
if _ROUTER_DISCOVERY_AVAILABLE:
    __all__.extend([
        "announce_from_router",
        "discover_endpoints",
        "discover_endpoints_advanced",
        "DiscoveredEndpoint",
    ])

# Add server functionality exports if available
if _SERVER_AVAILABLE:
    __all__.extend([
        "ServeOptions",
        "ServerManager",
        "FastAPIServerManager",
        "FlaskServerManager",
        "get_server_manager",
        "set_pre_allocated_port",
        "get_pre_allocated_port",
        "negotiate_port",
        "serve_module",
        "serve_with_options",
        "serve_module_full",
        "serve_module_with_lifecycle",
    ])

# Add bootstrap functionality exports if available
if _BOOTSTRAP_AVAILABLE:
    __all__.extend([
        "bootstrap_module",
        "bootstrap_module_legacy",
        "BootstrapResult",
        "AppStateExt",
    ]) 