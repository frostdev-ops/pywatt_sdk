"""
Service discovery client for PyWatt modules.

This module provides functionality for registering service providers and
discovering services through the orchestrator.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any

from ..communication import TcpChannel, ConnectionConfig, MessageError
from ..communication.message import Message, EncodedMessage


class ServiceType(Enum):
    """Types of services that can be registered."""
    HTTP = "http"
    GRPC = "grpc"
    WEBSOCKET = "websocket"
    CUSTOM = "custom"


@dataclass
class ServiceProviderInfo:
    """Information about a service provider."""
    id: str
    name: str
    service_type: ServiceType
    endpoint: str
    version: str
    metadata: Optional[Dict[str, str]] = None
    health_check_endpoint: Optional[str] = None
    
    @classmethod
    def new(cls, id: str, name: str, service_type: ServiceType, endpoint: str, version: str) -> 'ServiceProviderInfo':
        """Create a new service provider info."""
        return cls(
            id=id,
            name=name,
            service_type=service_type,
            endpoint=endpoint,
            version=version
        )
    
    def with_metadata(self, key: str, value: str) -> 'ServiceProviderInfo':
        """Add metadata to the service provider."""
        if self.metadata is None:
            self.metadata = {}
        self.metadata[key] = value
        return self
    
    def with_health_check(self, endpoint: str) -> 'ServiceProviderInfo':
        """Set the health check endpoint."""
        self.health_check_endpoint = endpoint
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "service_type": self.service_type.value,
            "endpoint": self.endpoint,
            "version": self.version,
            "metadata": self.metadata,
            "health_check_endpoint": self.health_check_endpoint,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServiceProviderInfo':
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            service_type=ServiceType(data["service_type"]),
            endpoint=data["endpoint"],
            version=data["version"],
            metadata=data.get("metadata"),
            health_check_endpoint=data.get("health_check_endpoint"),
        )


class ServiceDiscoveryError(Exception):
    """Base class for service discovery errors."""
    pass


class ConnectionError(ServiceDiscoveryError):
    """Connection to orchestrator failed."""
    pass


class RegistrationError(ServiceDiscoveryError):
    """Service registration failed."""
    pass


class DiscoveryError(ServiceDiscoveryError):
    """Service discovery failed."""
    pass


class Timeout(ServiceDiscoveryError):
    """Operation timed out."""
    def __init__(self, duration: float):
        self.duration = duration
        super().__init__(f"Operation timed out after {duration}s")


@dataclass
class RegisterServiceProviderRequest:
    """Request to register a service provider."""
    request_type: str = "register_service_provider"
    provider_info: Optional[ServiceProviderInfo] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_type": self.request_type,
            "provider_info": self.provider_info.to_dict() if self.provider_info else None,
        }


@dataclass
class RegisterServiceProviderResponse:
    """Response to service provider registration."""
    response_type: str
    success: bool
    error: Optional[str] = None
    provider_id: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RegisterServiceProviderResponse':
        """Create from dictionary."""
        return cls(
            response_type=data["response_type"],
            success=data["success"],
            error=data.get("error"),
            provider_id=data.get("provider_id"),
        )


@dataclass
class DiscoverServiceProvidersRequest:
    """Request to discover service providers."""
    request_type: str = "discover_service_providers"
    service_name: Optional[str] = None
    service_type: Optional[ServiceType] = None
    version: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_type": self.request_type,
            "service_name": self.service_name,
            "service_type": self.service_type.value if self.service_type else None,
            "version": self.version,
        }


@dataclass
class DiscoverServiceProvidersResponse:
    """Response to service provider discovery."""
    response_type: str
    success: bool
    error: Optional[str] = None
    providers: Optional[List[ServiceProviderInfo]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DiscoverServiceProvidersResponse':
        """Create from dictionary."""
        providers = None
        if data.get("providers"):
            providers = [ServiceProviderInfo.from_dict(p) for p in data["providers"]]
        
        return cls(
            response_type=data["response_type"],
            success=data["success"],
            error=data.get("error"),
            providers=providers,
        )


class ServiceProviderBuilder:
    """Builder for creating service provider information."""
    
    def __init__(self):
        self._id: Optional[str] = None
        self._name: Optional[str] = None
        self._service_type: Optional[ServiceType] = None
        self._endpoint: Optional[str] = None
        self._version: Optional[str] = None
        self._metadata: Dict[str, str] = {}
        self._health_check_endpoint: Optional[str] = None
    
    def with_id(self, id: str) -> 'ServiceProviderBuilder':
        """Set the service provider ID."""
        self._id = id
        return self
    
    def with_name(self, name: str) -> 'ServiceProviderBuilder':
        """Set the service name."""
        self._name = name
        return self
    
    def with_service_type(self, service_type: ServiceType) -> 'ServiceProviderBuilder':
        """Set the service type."""
        self._service_type = service_type
        return self
    
    def with_endpoint(self, endpoint: str) -> 'ServiceProviderBuilder':
        """Set the service endpoint."""
        self._endpoint = endpoint
        return self
    
    def with_version(self, version: str) -> 'ServiceProviderBuilder':
        """Set the service version."""
        self._version = version
        return self
    
    def with_metadata(self, key: str, value: str) -> 'ServiceProviderBuilder':
        """Add metadata."""
        self._metadata[key] = value
        return self
    
    def with_health_check(self, endpoint: str) -> 'ServiceProviderBuilder':
        """Set the health check endpoint."""
        self._health_check_endpoint = endpoint
        return self
    
    def build(self) -> ServiceProviderInfo:
        """Build the service provider info."""
        if not all([self._id, self._name, self._service_type, self._endpoint, self._version]):
            raise ValueError("Missing required fields for service provider")
        
        provider = ServiceProviderInfo(
            id=self._id,
            name=self._name,
            service_type=self._service_type,
            endpoint=self._endpoint,
            version=self._version,
            metadata=self._metadata if self._metadata else None,
            health_check_endpoint=self._health_check_endpoint,
        )
        return provider


class ServiceDiscoveryClient:
    """Client for service discovery operations."""
    
    def __init__(self, channel: TcpChannel):
        self.channel = channel
    
    @classmethod
    async def connect(cls, config: ConnectionConfig) -> 'ServiceDiscoveryClient':
        """Create and connect a new service discovery client."""
        channel = await TcpChannel.connect(config)
        return cls(channel)
    
    async def register_service_provider(self, provider_info: ServiceProviderInfo) -> str:
        """Register a service provider with the orchestrator."""
        try:
            # Send registration request
            request = RegisterServiceProviderRequest(provider_info=provider_info)
            message = Message.new(request.to_dict())
            encoded = message.encode()
            
            await self.channel.send(encoded)
            
            # Wait for response
            response_encoded = await self.channel.receive_with_timeout(10.0)
            response_message = response_encoded.decode()
            response_data = response_message.content
            
            response = RegisterServiceProviderResponse.from_dict(response_data)
            
            if not response.success:
                error_msg = response.error or "Unknown registration error"
                raise RegistrationError(error_msg)
            
            if not response.provider_id:
                raise RegistrationError("Registration succeeded but no provider ID returned")
            
            return response.provider_id
            
        except asyncio.TimeoutError:
            raise Timeout(10.0)
        except MessageError as e:
            raise ConnectionError(f"Channel error: {e}")
    
    async def discover_service_providers(
        self,
        service_name: Optional[str] = None,
        service_type: Optional[ServiceType] = None,
        version: Optional[str] = None
    ) -> List[ServiceProviderInfo]:
        """Discover service providers matching the criteria."""
        try:
            # Send discovery request
            request = DiscoverServiceProvidersRequest(
                service_name=service_name,
                service_type=service_type,
                version=version
            )
            message = Message.new(request.to_dict())
            encoded = message.encode()
            
            await self.channel.send(encoded)
            
            # Wait for response
            response_encoded = await self.channel.receive_with_timeout(10.0)
            response_message = response_encoded.decode()
            response_data = response_message.content
            
            response = DiscoverServiceProvidersResponse.from_dict(response_data)
            
            if not response.success:
                error_msg = response.error or "Unknown discovery error"
                raise DiscoveryError(error_msg)
            
            return response.providers or []
            
        except asyncio.TimeoutError:
            raise Timeout(10.0)
        except MessageError as e:
            raise ConnectionError(f"Channel error: {e}")
    
    async def discover_service_by_name(self, service_name: str) -> List[ServiceProviderInfo]:
        """Discover service providers by name."""
        return await self.discover_service_providers(service_name=service_name)
    
    async def discover_service_by_type(self, service_type: ServiceType) -> List[ServiceProviderInfo]:
        """Discover service providers by type."""
        return await self.discover_service_providers(service_type=service_type)
    
    async def discover_service_by_name_and_type(
        self,
        service_name: str,
        service_type: ServiceType
    ) -> List[ServiceProviderInfo]:
        """Discover service providers by name and type."""
        return await self.discover_service_providers(
            service_name=service_name,
            service_type=service_type
        )
    
    async def close(self) -> None:
        """Close the connection."""
        await self.channel.disconnect()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Aliases for backward compatibility
ServiceProvider = ServiceProviderInfo 