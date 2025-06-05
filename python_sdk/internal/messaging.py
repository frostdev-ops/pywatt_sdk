"""
Internal Messaging System

This module provides inter-module communication capabilities through the orchestrator.
Modules can send messages to other modules and receive responses asynchronously.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, TypeVar, Generic, Callable, Awaitable, Type
from weakref import WeakValueDictionary

from ..core.error import PyWattSDKError
from ..communication.message import Message, EncodedMessage, EncodingFormat
from ..communication.message_channel import MessageChannel
from ..communication.tcp_channel import TcpChannel, ConnectionConfig

logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')

# Internal Messaging Error Classes
class InternalMessagingError(PyWattSDKError):
    """Base class for internal messaging errors."""
    pass

class InternalMessagingTimeoutError(InternalMessagingError):
    """Raised when a message request times out."""
    pass

class InternalMessagingNetworkError(InternalMessagingError):
    """Raised when network communication fails."""
    pass

class InternalMessagingSerializationError(InternalMessagingError):
    """Raised when message serialization/deserialization fails."""
    pass

class InternalMessagingTargetNotFoundError(InternalMessagingError):
    """Raised when the target module or endpoint is not found."""
    pass

class InternalMessagingApplicationError(InternalMessagingError):
    """Raised when the target module returns an application error."""
    pass

# Message Types for Orchestrator Communication
@dataclass
class RouteToModuleRequest:
    """Request to route a message to another module."""
    target_module_id: str
    target_endpoint: str
    request_id: str
    payload: EncodedMessage
    timeout_seconds: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": "route_to_module",
            "target_module_id": self.target_module_id,
            "target_endpoint": self.target_endpoint,
            "request_id": self.request_id,
            "payload": {
                "data": self.payload.data.hex(),
                "format": self.payload.format.value,
                "metadata": self.payload.metadata,
            },
            "timeout_seconds": self.timeout_seconds,
        }

@dataclass
class RouteToModuleResponse:
    """Response from routing a message to another module."""
    request_id: str
    success: bool
    payload: Optional[EncodedMessage] = None
    error: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RouteToModuleResponse':
        """Create from dictionary."""
        payload = None
        if data.get("payload"):
            payload_data = data["payload"]
            payload = EncodedMessage(
                data=bytes.fromhex(payload_data["data"]),
                format=EncodingFormat(payload_data["format"]),
                metadata=payload_data.get("metadata", {}),
            )
        
        return cls(
            request_id=data["request_id"],
            success=data["success"],
            payload=payload,
            error=data.get("error"),
        )

# Pending Request Tracking
@dataclass
class PendingRequest:
    """Tracks a pending request awaiting response."""
    request_id: str
    future: asyncio.Future
    created_at: datetime = field(default_factory=datetime.utcnow)
    timeout: Optional[timedelta] = None
    
    def is_expired(self) -> bool:
        """Check if the request has expired."""
        if self.timeout is None:
            return False
        return datetime.utcnow() - self.created_at > self.timeout

# Internal Messaging Client
class InternalMessagingClient:
    """Client for sending messages to other modules via the orchestrator."""
    
    def __init__(
        self,
        module_id: str,
        orchestrator_channel: Optional[MessageChannel] = None,
        default_timeout: timedelta = timedelta(seconds=30),
        default_encoding: EncodingFormat = EncodingFormat.JSON,
    ):
        self.module_id = module_id
        self.orchestrator_channel = orchestrator_channel
        self.default_timeout = default_timeout
        self.default_encoding = default_encoding
        
        # Track pending requests
        self._pending_requests: Dict[str, PendingRequest] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Start cleanup task
        self._start_cleanup_task()
    
    def _start_cleanup_task(self) -> None:
        """Start background task to clean up expired requests."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_requests())
    
    async def _cleanup_expired_requests(self) -> None:
        """Background task to clean up expired requests."""
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                expired_ids = []
                for request_id, pending in self._pending_requests.items():
                    if pending.is_expired():
                        expired_ids.append(request_id)
                        if not pending.future.done():
                            pending.future.set_exception(
                                InternalMessagingTimeoutError(f"Request {request_id} timed out")
                            )
                
                for request_id in expired_ids:
                    self._pending_requests.pop(request_id, None)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
    async def send_request(
        self,
        target_module_id: str,
        target_endpoint: str,
        request_payload: Any,
        response_type: Type[R] = dict,
        timeout: Optional[timedelta] = None,
        encoding: Optional[EncodingFormat] = None,
    ) -> R:
        """
        Send a request to another module and await its response.
        
        Args:
            target_module_id: The ID of the target module
            target_endpoint: The endpoint on the target module
            request_payload: The request data to send
            response_type: Expected type of the response
            timeout: Request timeout (uses default if None)
            encoding: Message encoding format (uses default if None)
            
        Returns:
            The deserialized response from the target module
            
        Raises:
            InternalMessagingError: If the request fails
        """
        if self.orchestrator_channel is None:
            raise InternalMessagingNetworkError("No orchestrator channel available")
        
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        
        # Use provided timeout or default
        request_timeout = timeout or self.default_timeout
        request_encoding = encoding or self.default_encoding
        
        try:
            # Serialize the request payload
            message = Message(data=request_payload)
            encoded_payload = message.encode(request_encoding)
            
            # Create route request
            route_request = RouteToModuleRequest(
                target_module_id=target_module_id,
                target_endpoint=target_endpoint,
                request_id=request_id,
                payload=encoded_payload,
                timeout_seconds=request_timeout.total_seconds(),
            )
            
            # Create future for response
            response_future = asyncio.Future()
            pending_request = PendingRequest(
                request_id=request_id,
                future=response_future,
                timeout=request_timeout,
            )
            
            # Track the pending request
            self._pending_requests[request_id] = pending_request
            
            # Send the route request to orchestrator
            route_message = Message(data=route_request.to_dict())
            encoded_route_message = route_message.encode(request_encoding)
            
            await self.orchestrator_channel.send(encoded_route_message)
            
            # Wait for response with timeout
            try:
                response_data = await asyncio.wait_for(
                    response_future,
                    timeout=request_timeout.total_seconds()
                )
                
                # Deserialize response
                if response_type == dict:
                    return response_data
                elif hasattr(response_type, 'from_dict'):
                    return response_type.from_dict(response_data)
                else:
                    # Try to construct the response type
                    return response_type(**response_data)
                    
            except asyncio.TimeoutError:
                raise InternalMessagingTimeoutError(
                    f"Request to {target_module_id}:{target_endpoint} timed out after {request_timeout}"
                )
            finally:
                # Clean up pending request
                self._pending_requests.pop(request_id, None)
                
        except Exception as e:
            # Clean up pending request on error
            self._pending_requests.pop(request_id, None)
            
            if isinstance(e, InternalMessagingError):
                raise
            elif isinstance(e, (ConnectionError, OSError)):
                raise InternalMessagingNetworkError(f"Network error: {e}")
            else:
                raise InternalMessagingSerializationError(f"Serialization error: {e}")
    
    async def send_notification(
        self,
        target_module_id: str,
        target_endpoint: str,
        notification_payload: Any,
        encoding: Optional[EncodingFormat] = None,
    ) -> None:
        """
        Send a one-way notification to another module (no response expected).
        
        Args:
            target_module_id: The ID of the target module
            target_endpoint: The endpoint on the target module
            notification_payload: The notification data to send
            encoding: Message encoding format (uses default if None)
            
        Raises:
            InternalMessagingError: If sending the notification fails
        """
        if self.orchestrator_channel is None:
            raise InternalMessagingNetworkError("No orchestrator channel available")
        
        request_encoding = encoding or self.default_encoding
        
        try:
            # Serialize the notification payload
            message = Message(data=notification_payload)
            encoded_payload = message.encode(request_encoding)
            
            # Create route request (no response expected)
            route_request = RouteToModuleRequest(
                target_module_id=target_module_id,
                target_endpoint=target_endpoint,
                request_id=str(uuid.uuid4()),  # Still need an ID for tracking
                payload=encoded_payload,
                timeout_seconds=None,  # No timeout for notifications
            )
            
            # Send the route request to orchestrator
            route_message = Message(data=route_request.to_dict())
            encoded_route_message = route_message.encode(request_encoding)
            
            await self.orchestrator_channel.send(encoded_route_message)
            
        except Exception as e:
            if isinstance(e, (ConnectionError, OSError)):
                raise InternalMessagingNetworkError(f"Network error: {e}")
            else:
                raise InternalMessagingSerializationError(f"Serialization error: {e}")
    
    def handle_response(self, response_data: Dict[str, Any]) -> None:
        """
        Handle a response from the orchestrator.
        
        This method should be called by the main message processing loop
        when a response is received from the orchestrator.
        """
        try:
            response = RouteToModuleResponse.from_dict(response_data)
            
            # Find the pending request
            pending_request = self._pending_requests.get(response.request_id)
            if pending_request is None:
                logger.warning(f"Received response for unknown request ID: {response.request_id}")
                return
            
            # Complete the future
            if not pending_request.future.done():
                if response.success and response.payload:
                    # Decode the response payload
                    try:
                        decoded_message = Message.decode(response.payload)
                        pending_request.future.set_result(decoded_message.data)
                    except Exception as e:
                        pending_request.future.set_exception(
                            InternalMessagingSerializationError(f"Failed to decode response: {e}")
                        )
                elif response.error:
                    # Handle error response
                    if "not found" in response.error.lower():
                        pending_request.future.set_exception(
                            InternalMessagingTargetNotFoundError(response.error)
                        )
                    else:
                        pending_request.future.set_exception(
                            InternalMessagingApplicationError(response.error)
                        )
                else:
                    pending_request.future.set_exception(
                        InternalMessagingError("Unknown response format")
                    )
            
            # Clean up
            self._pending_requests.pop(response.request_id, None)
            
        except Exception as e:
            logger.error(f"Error handling response: {e}")
    
    async def close(self) -> None:
        """Close the messaging client and cleanup resources."""
        # Cancel cleanup task
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all pending requests
        for pending in self._pending_requests.values():
            if not pending.future.done():
                pending.future.set_exception(
                    InternalMessagingError("Messaging client is closing")
                )
        
        self._pending_requests.clear()
        
        # Close orchestrator channel
        if self.orchestrator_channel:
            await self.orchestrator_channel.close()

