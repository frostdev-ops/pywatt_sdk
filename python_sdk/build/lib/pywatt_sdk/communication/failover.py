"""Advanced Failover Mechanisms and Performance Optimizations

This module provides robust failover capabilities, circuit breaker patterns,
performance optimizations including connection pooling, message batching,
and intelligent retry mechanisms.
"""

import asyncio
import gzip
import hashlib
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Awaitable, Any, TypeVar, Generic
import logging
from datetime import datetime, timedelta
import uuid

from .message import EncodedMessage, MessageError
from .tcp_channel import ChannelType, MessageChannel

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout: float = 60.0  # seconds
    window_size: float = 60.0  # seconds
    minimum_requests: int = 10


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    state: CircuitBreakerState
    failure_count: int
    success_count: int
    request_count: int
    last_failure_time: Optional[datetime]


class CircuitBreaker:
    """Circuit breaker for channel failure detection and protection."""

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.request_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.window_start = datetime.now()
        self._lock = asyncio.Lock()

    async def can_execute(self) -> bool:
        """Check if the circuit allows a request."""
        async with self._lock:
            if self.state == CircuitBreakerState.CLOSED:
                return True
            elif self.state == CircuitBreakerState.OPEN:
                # Check if enough time has passed to try half-open
                if self.last_failure_time:
                    time_since_failure = datetime.now() - self.last_failure_time
                    if time_since_failure.total_seconds() > self.config.timeout:
                        await self._transition_to_half_open()
                        return True
                return False
            else:  # HALF_OPEN
                return True

    async def record_success(self) -> None:
        """Record a successful execution."""
        async with self._lock:
            self.success_count += 1
            await self._increment_request_count()

            if self.state == CircuitBreakerState.HALF_OPEN:
                if self.success_count >= self.config.success_threshold:
                    await self._transition_to_closed()

    async def record_failure(self) -> None:
        """Record a failed execution."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            await self._increment_request_count()
            await self._evaluate_state()

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self.state

    def get_stats(self) -> CircuitBreakerStats:
        """Get failure statistics."""
        return CircuitBreakerStats(
            state=self.state,
            failure_count=self.failure_count,
            success_count=self.success_count,
            request_count=self.request_count,
            last_failure_time=self.last_failure_time,
        )

    async def _increment_request_count(self) -> None:
        """Increment request count and reset window if needed."""
        self.request_count += 1

        # Reset window if needed
        window_elapsed = datetime.now() - self.window_start
        if window_elapsed.total_seconds() > self.config.window_size:
            self.request_count = 1
            self.window_start = datetime.now()
            self.failure_count = 0
            self.success_count = 0

    async def _evaluate_state(self) -> None:
        """Evaluate whether to open the circuit."""
        if (self.request_count >= self.config.minimum_requests and
            self.failure_count >= self.config.failure_threshold):
            await self._transition_to_open()

    async def _transition_to_open(self) -> None:
        """Transition circuit to open state."""
        if self.state != CircuitBreakerState.OPEN:
            self.state = CircuitBreakerState.OPEN
            logger.warning("Circuit breaker opened due to failures")

    async def _transition_to_half_open(self) -> None:
        """Transition circuit to half-open state."""
        self.state = CircuitBreakerState.HALF_OPEN
        self.success_count = 0
        logger.info("Circuit breaker transitioned to half-open")

    async def _transition_to_closed(self) -> None:
        """Transition circuit to closed state."""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        logger.info("Circuit breaker closed - channel recovered")


@dataclass
class RetryConfig:
    """Retry policy configuration."""
    max_attempts: int = 3
    base_delay: float = 0.1  # seconds
    max_delay: float = 30.0  # seconds
    backoff_multiplier: float = 2.0
    jitter_factor: float = 0.1
    retry_on_all_errors: bool = False


class RetryMechanism:
    """Retry mechanism with exponential backoff and jitter."""

    def __init__(self, config: RetryConfig):
        self.config = config

    async def execute(
        self,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Execute a function with retry logic."""
        attempt = 0
        delay = self.config.base_delay

        while True:
            attempt += 1

            try:
                result = await operation()
                if attempt > 1:
                    logger.debug(f"Operation succeeded after {attempt} attempts")
                return result
            except Exception as error:
                if attempt >= self.config.max_attempts:
                    logger.error(f"Operation failed after {attempt} attempts: {error}")
                    raise

                if not self.config.retry_on_all_errors:
                    # Add logic here to determine if error is retryable
                    # For now, retry all errors
                    pass

                logger.debug(f"Operation failed on attempt {attempt}, retrying in {delay:.2f}s: {error}")

                # Add jitter to prevent thundering herd
                jitter = (random.random() - 0.5) * self.config.jitter_factor
                jittered_delay = delay * (1.0 + jitter)

                await asyncio.sleep(jittered_delay)

                # Exponential backoff
                delay = min(delay * self.config.backoff_multiplier, self.config.max_delay)


