"""
IPC channel implementation for PyWatt modules.

This module provides a Unix Domain Socket-based channel for communication between modules
and the orchestrator, offering high-performance local communication.
"""

import asyncio
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from io import BytesIO

from .message_channel import (
    MessageChannel, ConnectionState, ChannelType, ChannelCapabilities,
    NetworkError, ConnectionError, ConnectionTimeout, ConnectionClosed,
    ConnectionFailed, ReconnectionFailed, InvalidConfig
)
from .message import EncodedMessage, MessageError
from .tcp_channel import ReconnectPolicy


@dataclass
class IpcConnectionConfig:
    """Configuration for an IPC connection using Unix Domain Sockets."""
    socket_path: Path = Path("/tmp/pywatt.sock")
    timeout: float = 5.0
    reconnect_policy: ReconnectPolicy = ReconnectPolicy.EXPONENTIAL_BACKOFF
    
    # Reconnection policy parameters
    fixed_delay: float = 1.0
    max_attempts: Optional[int] = None
    initial_delay: float = 0.1
    max_delay: float = 30.0
    multiplier: float = 2.0
    
    @classmethod
    def new(cls, socket_path: str) -> 'IpcConnectionConfig':
        """Create a new IPC connection configuration."""
        return cls(socket_path=Path(socket_path))
    
    def with_timeout(self, timeout: float) -> 'IpcConnectionConfig':
        """Set the timeout for connection attempts and operations."""
        self.timeout = timeout
        return self
    
    def with_reconnect_policy(self, policy: ReconnectPolicy) -> 'IpcConnectionConfig':
        """Set the reconnection policy."""
        self.reconnect_policy = policy
        return self
    
    def with_fixed_interval(self, delay: float, max_attempts: Optional[int] = None) -> 'IpcConnectionConfig':
        """Configure fixed interval reconnection."""
        self.reconnect_policy = ReconnectPolicy.FIXED_INTERVAL
        self.fixed_delay = delay
        self.max_attempts = max_attempts
        return self
    
    def with_exponential_backoff(self, initial_delay: float, max_delay: float, multiplier: float = 2.0) -> 'IpcConnectionConfig':
        """Configure exponential backoff reconnection."""
        self.reconnect_policy = ReconnectPolicy.EXPONENTIAL_BACKOFF
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        return self


