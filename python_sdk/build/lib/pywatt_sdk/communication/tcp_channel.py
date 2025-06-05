"""
TCP channel implementation for PyWatt modules.

This module provides a TCP-based channel for communication between modules and the
orchestrator, supporting both plain TCP and TLS-secured connections.
"""

import asyncio
import ssl
import struct
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union
from io import BytesIO

from .message_channel import (
    MessageChannel, ConnectionState, ChannelType, ChannelCapabilities,
    NetworkError, ConnectionError, ConnectionTimeout, ConnectionClosed,
    ConnectionFailed, ReconnectionFailed, InvalidConfig
)
from .message import EncodedMessage, MessageError


class ReconnectPolicy(Enum):
    """Reconnection policy for handling connection failures."""
    NONE = "none"
    FIXED_INTERVAL = "fixed_interval"
    EXPONENTIAL_BACKOFF = "exponential_backoff"


@dataclass
class TlsConfig:
    """TLS configuration for secure connections."""
    ca_cert_path: Optional[str] = None
    client_cert_path: Optional[str] = None
    client_key_path: Optional[str] = None
    verify_server: bool = True
    server_name: Optional[str] = None
    
    def create_ssl_context(self) -> ssl.SSLContext:
        """Create an SSL context from the configuration."""
        context = ssl.create_default_context()
        
        if not self.verify_server:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        
        if self.ca_cert_path:
            context.load_verify_locations(self.ca_cert_path)
        
        if self.client_cert_path and self.client_key_path:
            context.load_cert_chain(self.client_cert_path, self.client_key_path)
        
        return context


@dataclass
class ConnectionConfig:
    """Configuration for a TCP connection."""
    host: str = "localhost"
    port: int = 9000
    timeout: float = 5.0
    tls_config: Optional[TlsConfig] = None
    reconnect_policy: ReconnectPolicy = ReconnectPolicy.EXPONENTIAL_BACKOFF
    
    # Reconnection policy parameters
    fixed_delay: float = 1.0
    max_attempts: Optional[int] = None
    initial_delay: float = 0.1
    max_delay: float = 30.0
    multiplier: float = 2.0
    
    @classmethod
    def new(cls, host: str, port: int) -> 'ConnectionConfig':
        """Create a new connection configuration."""
        return cls(host=host, port=port)
    
    def with_timeout(self, timeout: float) -> 'ConnectionConfig':
        """Set the timeout for connection attempts and operations."""
        self.timeout = timeout
        return self
    
    def with_tls_config(self, tls_config: TlsConfig) -> 'ConnectionConfig':
        """Set the TLS configuration."""
        self.tls_config = tls_config
        return self
    
    def with_reconnect_policy(self, policy: ReconnectPolicy) -> 'ConnectionConfig':
        """Set the reconnection policy."""
        self.reconnect_policy = policy
        return self
    
    def with_fixed_interval(self, delay: float, max_attempts: Optional[int] = None) -> 'ConnectionConfig':
        """Configure fixed interval reconnection."""
        self.reconnect_policy = ReconnectPolicy.FIXED_INTERVAL
        self.fixed_delay = delay
        self.max_attempts = max_attempts
        return self
    
    def with_exponential_backoff(self, initial_delay: float, max_delay: float, multiplier: float = 2.0) -> 'ConnectionConfig':
        """Configure exponential backoff reconnection."""
        self.reconnect_policy = ReconnectPolicy.EXPONENTIAL_BACKOFF
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        return self


class TcpChannel(MessageChannel):
    """A TCP-based message channel."""
    
    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._state = ConnectionState.DISCONNECTED
        self._connect_attempts = 0
        self._lock = asyncio.Lock()
        
    @classmethod
    async def connect(cls, config: ConnectionConfig) -> 'TcpChannel':
        """Create and connect a new TCP channel."""
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
            # Create SSL context if TLS is configured
            ssl_context = None
            if self.config.tls_config:
                ssl_context = self.config.tls_config.create_ssl_context()
            
            # Connect with timeout
            connect_coro = asyncio.open_connection(
                self.config.host,
                self.config.port,
                ssl=ssl_context
            )
            
            self._reader, self._writer = await asyncio.wait_for(
                connect_coro,
                timeout=self.config.timeout
            )
            
            # Set TCP_NODELAY for better performance
            sock = self._writer.get_extra_info('socket')
            if sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            self._state = ConnectionState.CONNECTED
            
        except asyncio.TimeoutError:
            self._state = ConnectionState.DISCONNECTED
            raise ConnectionTimeout(self.config.timeout)
        except Exception as e:
            self._state = ConnectionState.DISCONNECTED
            raise ConnectionError(f"Failed to connect: {e}")
    
    async def send(self, message: EncodedMessage) -> None:
        """Send a message over the TCP channel."""
        await self._ensure_connected()
        
        try:
            await self._send_message(message)
        except Exception as e:
            # If sending failed due to connection, try to reconnect and retry once
            if self._is_connection_error(e):
                await self._connect_with_retry()
                await self._send_message(message)
            else:
                raise MessageError(f"TCP channel error: {e}")
    
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
        """Receive a message from the TCP channel."""
        await self._ensure_connected()
        
        try:
            return await self._receive_message()
        except Exception as e:
            # If receiving failed due to connection, try to reconnect and retry once
            if self._is_connection_error(e):
                await self._connect_with_retry()
                return await self._receive_message()
            else:
                raise MessageError(f"TCP channel error: {e}")
    
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
            raise ConnectionFailed("Connection previously failed and cannot be recovered")
        else:
            await self._connect_with_retry()
    
    def _is_connection_error(self, error: Exception) -> bool:
        """Check if an error is connection-related."""
        return isinstance(error, (
            ConnectionError, ConnectionClosed, ConnectionTimeout,
            OSError, asyncio.IncompleteReadError
        ))
    
    def get_channel_type(self) -> ChannelType:
        """Get the type of this channel."""
        return ChannelType.TCP
    
    def get_capabilities(self) -> ChannelCapabilities:
        """Get the capabilities of this channel."""
        return ChannelCapabilities.tcp_standard()
    
    async def ping(self) -> None:
        """Ping the connection to check if it's alive."""
        # For TCP, we can try to send a small message or check socket status
        if self._writer:
            sock = self._writer.get_extra_info('socket')
            if sock and sock.fileno() == -1:
                raise ConnectionError("Socket is closed")
        else:
            raise ConnectionError("No active connection")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


# Import socket for TCP_NODELAY
import socket 