@dataclass
class BatchConfig:
    """Message batching configuration."""
    max_batch_size: int = 100
    max_batch_delay: float = 0.01  # seconds
    max_batch_bytes: int = 1024 * 1024  # 1MB
    preserve_order: bool = True


@dataclass
class MessageBatch:
    """Message batch for efficient transmission."""
    messages: List[EncodedMessage] = field(default_factory=list)
    total_size: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def add_message(self, message: EncodedMessage) -> bool:
        """Add a message to the batch."""
        message_size = len(message.data)
        if self.can_add(message_size):
            self.total_size += message_size
            self.messages.append(message)
            return True
        return False

    def is_ready(self, config: BatchConfig) -> bool:
        """Check if the batch is ready to send based on configuration."""
        return (
            len(self.messages) >= config.max_batch_size or
            self.total_size >= config.max_batch_bytes or
            (datetime.now() - self.created_at).total_seconds() >= config.max_batch_delay
        )

    def is_empty(self) -> bool:
        """Check if the batch is empty."""
        return len(self.messages) == 0

    def __len__(self) -> int:
        """Get the number of messages in the batch."""
        return len(self.messages)

    def can_add(self, message_size: int) -> bool:
        """Check if a message can be added to the batch."""
        return self.total_size + message_size <= (2**31 - 1)  # Avoid overflow


class MessageBatcher:
    """Message batcher for efficient bulk transmission."""

    def __init__(self, config: BatchConfig):
        self.config = config
        self.pending_batch = MessageBatch()
        self.batch_queue: asyncio.Queue[MessageBatch] = asyncio.Queue()
        self._lock = asyncio.Lock()

    async def add_message(self, message: EncodedMessage) -> None:
        """Add a message to the batcher."""
        async with self._lock:
            if not self.pending_batch.add_message(message):
                # Current batch is full, send it and start a new one
                if not self.pending_batch.is_empty():
                    await self.batch_queue.put(self.pending_batch)
                    self.pending_batch = MessageBatch()

                # Try adding to new batch
                if not self.pending_batch.add_message(message):
                    raise MessageError("Message too large for batch")

            # Check if batch is ready to send
            if self.pending_batch.is_ready(self.config):
                await self.batch_queue.put(self.pending_batch)
                self.pending_batch = MessageBatch()

    async def flush(self) -> None:
        """Force flush any pending batch."""
        async with self._lock:
            if not self.pending_batch.is_empty():
                await self.batch_queue.put(self.pending_batch)
                self.pending_batch = MessageBatch()

    async def receive_batch(self) -> Optional[MessageBatch]:
        """Receive the next ready batch."""
        try:
            return await self.batch_queue.get()
        except asyncio.CancelledError:
            return None


class ConnectionPool(Generic[T]):
    """Connection pool for managing multiple connections to the same endpoint."""

    def __init__(
        self,
        max_connections: int,
        connection_factory: Callable[[], Awaitable[T]],
    ):
        self.max_connections = max_connections
        self.connection_factory = connection_factory
        self.connections: List[T] = []
        self.semaphore = asyncio.Semaphore(max_connections)
        self._lock = asyncio.Lock()

    async def get_connection(self) -> 'PooledConnection[T]':
        """Get a connection from the pool."""
        await self.semaphore.acquire()

        async with self._lock:
            if self.connections:
                connection = self.connections.pop()
            else:
                connection = await self.connection_factory()

        return PooledConnection(connection, self)

    async def return_connection(self, connection: T) -> None:
        """Return a connection to the pool."""
        async with self._lock:
            if len(self.connections) < self.max_connections:
                self.connections.append(connection)

        self.semaphore.release()

    def get_stats(self) -> Dict[str, int]:
        """Get pool statistics."""
        return {
            "available_connections": len(self.connections),
            "max_connections": self.max_connections,
            "active_connections": self.max_connections - self.semaphore._value,
        }


