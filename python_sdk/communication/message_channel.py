"""
Message channel abstraction for PyWatt Python SDK.

This module provides the core MessageChannel interface and related types
for interchangeable communication channels (TCP, Unix Domain Sockets, etc.).
"""

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass

from .message import EncodedMessage


class ConnectionState(Enum):
    """Current state of a connection."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    FAILED = "failed"


class ChannelType(Enum):
    """Indicates which type of communication channel to use."""
    TCP = "tcp"
    IPC = "ipc"


@dataclass
class ChannelPreferences:
    """Preferences for channel selection and usage."""
    use_tcp: bool = True
    use_ipc: bool = True
    prefer_ipc_for_local: bool = True
    prefer_tcp_for_remote: bool = True
    enable_fallback: bool = True
    
    @classmethod
    def tcp_only(cls) -> 'ChannelPreferences':
        """Create preferences for TCP-only usage."""
        return cls(
            use_tcp=True,
            use_ipc=False,
            prefer_ipc_for_local=False,
            prefer_tcp_for_remote=True,
            enable_fallback=False
        )
    
    @classmethod
    def ipc_only(cls) -> 'ChannelPreferences':
        """Create preferences for IPC-only usage."""
        return cls(
            use_tcp=False,
            use_ipc=True,
            prefer_ipc_for_local=True,
            prefer_tcp_for_remote=False,
            enable_fallback=False
        )
    
    @classmethod
    def prefer_ipc(cls) -> 'ChannelPreferences':
        """Create preferences that prefer IPC but allow TCP fallback."""
        return cls(
            use_tcp=True,
            use_ipc=True,
            prefer_ipc_for_local=True,
            prefer_tcp_for_remote=False,
            enable_fallback=True
        )
    
    @classmethod
    def prefer_tcp(cls) -> 'ChannelPreferences':
        """Create preferences that prefer TCP but allow IPC fallback."""
        return cls(
            use_tcp=True,
            use_ipc=True,
            prefer_ipc_for_local=False,
            prefer_tcp_for_remote=True,
            enable_fallback=True
        )


@dataclass
class ChannelCapabilities:
    """Capabilities that a communication channel supports."""
    module_messaging: bool = True
    http_proxy: bool = True
    service_calls: bool = True
    file_transfer: bool = False
    streaming: bool = False
    batching: bool = False
    compression: bool = False
    max_message_size: Optional[int] = None
    
    @classmethod
    def tcp_standard(cls) -> 'ChannelCapabilities':
        """Standard capabilities for TCP channels."""
        return cls(
            module_messaging=True,
            http_proxy=True,
            service_calls=True,
            file_transfer=True,
            streaming=True,
            batching=True,
            compression=True,
            max_message_size=64 * 1024 * 1024  # 64MB
        )
    
    @classmethod
    def ipc_standard(cls) -> 'ChannelCapabilities':
        """Standard capabilities for IPC channels."""
        return cls(
            module_messaging=True,
            http_proxy=True,
            service_calls=True,
            file_transfer=True,
            streaming=True,
            batching=True,
            compression=True,
            max_message_size=128 * 1024 * 1024  # 128MB (higher for local communication)
        )
    
    @classmethod
    def high_performance(cls) -> 'ChannelCapabilities':
        """High-performance capabilities."""
        return cls(
            module_messaging=True,
            http_proxy=True,
            service_calls=True,
            file_transfer=True,
            streaming=True,
            batching=True,
            compression=True,
            max_message_size=1024 * 1024 * 1024  # 1GB
        )


class MessageChannel(ABC):
    """
    A trait for channels that can send and receive messages.
    
    This trait allows for interchangeable use of different communication
    channels (TCP, Unix Domain Sockets, etc.) with the same interface.
    """
    
    @abstractmethod
    async def send(self, message: EncodedMessage) -> None:
        """Send a message over the channel."""
        pass
    
    @abstractmethod
    async def receive(self) -> EncodedMessage:
        """Receive a message from the channel."""
        pass
    
    @abstractmethod
    async def state(self) -> ConnectionState:
        """Get the current connection state."""
        pass
    
    @abstractmethod
    async def connect(self) -> None:
        """Connect or reconnect the channel."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect the channel."""
        pass
    
    @abstractmethod
    def get_channel_type(self) -> ChannelType:
        """Get the type of this channel."""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> ChannelCapabilities:
        """Get the capabilities of this channel."""
        pass


class NetworkError(Exception):
    """Base class for network-related errors."""
    pass


class ConnectionError(NetworkError):
    """Connection-related error."""
    pass


class ConnectionTimeout(NetworkError):
    """Connection timeout error."""
    def __init__(self, timeout_duration: float):
        self.timeout_duration = timeout_duration
        super().__init__(f"Connection timeout after {timeout_duration}s")


class ConnectionClosed(NetworkError):
    """Connection closed error."""
    pass


class ConnectionFailed(NetworkError):
    """Connection failed error."""
    pass


class ReconnectionFailed(NetworkError):
    """Reconnection failed error."""
    def __init__(self, attempts: int, reason: str):
        self.attempts = attempts
        self.reason = reason
        super().__init__(f"Reconnection failed after {attempts} attempts: {reason}")


class InvalidConfig(NetworkError):
    """Invalid configuration error."""
    pass


class ChannelError(NetworkError):
    """Channel-specific error."""
    pass 