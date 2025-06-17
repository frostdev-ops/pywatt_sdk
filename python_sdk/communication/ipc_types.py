"""IPC message types for PyWatt SDK.

This module provides Pydantic models for all IPC message types used for
communication between modules and the orchestrator, mirroring the Rust SDK
ipc_types implementation.
"""

import ipaddress
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import uuid

from pydantic import BaseModel, Field, validator, RootModel


class SecurityLevel(str, Enum):
    """Security level for communication channels."""
    NONE = "None"
    TOKEN = "Token"
    MTLS = "Mtls"


class ServiceType(str, Enum):
    """Type of service that can be provided by modules."""
    DATABASE = "Database"
    CACHE = "Cache"
    JWT = "Jwt"
    
    @classmethod
    def custom(cls, name: str) -> str:
        """Create a custom service type."""
        return f"Custom({name})"


class ListenAddress(RootModel[Union[str, Dict[str, str]]]):
    """Address to listen on, either TCP or Unix domain socket.
    
    This matches Rust's untagged enum serialization:
    - TCP addresses serialize as strings like "127.0.0.1:8080"
    - Unix addresses serialize as objects like {"Unix": "/path/to/socket"}
    """
    
    @classmethod
    def tcp(cls, host: str, port: int) -> "ListenAddress":
        """Create a TCP listen address."""
        return cls(root=f"{host}:{port}")
    
    @classmethod
    def unix(cls, path: str) -> "ListenAddress":
        """Create a Unix socket listen address."""
        return cls(root={"Unix": path})
    
    def __str__(self) -> str:
        """String representation of the address."""
        if isinstance(self.root, str):
            return self.root
        else:
            return self.root.get("Unix", "")
    
    def is_tcp(self) -> bool:
        """Check if this is a TCP address."""
        return isinstance(self.root, str)
    
    def is_unix(self) -> bool:
        """Check if this is a Unix address."""
        return isinstance(self.root, dict) and "Unix" in self.root


class TcpChannelConfig(BaseModel):
    """Configuration for a TCP channel."""
    
    host: str = Field(..., description="TCP host address")
    port: int = Field(..., description="TCP port number")
    tls_enabled: bool = Field(default=False, description="Whether TLS is enabled")
    required: bool = Field(default=False, description="Whether this channel is required")
    
    @validator('port')
    def validate_port(cls, v):
        """Validate port number."""
        if not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v
    
    def with_tls(self, enabled: bool) -> "TcpChannelConfig":
        """Set TLS enabled status."""
        self.tls_enabled = enabled
        return self
    
    def with_required(self, required: bool) -> "TcpChannelConfig":
        """Set required status."""
        self.required = required
        return self


class IpcChannelConfig(BaseModel):
    """Configuration for an IPC channel using Unix Domain Sockets."""
    
    socket_path: str = Field(..., description="Path to the Unix Domain Socket")
    required: bool = Field(default=False, description="Whether this channel is required")
    
    def with_required(self, required: bool) -> "IpcChannelConfig":
        """Set required status."""
        self.required = required
        return self


class InitBlob(BaseModel):
    """Sent from Orchestrator -> Module on startup."""
    
    orchestrator_api: str = Field(..., description="Orchestrator API URL")
    module_id: str = Field(..., description="Module identifier")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    listen: ListenAddress = Field(..., description="Listen address assigned by orchestrator")
    
    # Independent communication channels
    tcp_channel: Optional[TcpChannelConfig] = Field(None, description="TCP channel configuration")
    ipc_channel: Optional[IpcChannelConfig] = Field(None, description="IPC channel configuration")
    
    # Security configuration
    auth_token: Optional[str] = Field(None, description="Authentication token")
    security_level: SecurityLevel = Field(default=SecurityLevel.NONE, description="Security level")
    
    # Additional fields for Wattson compatibility
    debug_mode: bool = Field(default=False, description="Whether debug mode is enabled")
    log_level: str = Field(default="info", description="Log level for the module")
    
    def has_channels(self) -> bool:
        """Check if the module has any channel configurations."""
        return self.tcp_channel is not None or self.ipc_channel is not None
    
    def has_required_channels(self) -> bool:
        """Check if the module has required channels."""
        return (
            (self.tcp_channel is not None and self.tcp_channel.required) or
            (self.ipc_channel is not None and self.ipc_channel.required)
        )


