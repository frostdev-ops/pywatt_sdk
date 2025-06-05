"""Communication layer for PyWatt SDK.

This module provides all communication-related functionality including:
- IPC communication (stdin/stdout)
- TCP channels
- HTTP over IPC and TCP
- Message handling and routing
- Port negotiation
"""

# Core communication
from .ipc_stdio import read_init, send_announce, process_ipc_messages
from .message import Message, MessageMetadata, EncodedMessage, EncodingFormat, MessageError
from .message_channel import MessageChannel, ChannelType, ConnectionState
from .tcp_channel import TcpChannel, ConnectionConfig, ReconnectPolicy
from .ipc_channel import IpcChannel, IpcConnectionConfig

# IPC types
from .ipc_types import (
    ServiceRequest, ServiceResponse, ServiceOperation,
    ServiceOperationResult, ServiceType, SecurityLevel,
    InitBlob, AnnounceBlob, EndpointAnnounce
)

# Re-export commonly used types
__all__ = [
    # Core communication
    "read_init", "send_announce", "process_ipc_messages",
    "Message", "MessageMetadata", "EncodedMessage", "EncodingFormat", "MessageError",
    "MessageChannel", "ChannelType", "ConnectionState",
    "TcpChannel", "ConnectionConfig", "ReconnectPolicy",
    "IpcChannel", "IpcConnectionConfig",
    
    # Service operation types
    "ServiceRequest", "ServiceResponse", "ServiceOperation",
    "ServiceOperationResult", "ServiceType", "SecurityLevel",
    "InitBlob", "AnnounceBlob", "EndpointAnnounce",
] 