"""
Module registration and capability advertisement for PyWatt modules.

This module provides functionality for registering modules with the orchestrator,
sending heartbeats, and advertising capabilities over TCP connections.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Awaitable
from datetime import datetime

from ..communication import TcpChannel, ConnectionConfig, MessageError
from ..communication.message import Message, EncodedMessage


class HealthStatus(Enum):
    """Health status of a module."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ModuleInfo:
    """Information about a module for registration."""
    name: str
    version: str
    description: str
    id: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None
    
    @classmethod
    def new(cls, name: str, version: str, description: str) -> 'ModuleInfo':
        """Create a new module info."""
        return cls(name=name, version=version, description=description)
    
    def with_id(self, module_id: str) -> 'ModuleInfo':
        """Set a unique identifier for the module."""
        self.id = module_id
        return self
    
    def with_metadata(self, key: str, value: str) -> 'ModuleInfo':
        """Add a metadata entry to the module info."""
        if self.metadata is None:
            self.metadata = {}
        self.metadata[key] = value
        return self


@dataclass
class Endpoint:
    """Information about an HTTP endpoint provided by a module."""
    path: str
    methods: List[str]
    auth: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None
    
    @classmethod
    def new(cls, path: str, methods: List[str]) -> 'Endpoint':
        """Create a new endpoint."""
        return cls(path=path, methods=methods)
    
    def with_auth(self, auth: str) -> 'Endpoint':
        """Set authentication requirements for the endpoint."""
        self.auth = auth
        return self
    
    def with_metadata(self, key: str, value: str) -> 'Endpoint':
        """Add a metadata entry to the endpoint."""
        if self.metadata is None:
            self.metadata = {}
        self.metadata[key] = value
        return self


@dataclass
class Capabilities:
    """Capabilities advertised by a module."""
    endpoints: List[Endpoint] = field(default_factory=list)
    message_types: Optional[List[str]] = None
    additional_capabilities: Optional[Dict[str, Any]] = None
    
    @classmethod
    def new(cls) -> 'Capabilities':
        """Create a new empty capabilities object."""
        return cls()
    
    def with_http_endpoint(self, path: str, methods: List[str]) -> 'Capabilities':
        """Add an HTTP endpoint to the capabilities."""
        self.endpoints.append(Endpoint.new(path, methods))
        return self
    
    def with_message_type(self, message_type: str) -> 'Capabilities':
        """Add a message type to the capabilities."""
        if self.message_types is None:
            self.message_types = []
        self.message_types.append(message_type)
        return self
    
    def with_capability(self, key: str, value: Any) -> 'Capabilities':
        """Add an additional capability to the module."""
        if self.additional_capabilities is None:
            self.additional_capabilities = {}
        self.additional_capabilities[key] = value
        return self


@dataclass
class RegisteredModule:
    """A registered module with the orchestrator."""
    info: ModuleInfo
    id: str
    token: str
    orchestrator_host: str
    orchestrator_port: int
    env: Optional[Dict[str, str]] = None
    additional_data: Optional[Dict[str, Any]] = None


class RegistrationError(Exception):
    """Base class for registration-related errors."""
    pass


class NameTaken(RegistrationError):
    """The module name is already taken."""
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Module name '{name}' is already taken")


class ConnectionError(RegistrationError):
    """The connection to the orchestrator failed."""
    pass


class Rejected(RegistrationError):
    """The registration was rejected by the orchestrator."""
    pass


class AuthenticationFailed(RegistrationError):
    """Authentication failed."""
    pass


class SerializationError(RegistrationError):
    """An error occurred during serialization or deserialization."""
    pass


class ChannelError(RegistrationError):
    """An error occurred in the TCP channel."""
    pass


class Timeout(RegistrationError):
    """The registration timed out."""
    def __init__(self, duration: float):
        self.duration = duration
        super().__init__(f"Registration timed out after {duration}s")


# Message types for registration protocol
@dataclass
class RegistrationRequest:
    """Registration request message."""
    request_type: str = "registration"
    module_info: Optional[ModuleInfo] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_type": self.request_type,
            "module_info": {
                "name": self.module_info.name,
                "version": self.module_info.version,
                "description": self.module_info.description,
                "id": self.module_info.id,
                "metadata": self.module_info.metadata,
            } if self.module_info else None
        }


