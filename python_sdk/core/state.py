"""Application state management for PyWatt modules.

This module provides the AppState and AppConfig classes that manage shared
module state, configuration, and communication channels.
"""

import asyncio
import logging
from typing import Any, Dict, Generic, Optional, TypeVar, List, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
import uuid
from pydantic import BaseModel

# Import Phase 2 components - make all imports optional to avoid import errors
try:
    from communication.message_channel import MessageChannel, ChannelType, ChannelPreferences, ChannelCapabilities
except ImportError:
    MessageChannel = None
    ChannelType = None
    ChannelPreferences = None
    ChannelCapabilities = None

try:
    from communication.tcp_channel import TcpChannel, ConnectionConfig
except ImportError:
    TcpChannel = None
    ConnectionConfig = None

try:
    from communication.ipc_channel import IpcChannel, IpcConnectionConfig
except ImportError:
    IpcChannel = None
    IpcConnectionConfig = None

try:
    from communication.message import EncodingFormat
except ImportError:
    from enum import Enum
    class EncodingFormat(Enum):
        JSON = "json"
        MSGPACK = "msgpack"

# Optional imports for advanced features
try:
    from services.registration import ModuleRegistrationClient
except ImportError:
    ModuleRegistrationClient = None

try:
    from services.service_discovery import ServiceDiscoveryClient
except ImportError:
    ServiceDiscoveryClient = None

try:
    from data.database import DatabaseConnection, create_database_connection
except ImportError:
    DatabaseConnection = None
    create_database_connection = None

try:
    from data.cache import CacheService, create_cache_service
except ImportError:
    CacheService = None
    create_cache_service = None

try:
    from security.secret_client import SecretClient
except ImportError:
    SecretClient = None

try:
    from security.jwt_auth import JwtValidator, JwtConfig
except ImportError:
    JwtValidator = None
    JwtConfig = None

try:
    from internal.messaging import InternalMessagingClient, create_messaging_client
except ImportError:
    InternalMessagingClient = None
    create_messaging_client = None

logger = logging.getLogger(__name__)


T = TypeVar("T")  # User state type


class AppConfig(BaseModel):
    """Configuration for the application.
    
    This class manages all configuration settings for a PyWatt module,
    including message formats, timeouts, and feature flags.
    """
    
    # Message encoding configuration
    message_format_primary: Optional["EncodingFormat"] = EncodingFormat.JSON
    message_format_secondary: Optional["EncodingFormat"] = EncodingFormat.MSGPACK
    
    # IPC configuration
    ipc_timeout_ms: Optional[int] = 30000  # 30 seconds
    ipc_only: bool = False
    
    # Advanced features
    enable_advanced_features: bool = True  # Enable Phase 2 features by default
    
    # Communication configuration
    tcp_config: Optional[Dict[str, Any]] = None
    ipc_config: Optional[Dict[str, Any]] = None
    
    # Service configuration
    enable_service_discovery: bool = True
    enable_module_registration: bool = True
    
    # Database configuration
    database_config: Optional[Dict[str, Any]] = None
    
    # Cache configuration
    cache_config: Optional[Dict[str, Any]] = None
    
    # Security configuration
    jwt_config: Optional[Dict[str, Any]] = None
    secret_config: Optional[Dict[str, Any]] = None
    
    # Routing configuration (placeholder for future implementation)
    routing_config: Optional[Dict[str, Any]] = None
    failover_config: Optional[Dict[str, Any]] = None
    sla_config: Optional[Dict[str, Any]] = None
    alert_config: Optional[Dict[str, Any]] = None
    stream_config: Optional[Dict[str, Any]] = None
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True


# Type alias for module message handlers
ModuleMessageHandler = Callable[[str, uuid.UUID, Any], Awaitable[None]]