class EndpointAnnounce(BaseModel):
    """Information about a single HTTP/WebSocket endpoint provided by a module."""
    
    path: str = Field(..., description="Endpoint path")
    methods: List[str] = Field(..., description="Supported HTTP methods")
    auth: Optional[str] = Field(None, description="Authentication requirement")


class AnnounceBlob(BaseModel):
    """Sent from Module -> Orchestrator once the module has bound its listener."""
    
    listen: str = Field(..., description="The socket address the server actually bound to")
    endpoints: List[EndpointAnnounce] = Field(..., description="All endpoints exposed by the module")


class GetSecretRequest(BaseModel):
    """Sent from Module -> Orchestrator to fetch a secret."""
    
    name: str = Field(..., description="Name of the secret")


class SecretValueResponse(BaseModel):
    """Sent from Orchestrator -> Module in response to GetSecret or proactively during rotation."""
    
    name: str = Field(..., description="Secret name")
    value: str = Field(..., description="Secret value")
    rotation_id: Optional[str] = Field(None, description="Rotation batch identifier")


class RotatedNotification(BaseModel):
    """Batched notification that a group of secrets have been rotated."""
    
    keys: List[str] = Field(..., description="List of rotated secret keys")
    rotation_id: str = Field(..., description="Rotation batch identifier")


class RotationAckRequest(BaseModel):
    """Sent from Module -> Orchestrator after processing a rotation batch."""
    
    rotation_id: str = Field(..., description="Rotation batch identifier")
    status: str = Field(..., description="Status: 'success' or 'error'")
    message: Optional[str] = Field(None, description="Optional human-readable context")


class RegisterServiceProviderRequest(BaseModel):
    """Request to register as a service provider."""
    
    service_type: str = Field(..., description="Type of service being provided")
    name: str = Field(..., description="Human-readable name for the service")
    version: Optional[str] = Field(None, description="Optional version of the service")
    address: str = Field(..., description="Network address where the service can be reached")
    metadata: Optional[Dict[str, str]] = Field(None, description="Optional metadata about the service")


class RegisterServiceProviderResponse(BaseModel):
    """Response to service provider registration."""
    
    success: bool = Field(..., description="Whether the registration was successful")
    provider_id: Optional[str] = Field(None, description="Unique provider ID if successful")
    error: Optional[str] = Field(None, description="Error message if unsuccessful")


class DiscoverServiceProvidersRequest(BaseModel):
    """Request to discover service providers."""
    
    service_type: str = Field(..., description="Type of service to discover")
    all_providers: Optional[bool] = Field(None, description="Whether to return all providers or just the first healthy one")


class ServiceProviderInfo(BaseModel):
    """Information about a discovered service provider."""
    
    provider_id: str = Field(..., description="Unique provider ID")
    module_id: str = Field(..., description="Module ID that provides this service")
    service_type: str = Field(..., description="Type of service provided")
    name: str = Field(..., description="Human-readable name for the service")
    version: Optional[str] = Field(None, description="Optional version of the service")
    address: str = Field(..., description="Network address where the service can be reached")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Metadata about the service")
    is_healthy: bool = Field(..., description="Whether the provider is currently healthy")


class DiscoverServiceProvidersResponse(BaseModel):
    """Response to service provider discovery."""
    
    success: bool = Field(..., description="Whether the discovery was successful")
    providers: List[ServiceProviderInfo] = Field(..., description="List of discovered service providers")
    error: Optional[str] = Field(None, description="Error message if unsuccessful")