class PooledConnection(Generic[T]):
    """A pooled connection that automatically returns to the pool when done."""

    def __init__(self, connection: T, pool: ConnectionPool[T]):
        self.connection = connection
        self.pool = pool
        self._returned = False

    async def __aenter__(self) -> T:
        return self.connection

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.return_to_pool()

    async def return_to_pool(self) -> None:
        """Return the connection to the pool."""
        if not self._returned:
            await self.pool.return_connection(self.connection)
            self._returned = True

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying connection."""
        return getattr(self.connection, name)


@dataclass
class PerformanceConfig:
    """Performance optimization configuration."""
    enable_compression: bool = True
    compression_threshold: int = 1024  # bytes
    enable_zero_copy: bool = False
    io_buffer_size: int = 8192
    tcp_nodelay: bool = True
    tcp_send_buffer: Optional[int] = None
    tcp_recv_buffer: Optional[int] = None


class MessageCompressor:
    """Message compressor for large messages."""

    def __init__(self, config: PerformanceConfig):
        self.config = config

    def compress_message(self, message: EncodedMessage) -> bool:
        """Compress a message if it meets the threshold. Returns True if compressed."""
        if not self.config.enable_compression:
            return False

        if len(message.data) < self.config.compression_threshold:
            return False

        try:
            compressed_data = gzip.compress(message.data)
            if len(compressed_data) < len(message.data):
                # Only use compression if it actually reduces size
                message.data = compressed_data
                # Mark as compressed in metadata if available
                if hasattr(message, 'metadata') and message.metadata:
                    message.metadata.properties = message.metadata.properties or {}
                    message.metadata.properties['compressed'] = 'gzip'
                return True
        except Exception as e:
            logger.warning(f"Failed to compress message: {e}")

        return False

    def decompress_message(self, message: EncodedMessage) -> None:
        """Decompress a message if it's marked as compressed."""
        if not hasattr(message, 'metadata') or not message.metadata:
            return

        properties = message.metadata.properties or {}
        if properties.get('compressed') == 'gzip':
            try:
                message.data = gzip.decompress(message.data)
                # Remove compression marker
                del properties['compressed']
            except Exception as e:
                raise MessageError(f"Failed to decompress message: {e}")


@dataclass
class FailoverConfig:
    """Failover manager configuration."""
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    batch: Optional[BatchConfig] = field(default_factory=BatchConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    enable_graceful_degradation: bool = True
    health_check_interval: float = 10.0  # seconds


class FailoverManager:
    """Comprehensive failover manager."""

    def __init__(self, config: FailoverConfig):
        self.config = config
        self.circuit_breakers: Dict[ChannelType, CircuitBreaker] = {}
        self.retry_mechanism = RetryMechanism(config.retry)
        self.message_batcher = MessageBatcher(config.batch) if config.batch else None
        self.compressor = MessageCompressor(config.performance)
        self._lock = asyncio.Lock()

    async def execute_with_failover(
        self,
        channel_type: ChannelType,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Execute an operation with comprehensive failover protection."""
        # Get or create circuit breaker for this channel
        async with self._lock:
            if channel_type not in self.circuit_breakers:
                self.circuit_breakers[channel_type] = CircuitBreaker(self.config.circuit_breaker)

        circuit_breaker = self.circuit_breakers[channel_type]

        # Check if circuit breaker allows execution
        if not await circuit_breaker.can_execute():
            raise MessageError(f"Circuit breaker is open for channel {channel_type}")

        # Execute with retry mechanism
        async def protected_operation() -> T:
            start_time = time.time()
            try:
                result = await operation()
                # Record success
                latency = time.time() - start_time
                await circuit_breaker.record_success()
                return result
            except Exception as e:
                # Record failure
                await circuit_breaker.record_failure()
                raise

        return await self.retry_mechanism.execute(protected_operation)

    async def send_with_batching(self, message: EncodedMessage) -> None:
        """Send a message using batching if enabled."""
        if self.message_batcher:
            await self.message_batcher.add_message(message)
        else:
            raise MessageError("Batching not enabled")

    async def flush_batches(self) -> None:
        """Flush any pending batches."""
        if self.message_batcher:
            await self.message_batcher.flush()

    def get_circuit_breaker_stats(self) -> Dict[ChannelType, CircuitBreakerStats]:
        """Get circuit breaker statistics for all channels."""
        return {
            channel: breaker.get_stats()
            for channel, breaker in self.circuit_breakers.items()
        }

    async def set_circuit_breaker_state(
        self,
        channel: ChannelType,
        state: CircuitBreakerState,
    ) -> None:
        """Manually set circuit breaker state (for testing/admin purposes)."""
        async with self._lock:
            if channel in self.circuit_breakers:
                self.circuit_breakers[channel].state = state 