# Factory Functions
def create_messaging_client(
    module_id: str,
    orchestrator_endpoint: Optional[str] = None,
    default_timeout: timedelta = timedelta(seconds=30),
) -> InternalMessagingClient:
    """
    Create an InternalMessagingClient with appropriate configuration.
    
    Args:
        module_id: The ID of this module
        orchestrator_endpoint: Orchestrator endpoint (auto-detected if None)
        default_timeout: Default timeout for requests
        
    Returns:
        Configured InternalMessagingClient
    """
    # Determine orchestrator endpoint
    if orchestrator_endpoint is None:
        import os
        orchestrator_endpoint = os.getenv("PYWATT_ORCHESTRATOR_ENDPOINT", "127.0.0.1:9900")
    
    # Create orchestrator channel
    orchestrator_channel = None
    if orchestrator_endpoint:
        try:
            # Parse endpoint
            if ":" in orchestrator_endpoint:
                host, port_str = orchestrator_endpoint.rsplit(":", 1)
                port = int(port_str)
            else:
                host = orchestrator_endpoint
                port = 9900
            
            # Create TCP channel to orchestrator
            config = ConnectionConfig(host=host, port=port)
            orchestrator_channel = TcpChannel(config)
            
        except Exception as e:
            logger.warning(f"Failed to create orchestrator channel: {e}")
    
    return InternalMessagingClient(
        module_id=module_id,
        orchestrator_channel=orchestrator_channel,
        default_timeout=default_timeout,
    )