class ServiceRequest(BaseModel):
    """Request a service connection from the orchestrator."""
    
    id: str = Field(..., description="Identifier for the service")
    service_type: str = Field(..., description="Type of service")
    config: Optional[Dict[str, Any]] = Field(None, description="Optional configuration override")


class ServiceResponse(BaseModel):
    """Response to a service request."""
    
    id: str = Field(..., description="ID from the request")
    service_type: str = Field(..., description="Type of service")
    success: bool = Field(..., description="Whether the request was successful")
    error: Optional[str] = Field(None, description="Error message if unsuccessful")
    connection_id: Optional[str] = Field(None, description="Unique ID for the connection")


class ServiceOperation(BaseModel):
    """Perform an operation on a service."""
    
    connection_id: str = Field(..., description="ID of the connection to use")
    service_type: str = Field(..., description="Type of service")
    operation: str = Field(..., description="Name of the operation")
    params: Dict[str, Any] = Field(..., description="Parameters for the operation")


class ServiceOperationResult(BaseModel):
    """Result of a service operation."""
    
    success: bool = Field(..., description="Whether the operation was successful")
    result: Optional[Dict[str, Any]] = Field(None, description="Result data if successful")
    error: Optional[str] = Field(None, description="Error message if unsuccessful")


class IpcHttpRequest(BaseModel):
    """HTTP request from orchestrator to module."""
    
    request_id: str = Field(..., description="Unique request identifier")
    method: str = Field(..., description="HTTP method")
    uri: str = Field(..., description="Request URI")
    headers: Dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    body: Optional[bytes] = Field(None, description="Request body")


class IpcHttpResponse(BaseModel):
    """HTTP response from module to orchestrator."""
    
    request_id: str = Field(..., description="Request identifier from the original request")
    status_code: int = Field(..., description="HTTP status code")
    headers: Dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    body: Optional[bytes] = Field(None, description="Response body")
    
    @validator('status_code')
    def validate_status_code(cls, v):
        """Validate HTTP status code."""
        if not (100 <= v <= 599):
            raise ValueError("Status code must be between 100 and 599")
        return v


class IpcPortNegotiation(BaseModel):
    """Port negotiation request from module to orchestrator."""
    
    request_id: str = Field(..., description="Unique ID for this port request")
    specific_port: Optional[int] = Field(None, description="Optional specific port that the module wants to use")
    
    @validator('specific_port')
    def validate_specific_port(cls, v):
        """Validate specific port number."""
        if v is not None and not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v


class IpcPortNegotiationResponse(BaseModel):
    """Port negotiation response from orchestrator to module."""
    
    request_id: str = Field(..., description="The request_id from the original request")
    success: bool = Field(..., description="Whether the port allocation was successful")
    port: int = Field(..., description="The allocated port number")
    error_message: Optional[str] = Field(None, description="Error message if port allocation failed")
    
    @validator('port')
    def validate_port(cls, v):
        """Validate port number."""
        if not (0 <= v <= 65535):  # 0 is allowed to indicate failure
            raise ValueError("Port must be between 0 and 65535")
        return v