class AppState(Generic[T]):
    """Shared application state for a PyWatt module.
    
    Contains SDK-provided fields (module_id, orchestrator_api, secret_client)
    plus user-defined state of type T, and communication channels.
    """
    
    def __init__(
        self,
        module_id: str,
        orchestrator_api: str,
        secret_client: Optional["SecretClient"] = None,
        user_state: T = None,
        config: Optional[AppConfig] = None,
    ) -> None:
        """Initialize AppState with required components.
        
        Args:
            module_id: Unique identifier for the module
            orchestrator_api: URL of the orchestrator API
            secret_client: Client for accessing secrets
            user_state: User-provided application state
            config: Application configuration
        """
        self._module_id = module_id
        self._orchestrator_api = orchestrator_api
        self._secret_client = secret_client
        self.user_state = user_state
        self.config = config or AppConfig()
        
        # Communication channels
        self.tcp_channel: Optional["TcpChannel"] = None
        self.ipc_channel: Optional["IpcChannel"] = None
        
        # Service clients
        self.registration_client: Optional["ModuleRegistrationClient"] = None
        self.service_discovery_client: Optional["ServiceDiscoveryClient"] = None
        self.internal_messaging_client: Optional["InternalMessagingClient"] = None
        
        # Data layer services
        self.database: Optional["DatabaseConnection"] = None
        self.cache: Optional["CacheService"] = None
        
        # Security services
        self.secret_manager: Optional["SecretClient"] = None
        self.jwt_validator: Optional["JwtValidator"] = None
        
        # Module message handlers
        self.module_message_handlers: Dict[str, ModuleMessageHandler] = {}
        
        # Advanced features (placeholders for future implementation)
        self.channel_router: Optional[Any] = None
        self.failover_manager: Optional[Any] = None
        self.performance_monitoring: Optional[Any] = None
        self.priority_queue: Optional[Any] = None
        self.request_multiplexer: Optional[Any] = None
        
        # Initialize advanced features if enabled
        if self.config.enable_advanced_features:
            self._initialize_advanced_features()
    
    def _initialize_advanced_features(self) -> None:
        """Initialize advanced features if enabled."""
        try:
            # Initialize secret manager
            if self.secret_manager is None and self._secret_client is not None:
                self.secret_manager = self._secret_client
            
            # Initialize internal messaging client
            if self.internal_messaging_client is None and create_messaging_client is not None:
                self.internal_messaging_client = create_messaging_client(
                    module_id=self.module_id,
                    orchestrator_endpoint=self.orchestrator_api,
                )
            
            # Initialize service clients if enabled
            if (self.config.enable_module_registration and 
                self.registration_client is None and 
                ModuleRegistrationClient is not None):
                self.registration_client = ModuleRegistrationClient(
                    orchestrator_endpoint=self.orchestrator_api
                )
            
            if (self.config.enable_service_discovery and 
                self.service_discovery_client is None and 
                ServiceDiscoveryClient is not None):
                self.service_discovery_client = ServiceDiscoveryClient(
                    orchestrator_endpoint=self.orchestrator_api
                )
            
            # Initialize data layer services
            if (self.config.database_config and 
                self.database is None and 
                create_database_connection is not None):
                self.database = create_database_connection(self.config.database_config)
            
            if (self.config.cache_config and 
                self.cache is None and 
                create_cache_service is not None):
                self.cache = create_cache_service(self.config.cache_config)
            
            # Initialize JWT validator
            if (self.config.jwt_config and 
                self.jwt_validator is None and 
                JwtValidator is not None and 
                JwtConfig is not None):
                jwt_config = JwtConfig(**self.config.jwt_config)
                self.jwt_validator = JwtValidator(jwt_config)
            
            logger.info(f"Advanced features initialized for module {self.module_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize advanced features: {e}")
            # Don't fail module startup if advanced features fail to initialize
    
    @property
    def module_id(self) -> str:
        """Get the module's ID."""
        return self._module_id
    
    @property
    def orchestrator_api(self) -> str:
        """Get the orchestrator API URL."""
        return self._orchestrator_api
    
    @property
    def secret_client(self) -> Optional["SecretClient"]:
        """Get the configured SecretClient instance."""
        return self._secret_client or self.secret_manager
    
    def custom(self) -> T:
        """Get a reference to the custom user state."""
        return self.user_state
    
    async def send_message(
        self,
        target: str,
        message: Any,
        preferences: Optional["ChannelPreferences"] = None,
    ) -> None:
        """Send a message using the best available channel.
        
        Args:
            target: Target module or endpoint
            message: Message to send
            preferences: Channel preferences for routing
        """
        if self.internal_messaging_client is None:
            raise RuntimeError("Internal messaging client not initialized")
        
        # Parse target (format: "module_id:endpoint")
        if ":" in target:
            target_module_id, target_endpoint = target.split(":", 1)
        else:
            target_module_id = target
            target_endpoint = "default"
        
        await self.internal_messaging_client.send_notification(
            target_module_id=target_module_id,
            target_endpoint=target_endpoint,
            notification_payload=message,
        )
    
    async def send_request(
        self,
        target: str,
        request: Any,
        response_type: type = dict,
        preferences: Optional["ChannelPreferences"] = None,
    ) -> Any:
        """Send a request and wait for response.
        
        Args:
            target: Target module or endpoint
            request: Request to send
            response_type: Expected response type
            preferences: Channel preferences for routing
            
        Returns:
            Response from the target
        """
        if self.internal_messaging_client is None:
            raise RuntimeError("Internal messaging client not initialized")
        
        # Parse target (format: "module_id:endpoint")
        if ":" in target:
            target_module_id, target_endpoint = target.split(":", 1)
        else:
            target_module_id = target
            target_endpoint = "default"
        
        return await self.internal_messaging_client.send_request(
            target_module_id=target_module_id,
            target_endpoint=target_endpoint,
            request_payload=request,
            response_type=response_type,
        )
    
    def available_channels(self) -> List["ChannelType"]:
        """Get the available channel types.
        
        Returns:
            List of available channel types
        """
        channels = []
        
        if self.tcp_channel is not None:
            channels.append(ChannelType.TCP)
        
        if self.ipc_channel is not None:
            channels.append(ChannelType.IPC)
        
        return channels
    
    def channel_capabilities(self, channel_type: "ChannelType") -> Optional["ChannelCapabilities"]:
        """Get the capabilities of a specific channel.
        
        Args:
            channel_type: Type of channel to query
            
        Returns:
            Channel capabilities or None if channel not available
        """
        if channel_type == ChannelType.TCP and self.tcp_channel is not None:
            return ChannelCapabilities.tcp_standard()
        elif channel_type == ChannelType.IPC and self.ipc_channel is not None:
            return ChannelCapabilities.ipc_standard()
        else:
            return None
    
    def has_channel(self, channel_type: "ChannelType") -> bool:
        """Check if a specific channel type is available.
        
        Args:
            channel_type: Type of channel to check
            
        Returns:
            True if channel is available
        """
        if channel_type == ChannelType.TCP:
            return self.tcp_channel is not None
        elif channel_type == ChannelType.IPC:
            return self.ipc_channel is not None
        else:
            return False
    
    async def channel_health(self) -> Dict["ChannelType", bool]:
        """Get the health status of all channels.
        
        Returns:
            Dictionary mapping channel types to health status
        """
        health = {}
        
        if self.tcp_channel is not None:
            # Placeholder for actual health check
            health[ChannelType.TCP] = True
        
        if self.ipc_channel is not None:
            # Placeholder for actual health check
            health[ChannelType.IPC] = True
        
        return health
    
    def recommend_channel(
        self,
        target: str,
        preferences: Optional["ChannelPreferences"] = None,
    ) -> Optional["ChannelType"]:
        """Recommend the best channel for a target.
        
        Args:
            target: Target module or endpoint
            preferences: Channel preferences
            
        Returns:
            Recommended channel type or None if no channels available
        """
        prefs = preferences or ChannelPreferences()
        available = self.available_channels()
        
        if not available:
            return None
        
        # Simple recommendation logic for Phase 1
        # In Phase 2/3, this will be more sophisticated
        if ChannelType.IPC in available and prefs.prefer_ipc_for_local:
            return ChannelType.IPC
        elif ChannelType.TCP in available:
            return ChannelType.TCP
        else:
            return available[0] if available else None
    
    async def register_module_message_handler(
        self,
        source_module_id: str,
        handler: ModuleMessageHandler,
    ) -> None:
        """Register a handler for module-to-module messages.
        
        Args:
            source_module_id: ID of the source module
            handler: Handler function for messages from this module
        """
        self.module_message_handlers[source_module_id] = handler
    
    async def remove_module_message_handler(self, source_module_id: str) -> None:
        """Remove a registered handler for a specific source module.
        
        Args:
            source_module_id: ID of the source module
        """
        self.module_message_handlers.pop(source_module_id, None)
    
    # Phase 2 Enhanced Methods
    
    async def get_secret(self, key: str, use_cache: bool = True) -> Any:
        """Get a secret value using the secret manager.
        
        Args:
            key: Secret key to retrieve
            use_cache: Whether to use cached values
            
        Returns:
            Secret value
        """
        if self.secret_manager is None:
            raise RuntimeError("Secret manager not initialized")
        
        secret = await self.secret_manager.get_secret(key, use_cache)
        return secret.expose_secret()
    
    async def set_secret(self, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Set a secret value using the secret manager.
        
        Args:
            key: Secret key
            value: Secret value
            metadata: Optional metadata
        """
        if self.secret_manager is None:
            raise RuntimeError("Secret manager not initialized")
        
        await self.secret_manager.set_secret(key, value, metadata)
    
    async def register_service_provider(self, service_type: str, provider_info: Dict[str, Any]) -> None:
        """Register this module as a service provider.
        
        Args:
            service_type: Type of service being provided
            provider_info: Information about the service provider
        """
        if self.service_discovery_client is None:
            raise RuntimeError("Service discovery client not initialized")
        
        await self.service_discovery_client.register_provider(service_type, provider_info)
    
    async def discover_service_providers(self, service_type: str) -> List[Dict[str, Any]]:
        """Discover service providers for a given service type.
        
        Args:
            service_type: Type of service to discover
            
        Returns:
            List of service provider information
        """
        if self.service_discovery_client is None:
            raise RuntimeError("Service discovery client not initialized")
        
        return await self.service_discovery_client.discover_providers(service_type)
    
    async def execute_query(self, query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute a database query.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            
        Returns:
            Query results
        """
        if self.database is None:
            raise RuntimeError("Database connection not initialized")
        
        return await self.database.execute_query(query, params or [])
    
    async def cache_get(self, key: str) -> Optional[Any]:
        """Get a value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        if self.cache is None:
            raise RuntimeError("Cache service not initialized")
        
        return await self.cache.get(key)
    
    async def cache_set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        if self.cache is None:
            raise RuntimeError("Cache service not initialized")
        
        await self.cache.set(key, value, ttl)
    
    async def validate_jwt_token(self, token: str, claims_type: type = dict) -> Any:
        """Validate a JWT token.
        
        Args:
            token: JWT token to validate
            claims_type: Expected claims type
            
        Returns:
            Validated claims
        """
        if self.jwt_validator is None:
            raise RuntimeError("JWT validator not initialized")
        
        return await self.jwt_validator.validate_token(token, claims_type)
    
    async def close(self) -> None:
        """Close all resources and cleanup."""
        try:
            # Close communication channels
            if self.tcp_channel:
                await self.tcp_channel.close()
            
            if self.ipc_channel:
                await self.ipc_channel.close()
            
            # Close service clients
            if self.internal_messaging_client:
                await self.internal_messaging_client.close()
            
            # Close data layer services
            if self.database:
                await self.database.close()
            
            if self.cache:
                await self.cache.close()
            
            # Close secret manager
            if self.secret_manager:
                self.secret_manager.close()
            
            logger.info(f"AppState for module {self.module_id} closed successfully")
            
        except Exception as e:
            logger.error(f"Error closing AppState: {e}")
    
    def __repr__(self) -> str:
        """String representation of AppState."""
        return (
            f"AppState(module_id='{self.module_id}', "
            f"orchestrator_api='{self.orchestrator_api}', "
            f"channels={self.available_channels()}, "
            f"user_state={type(self.user_state).__name__})"
        ) 