# Utility Functions
async def send_module_request(
    target_module_id: str,
    target_endpoint: str,
    request_payload: Any,
    response_type: Type[R] = dict,
    timeout: Optional[timedelta] = None,
    module_id: Optional[str] = None,
) -> R:
    """
    Convenience function to send a request to another module.
    
    This creates a temporary messaging client for one-off requests.
    For multiple requests, it's more efficient to create and reuse a client.
    """
    if module_id is None:
        import os
        module_id = os.getenv("PYWATT_MODULE_ID", "unknown")
    
    client = create_messaging_client(module_id)
    try:
        return await client.send_request(
            target_module_id=target_module_id,
            target_endpoint=target_endpoint,
            request_payload=request_payload,
            response_type=response_type,
            timeout=timeout,
        )
    finally:
        await client.close()

async def send_module_notification(
    target_module_id: str,
    target_endpoint: str,
    notification_payload: Any,
    module_id: Optional[str] = None,
) -> None:
    """
    Convenience function to send a notification to another module.
    
    This creates a temporary messaging client for one-off notifications.
    """
    if module_id is None:
        import os
        module_id = os.getenv("PYWATT_MODULE_ID", "unknown")
    
    client = create_messaging_client(module_id)
    try:
        await client.send_notification(
            target_module_id=target_module_id,
            target_endpoint=target_endpoint,
            notification_payload=notification_payload,
        )
    finally:
        await client.close() 