class ModuleToOrchestrator(BaseModel):
    """Messages sent from a module to the orchestrator."""
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
    
    # Use discriminated union with 'op' field
    op: str = Field(..., description="Operation type")
    
    # Message data (only one should be set based on op)
    identify: Optional[str] = None  # Module ID for identification
    announce: Optional[AnnounceBlob] = None
    get_secret: Optional[GetSecretRequest] = None
    rotation_ack: Optional[RotationAckRequest] = None
    register_service_provider: Optional[RegisterServiceProviderRequest] = None
    discover_service_providers: Optional[DiscoverServiceProvidersRequest] = None
    service_request: Optional[ServiceRequest] = None
    service_operation: Optional[ServiceOperation] = None
    http_response: Optional[IpcHttpResponse] = None
    port_request: Optional[IpcPortNegotiation] = None
    
    # Inter-module routing
    route_to_module: Optional[Dict[str, Any]] = None  # Will be properly typed in Phase 2
    
    @classmethod
    def identify_msg(cls, module_id: str) -> "ModuleToOrchestrator":
        """Create an identify message."""
        return cls(op="identify", identify=module_id)
    
    @classmethod
    def announce_msg(cls, announce: AnnounceBlob) -> "ModuleToOrchestrator":
        """Create an announce message."""
        return cls(op="announce", announce=announce)
    
    @classmethod
    def get_secret_msg(cls, request: GetSecretRequest) -> "ModuleToOrchestrator":
        """Create a get secret message."""
        return cls(op="get_secret", get_secret=request)
    
    @classmethod
    def rotation_ack_msg(cls, ack: RotationAckRequest) -> "ModuleToOrchestrator":
        """Create a rotation ack message."""
        return cls(op="rotation_ack", rotation_ack=ack)
    
    @classmethod
    def http_response_msg(cls, response: IpcHttpResponse) -> "ModuleToOrchestrator":
        """Create an HTTP response message."""
        return cls(op="http_response", http_response=response)
    
    @classmethod
    def port_request_msg(cls, request: IpcPortNegotiation) -> "ModuleToOrchestrator":
        """Create a port request message."""
        return cls(op="port_request", port_request=request)
    
    @classmethod
    def heartbeat_ack_msg(cls) -> "ModuleToOrchestrator":
        """Create a heartbeat ack message."""
        return cls(op="heartbeat_ack")


class OrchestratorToModule(BaseModel):
    """Messages sent from the orchestrator to a module."""
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
    
    # Use discriminated union with 'op' field
    op: str = Field(..., description="Operation type")
    
    # Message data (only one should be set based on op)
    init: Optional[InitBlob] = None
    secret: Optional[SecretValueResponse] = None
    rotated: Optional[RotatedNotification] = None
    register_service_provider_response: Optional[RegisterServiceProviderResponse] = None
    discover_service_providers_response: Optional[DiscoverServiceProvidersResponse] = None
    service_response: Optional[ServiceResponse] = None
    service_operation_result: Optional[ServiceOperationResult] = None
    http_request: Optional[IpcHttpRequest] = None
    port_response: Optional[IpcPortNegotiationResponse] = None
    
    # Inter-module routing
    routed_module_message: Optional[Dict[str, Any]] = None  # Will be properly typed in Phase 2
    routed_module_response: Optional[Dict[str, Any]] = None  # Will be properly typed in Phase 2
    
    @classmethod
    def init_msg(cls, init: InitBlob) -> "OrchestratorToModule":
        """Create an init message."""
        return cls(op="init", init=init)
    
    @classmethod
    def secret_msg(cls, secret: SecretValueResponse) -> "OrchestratorToModule":
        """Create a secret message."""
        return cls(op="secret", secret=secret)
    
    @classmethod
    def rotated_msg(cls, rotated: RotatedNotification) -> "OrchestratorToModule":
        """Create a rotated message."""
        return cls(op="rotated", rotated=rotated)
    
    @classmethod
    def shutdown_msg(cls) -> "OrchestratorToModule":
        """Create a shutdown message."""
        return cls(op="shutdown")
    
    @classmethod
    def http_request_msg(cls, request: IpcHttpRequest) -> "OrchestratorToModule":
        """Create an HTTP request message."""
        return cls(op="http_request", http_request=request)
    
    @classmethod
    def port_response_msg(cls, response: IpcPortNegotiationResponse) -> "OrchestratorToModule":
        """Create a port response message."""
        return cls(op="port_response", port_response=response)
    
    @classmethod
    def heartbeat_msg(cls) -> "OrchestratorToModule":
        """Create a heartbeat message."""
        return cls(op="heartbeat")


# Type aliases for compatibility
Init = InitBlob
Announce = AnnounceBlob
Endpoint = EndpointAnnounce

# Legacy aliases for backward compatibility
IpcPortResponse = IpcPortNegotiationResponse 