@dataclass
class RegistrationResponse:
    """Registration response message."""
    response_type: str
    success: bool
    error: Optional[str] = None
    module: Optional[RegisteredModule] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RegistrationResponse':
        """Create from dictionary."""
        module_data = data.get("module")
        module = None
        if module_data:
            info = ModuleInfo(
                name=module_data["info"]["name"],
                version=module_data["info"]["version"],
                description=module_data["info"]["description"],
                id=module_data["info"].get("id"),
                metadata=module_data["info"].get("metadata"),
            )
            module = RegisteredModule(
                info=info,
                id=module_data["id"],
                token=module_data["token"],
                orchestrator_host=module_data["orchestrator_host"],
                orchestrator_port=module_data["orchestrator_port"],
                env=module_data.get("env"),
                additional_data=module_data.get("additional_data"),
            )
        
        return cls(
            response_type=data["response_type"],
            success=data["success"],
            error=data.get("error"),
            module=module
        )


@dataclass
class HeartbeatRequest:
    """Heartbeat request message."""
    request_type: str = "heartbeat"
    module_id: Optional[str] = None
    token: Optional[str] = None
    status: HealthStatus = HealthStatus.HEALTHY
    details: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_type": self.request_type,
            "module_id": self.module_id,
            "token": self.token,
            "status": self.status.value,
            "details": self.details,
        }