class IpcChannel(MessageChannel):
    """A Unix Domain Socket-based message channel."""
    
    def __init__(self, config: IpcConnectionConfig):
        self.config = config
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._state = ConnectionState.DISCONNECTED
        self._connect_attempts = 0
        self._lock = asyncio.Lock()
    
    @classmethod
    async def connect(cls, config: IpcConnectionConfig) -> 'IpcChannel':
        """Create and connect a new IPC channel."""
        channel = cls(config)
        await channel.connect()
        return channel
    
    async def connect(self) -> None:
        """Connect or reconnect the channel."""
        async with self._lock:
            await self._connect_with_retry()
    
    async def _connect_with_retry(self) -> None:
        """Connect with retry according to the reconnection policy."""
        self._state = ConnectionState.CONNECTING
        self._connect_attempts = 0
        
        if self.config.reconnect_policy == ReconnectPolicy.NONE:
            try:
                await self._try_connect()
            except Exception:
                self._state = ConnectionState.FAILED
                raise
        elif self.config.reconnect_policy == ReconnectPolicy.FIXED_INTERVAL:
            await self._connect_fixed_interval()
        elif self.config.reconnect_policy == ReconnectPolicy.EXPONENTIAL_BACKOFF:
            await self._connect_exponential_backoff()
    
    async def _connect_fixed_interval(self) -> None:
        """Connect with fixed interval retry policy."""
        attempts = 0
        while True:
            if self.config.max_attempts and attempts >= self.config.max_attempts:
                self._state = ConnectionState.FAILED
                raise ReconnectionFailed(attempts, "Maximum reconnection attempts reached")
            
            try:
                await self._try_connect()
                return
            except Exception as e:
                attempts += 1
                self._connect_attempts = attempts
                
                if self.config.max_attempts and attempts >= self.config.max_attempts:
                    self._state = ConnectionState.FAILED
                    raise ReconnectionFailed(attempts, str(e))
                
                await asyncio.sleep(self.config.fixed_delay)
    
    async def _connect_exponential_backoff(self) -> None:
        """Connect with exponential backoff retry policy."""
        attempts = 0
        current_delay = self.config.initial_delay
        
        while True:
            try:
                await self._try_connect()
                return
            except Exception as e:
                attempts += 1
                self._connect_attempts = attempts
                
                await asyncio.sleep(current_delay)
                
                # Calculate next delay with exponential backoff
                next_delay = current_delay * self.config.multiplier
                current_delay = min(next_delay, self.config.max_delay)
    
    async def _try_connect(self) -> None:
        """Try to connect once with timeout."""
        if self._state == ConnectionState.CONNECTED:
            return
        
        self._state = ConnectionState.CONNECTING
        
        try:
            # Check if socket file exists
            if not self.config.socket_path.exists():
                raise ConnectionError(f"Socket file does not exist: {self.config.socket_path}")
            
            # Connect with timeout
            connect_coro = asyncio.open_unix_connection(str(self.config.socket_path))
            
            self._reader, self._writer = await asyncio.wait_for(
                connect_coro,
                timeout=self.config.timeout
            )
            
            self._state = ConnectionState.CONNECTED
            
        except asyncio.TimeoutError:
            self._state = ConnectionState.DISCONNECTED
            raise ConnectionTimeout(self.config.timeout)
        except FileNotFoundError:
            self._state = ConnectionState.DISCONNECTED
            raise ConnectionError(f"Socket file not found: {self.config.socket_path}")
        except PermissionError:
            self._state = ConnectionState.DISCONNECTED
            raise ConnectionError(f"Permission denied accessing socket: {self.config.socket_path}")
        except Exception as e:
            self._state = ConnectionState.DISCONNECTED
            raise ConnectionError(f"Failed to connect to Unix socket: {e}")
    
    async def send(self, message: EncodedMessage) -> None:
        """Send a message over the IPC channel."""
        await self._ensure_connected()
        
        try:
            await self._send_message(message)
        except Exception as e:
            # If sending failed due to connection, try to reconnect and retry once
            if self._is_connection_error(e):
                await self._connect_with_retry()
                await self._send_message(message)
            else:
                raise MessageError(f"IPC channel error: {e}")
    
    async def _send_message(self, message: EncodedMessage) -> None:
        """Send a message without retry logic."""
        if self._state != ConnectionState.CONNECTED or not self._writer:
            raise ConnectionError("Not connected")
        
        try:
            # Write message using the framing protocol
            buffer = BytesIO()
            message.write_to(buffer)
            data = buffer.getvalue()
            
            self._writer.write(data)
            await self._writer.drain()
            
        except Exception as e:
            self._state = ConnectionState.DISCONNECTED
            self._reader = None
            self._writer = None
            raise ConnectionError(f"Failed to send message: {e}")
    
    async def receive(self) -> EncodedMessage:
        """Receive a message from the IPC channel."""
        await self._ensure_connected()
        
        try:
            return await self._receive_message()
        except Exception as e:
            # If receiving failed due to connection, try to reconnect and retry once
            if self._is_connection_error(e):
                await self._connect_with_retry()
                return await self._receive_message()
            else:
                raise MessageError(f"IPC channel error: {e}")
    
    async def _receive_message(self) -> EncodedMessage:
        """Receive a message without retry logic."""
        if self._state != ConnectionState.CONNECTED or not self._reader:
            raise ConnectionError("Not connected")
        
        try:
            # Read length header (4 bytes)
            length_bytes = await self._reader.readexactly(4)
            length = struct.unpack('>I', length_bytes)[0]
            
            # Read format byte (1 byte)
            format_bytes = await self._reader.readexactly(1)
            
            # Read message data
            data = await self._reader.readexactly(length)
            
            # Reconstruct the framed message for EncodedMessage.read_from
            framed_data = length_bytes + format_bytes + data
            buffer = BytesIO(framed_data)
            
            return EncodedMessage.read_from(buffer)
            
        except asyncio.IncompleteReadError:
            self._state = ConnectionState.DISCONNECTED
            self._reader = None
            self._writer = None
            raise ConnectionClosed("Connection closed by peer")
        except Exception as e:
            self._state = ConnectionState.DISCONNECTED
            self._reader = None
            self._writer = None
            raise ConnectionError(f"Failed to receive message: {e}")
    
    async def receive_with_timeout(self, timeout: float) -> EncodedMessage:
        """Receive a message with timeout."""
        try:
            return await asyncio.wait_for(self.receive(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ConnectionTimeout(timeout)
    
    async def state(self) -> ConnectionState:
        """Get the current connection state."""
        return self._state
    
    async def disconnect(self) -> None:
        """Disconnect the channel."""
        async with self._lock:
            await self._close()
    
    async def _close(self) -> None:
        """Close the connection."""
        self._state = ConnectionState.DISCONNECTED
        
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass  # Ignore errors during close
            
        self._reader = None
        self._writer = None
    
    async def _ensure_connected(self) -> None:
        """Ensure the channel is connected."""
        if self._state == ConnectionState.CONNECTED:
            return
        elif self._state == ConnectionState.FAILED:
            # For IPC, reset failed connections to allow retry
            self._connect_attempts = 0
            await self._connect_with_retry()
        else:
            await self._connect_with_retry()
    
    def _is_connection_error(self, error: Exception) -> bool:
        """Check if an error is connection-related."""
        return isinstance(error, (
            ConnectionError, ConnectionClosed, ConnectionTimeout,
            OSError, asyncio.IncompleteReadError, FileNotFoundError,
            PermissionError
        ))
    
    def get_channel_type(self) -> ChannelType:
        """Get the type of this channel."""
        return ChannelType.IPC
    
    def get_capabilities(self) -> ChannelCapabilities:
        """Get the capabilities of this channel."""
        return ChannelCapabilities.ipc_standard()
    
    async def ping(self) -> None:
        """Ping the connection to check if it's alive."""
        # For Unix sockets, check if the socket file still exists and is accessible
        if not self.config.socket_path.exists():
            raise ConnectionError("Socket file no longer exists")
        
        if self._writer:
            # Check if the writer is still valid
            if self._writer.is_closing():
                raise ConnectionError("Connection is closing")
        else:
            raise ConnectionError("No active connection")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect() 