@dataclass
class HeartbeatResponse:
    """Heartbeat response message."""
    response_type: str
    success: bool
    error: Optional[str] = None
    status: HealthStatus = HealthStatus.HEALTHY
    context: Optional[Dict[str, str]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HeartbeatResponse':
        """Create from dictionary."""
        return cls(
            response_type=data["response_type"],
            success=data["success"],
            error=data.get("error"),
            status=HealthStatus(data.get("status", "healthy")),
            context=data.get("context"),
        )


@dataclass
class CapabilitiesRequest:
    """Capabilities advertisement request message."""
    request_type: str = "capabilities"
    module_id: Optional[str] = None
    token: Optional[str] = None
    capabilities: Optional[Capabilities] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        caps_dict = None
        if self.capabilities:
            caps_dict = {
                "endpoints": [
                    {
                        "path": ep.path,
                        "methods": ep.methods,
                        "auth": ep.auth,
                        "metadata": ep.metadata,
                    } for ep in self.capabilities.endpoints
                ],
                "message_types": self.capabilities.message_types,
                "additional_capabilities": self.capabilities.additional_capabilities,
            }
        
        return {
            "request_type": self.request_type,
            "module_id": self.module_id,
            "token": self.token,
            "capabilities": caps_dict,
        }


@dataclass
class CapabilitiesResponse:
    """Capabilities advertisement response message."""
    response_type: str
    success: bool
    error: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CapabilitiesResponse':
        """Create from dictionary."""
        return cls(
            response_type=data["response_type"],
            success=data["success"],
            error=data.get("error"),
        )


# Global registry for active TCP channel to orchestrator
_orchestrator_channel: Optional[TcpChannel] = None


async def register_module(config: ConnectionConfig, info: ModuleInfo) -> RegisteredModule:
    """Register a module with the orchestrator."""
    global _orchestrator_channel
    
    try:
        # Connect to orchestrator
        _orchestrator_channel = await TcpChannel.connect(config)
        
        # Send registration request
        request = RegistrationRequest(module_info=info)
        message = Message.new(request.to_dict())
        encoded = message.encode()
        
        await _orchestrator_channel.send(encoded)
        
        # Wait for response
        response_encoded = await _orchestrator_channel.receive_with_timeout(30.0)
        response_message = response_encoded.decode()
        response_data = response_message.content
        
        response = RegistrationResponse.from_dict(response_data)
        
        if not response.success:
            error_msg = response.error or "Unknown registration error"
            if "name" in error_msg.lower() and "taken" in error_msg.lower():
                raise NameTaken(info.name)
            elif "rejected" in error_msg.lower():
                raise Rejected(error_msg)
            elif "auth" in error_msg.lower():
                raise AuthenticationFailed(error_msg)
            else:
                raise RegistrationError(error_msg)
        
        if not response.module:
            raise RegistrationError("Registration succeeded but no module data returned")
        
        return response.module
        
    except asyncio.TimeoutError:
        raise Timeout(30.0)
    except MessageError as e:
        raise ChannelError(f"Channel error: {e}")
    except Exception as e:
        if isinstance(e, RegistrationError):
            raise
        raise ConnectionError(f"Failed to connect to orchestrator: {e}")


async def unregister_module(registered_module: RegisteredModule) -> None:
    """Unregister a module from the orchestrator."""
    global _orchestrator_channel
    
    if not _orchestrator_channel:
        raise RegistrationError("No active connection to orchestrator")
    
    try:
        # Send unregistration request
        request = {
            "request_type": "unregistration",
            "module_id": registered_module.id,
            "token": registered_module.token,
        }
        message = Message.new(request)
        encoded = message.encode()
        
        await _orchestrator_channel.send(encoded)
        
        # Wait for response
        response_encoded = await _orchestrator_channel.receive_with_timeout(10.0)
        response_message = response_encoded.decode()
        response_data = response_message.content
        
        if not response_data.get("success", False):
            error_msg = response_data.get("error", "Unknown unregistration error")
            raise RegistrationError(error_msg)
        
    except asyncio.TimeoutError:
        raise Timeout(10.0)
    except MessageError as e:
        raise ChannelError(f"Channel error: {e}")
    finally:
        # Close the connection
        await _orchestrator_channel.disconnect()
        _orchestrator_channel = None


async def heartbeat(registered_module: RegisteredModule, status: HealthStatus, details: Optional[Dict[str, str]] = None) -> HealthStatus:
    """Send a heartbeat to the orchestrator."""
    global _orchestrator_channel
    
    if not _orchestrator_channel:
        raise RegistrationError("No active connection to orchestrator")
    
    try:
        # Send heartbeat request
        request = HeartbeatRequest(
            module_id=registered_module.id,
            token=registered_module.token,
            status=status,
            details=details
        )
        message = Message.new(request.to_dict())
        encoded = message.encode()
        
        await _orchestrator_channel.send(encoded)
        
        # Wait for response
        response_encoded = await _orchestrator_channel.receive_with_timeout(10.0)
        response_message = response_encoded.decode()
        response_data = response_message.content
        
        response = HeartbeatResponse.from_dict(response_data)
        
        if not response.success:
            error_msg = response.error or "Unknown heartbeat error"
            raise RegistrationError(error_msg)
        
        return response.status
        
    except asyncio.TimeoutError:
        raise Timeout(10.0)
    except MessageError as e:
        raise ChannelError(f"Channel error: {e}")


async def advertise_capabilities(registered_module: RegisteredModule, capabilities: Capabilities) -> None:
    """Advertise capabilities to the orchestrator."""
    global _orchestrator_channel
    
    if not _orchestrator_channel:
        raise RegistrationError("No active connection to orchestrator")
    
    try:
        # Send capabilities request
        request = CapabilitiesRequest(
            module_id=registered_module.id,
            token=registered_module.token,
            capabilities=capabilities
        )
        message = Message.new(request.to_dict())
        encoded = message.encode()
        
        await _orchestrator_channel.send(encoded)
        
        # Wait for response
        response_encoded = await _orchestrator_channel.receive_with_timeout(10.0)
        response_message = response_encoded.decode()
        response_data = response_message.content
        
        response = CapabilitiesResponse.from_dict(response_data)
        
        if not response.success:
            error_msg = response.error or "Unknown capabilities error"
            raise RegistrationError(error_msg)
        
    except asyncio.TimeoutError:
        raise Timeout(10.0)
    except MessageError as e:
        raise ChannelError(f"Channel error: {e}")


async def start_heartbeat_loop(
    registered_module: RegisteredModule,
    interval: float,
    status_provider: Callable[[], Awaitable[HealthStatus]]
) -> asyncio.Task:
    """Start a periodic heartbeat loop."""
    
    async def heartbeat_loop():
        """The actual heartbeat loop."""
        while True:
            try:
                # Get current status
                current_status = await status_provider()
                
                # Send heartbeat
                await heartbeat(registered_module, current_status)
                
                # Wait for next interval
                await asyncio.sleep(interval)
                
            except Exception as e:
                # Log error but continue the loop
                print(f"Heartbeat error: {e}")
                await asyncio.sleep(interval)
    
    # Start the heartbeat loop as a background task
    return asyncio.create_task(heartbeat_loop()) 