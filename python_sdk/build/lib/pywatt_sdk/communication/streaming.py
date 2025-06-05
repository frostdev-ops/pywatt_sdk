"""Advanced Message Patterns and Streaming Support

This module provides support for streaming large data transfers, chunked message
transmission, flow control, bidirectional streaming, and various message patterns
including pub/sub, request multiplexing, and priority queues.
"""

import asyncio
import gzip
import hashlib
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Dict, List, Optional, Callable, Awaitable, Any, Union, Tuple
import logging
from datetime import datetime, timedelta
import uuid

from .message import EncodedMessage, MessageError, MessageMetadata
from .tcp_channel import MessageChannel

logger = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    """Stream configuration for large data transfers."""
    max_chunk_size: int = 64 * 1024  # 64KB
    window_size: int = 10
    ack_timeout: float = 30.0  # seconds
    max_retries: int = 3
    preserve_order: bool = True
    enable_compression: bool = True
    compression_threshold: int = 1024  # 1KB


class StreamPriority(IntEnum):
    """Stream priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class StreamMetadata:
    """Metadata for a data stream."""
    total_size: int
    content_type: Optional[str] = None
    priority: StreamPriority = StreamPriority.NORMAL
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """Stream chunk containing part of a larger message."""
    stream_id: str
    sequence: int
    total_chunks: int
    data: bytes
    compressed: bool = False
    checksum: int = 0
    is_final: bool = False
    stream_metadata: Optional[StreamMetadata] = None

    def __post_init__(self):
        if self.checksum == 0:
            self.checksum = self._calculate_checksum(self.data)

    @staticmethod
    def _calculate_checksum(data: bytes) -> int:
        """Calculate CRC32 checksum."""
        return hashlib.crc32(data) & 0xffffffff


@dataclass
class StreamAck:
    """Stream acknowledgment message."""
    stream_id: str
    sequence: int
    success: bool
    error: Optional[str] = None


class FlowControlWindow:
    """Flow control window for managing outstanding chunks."""

    def __init__(self, max_window: int):
        self.max_window = max_window
        self.outstanding: Dict[int, datetime] = {}
        self.next_sequence = 0
        self.acknowledged: Dict[int, bool] = {}

    def can_send(self) -> bool:
        """Check if we can send another chunk."""
        return len(self.outstanding) < self.max_window

    def record_sent(self, sequence: int) -> None:
        """Record a chunk as sent."""
        self.outstanding[sequence] = datetime.now()
        self.next_sequence = max(self.next_sequence, sequence + 1)

    def record_ack(self, sequence: int, success: bool) -> None:
        """Record an acknowledgment."""
        self.outstanding.pop(sequence, None)
        self.acknowledged[sequence] = success

    def get_timed_out_chunks(self, timeout: float) -> List[int]:
        """Get chunks that have timed out."""
        now = datetime.now()
        timeout_delta = timedelta(seconds=timeout)
        return [
            seq for seq, sent_at in self.outstanding.items()
            if now - sent_at > timeout_delta
        ]

    def next_sequence_num(self) -> int:
        """Get the next sequence number to send."""
        return self.next_sequence

    def is_complete(self, total_chunks: int) -> bool:
        """Check if all chunks have been acknowledged."""
        return (
            len(self.outstanding) == 0 and
            len(self.acknowledged) >= total_chunks and
            all(self.acknowledged.values())
        )


class StreamSender:
    """Stream sender for chunked data transmission."""

    def __init__(
        self,
        data: bytes,
        metadata: StreamMetadata,
        config: StreamConfig,
        channel: MessageChannel,
        ack_receiver: asyncio.Queue[StreamAck],
    ):
        self.stream_id = str(uuid.uuid4())
        self.config = config
        self.flow_control = FlowControlWindow(config.window_size)
        self.chunks = self._create_chunks(data, metadata)
        self.channel = channel
        self.ack_receiver = ack_receiver
        self.retry_counts: Dict[int, int] = defaultdict(int)

    async def send(self) -> None:
        """Send the stream with flow control."""
        total_chunks = len(self.chunks)
        pending_chunks = deque(self.chunks)

        # Send chunks with flow control
        while True:
            # Send chunks while window allows
            while pending_chunks and self.flow_control.can_send():
                chunk = pending_chunks.popleft()
                await self._send_chunk(chunk)
                self.flow_control.record_sent(chunk.sequence)

            # Check for completion
            if self.flow_control.is_complete(total_chunks):
                logger.debug(f"Stream {self.stream_id} completed successfully")
                break

            # Process acknowledgments and handle timeouts
            await self._process_acks_and_timeouts(pending_chunks)

            # Small delay to avoid busy waiting
            await asyncio.sleep(0.01)

    async def _send_chunk(self, chunk: StreamChunk) -> None:
        """Send a single chunk."""
        # Serialize chunk (simplified - in real implementation would use proper serialization)
        chunk_data = self._serialize_chunk(chunk)
        message = EncodedMessage(chunk_data)

        await self.channel.send(message)

        logger.debug(f"Sent chunk {chunk.sequence + 1}/{chunk.total_chunks} for stream {self.stream_id}")

    async def _process_acks_and_timeouts(self, pending_chunks: deque) -> None:
        """Process acknowledgments and handle timeouts."""
        # Process available acknowledgments
        try:
            while True:
                ack = self.ack_receiver.get_nowait()
                if ack.stream_id == self.stream_id:
                    self.flow_control.record_ack(ack.sequence, ack.success)

                    if not ack.success:
                        logger.warning(f"Chunk {ack.sequence} failed for stream {self.stream_id}: {ack.error}")
                        await self._handle_chunk_retry(ack.sequence, pending_chunks)
        except asyncio.QueueEmpty:
            pass

        # Handle timeouts
        timed_out_chunks = self.flow_control.get_timed_out_chunks(self.config.ack_timeout)
        for sequence in timed_out_chunks:
            logger.warning(f"Chunk {sequence} timed out for stream {self.stream_id}")
            await self._handle_chunk_retry(sequence, pending_chunks)

    async def _handle_chunk_retry(self, sequence: int, pending_chunks: deque) -> None:
        """Handle retrying a failed chunk."""
        retry_count = self.retry_counts[sequence]

        if retry_count >= self.config.max_retries:
            raise MessageError(f"Chunk {sequence} exceeded max retries for stream {self.stream_id}")

        self.retry_counts[sequence] += 1

        # Find the chunk to retry
        chunk_to_retry = None
        for chunk in self.chunks:
            if chunk.sequence == sequence:
                chunk_to_retry = chunk
                break

        if chunk_to_retry:
            # Re-queue the chunk for retry
            pending_chunks.appendleft(chunk_to_retry)
            # Remove from flow control to allow retry
            self.flow_control.record_ack(sequence, False)

        logger.warning(f"Retrying chunk {sequence} for stream {self.stream_id} (attempt {retry_count + 1})")

    def _create_chunks(self, data: bytes, metadata: StreamMetadata) -> List[StreamChunk]:
        """Create chunks from data."""
        chunks = []
        total_size = len(data)
        total_chunks = (total_size + self.config.max_chunk_size - 1) // self.config.max_chunk_size

        for sequence, start in enumerate(range(0, total_size, self.config.max_chunk_size)):
            end = min(start + self.config.max_chunk_size, total_size)
            chunk_data = data[start:end]

            # Compress if enabled and chunk is large enough
            compressed = False
            if (self.config.enable_compression and
                len(chunk_data) >= self.config.compression_threshold):
                try:
                    compressed_data = gzip.compress(chunk_data)
                    if len(compressed_data) < len(chunk_data):
                        chunk_data = compressed_data
                        compressed = True
                except Exception:
                    pass  # Keep original data if compression fails

            chunk = StreamChunk(
                stream_id=self.stream_id,
                sequence=sequence,
                total_chunks=total_chunks,
                data=chunk_data,
                compressed=compressed,
                is_final=sequence == total_chunks - 1,
                stream_metadata=metadata if sequence == 0 else None,
            )

            chunks.append(chunk)

        return chunks

    def _serialize_chunk(self, chunk: StreamChunk) -> bytes:
        """Serialize chunk for transmission (simplified implementation)."""
        # In a real implementation, this would use proper serialization like msgpack or protobuf
        import json
        chunk_dict = {
            'stream_id': chunk.stream_id,
            'sequence': chunk.sequence,
            'total_chunks': chunk.total_chunks,
            'data': chunk.data.hex(),  # Convert bytes to hex string
            'compressed': chunk.compressed,
            'checksum': chunk.checksum,
            'is_final': chunk.is_final,
            'stream_metadata': {
                'total_size': chunk.stream_metadata.total_size,
                'content_type': chunk.stream_metadata.content_type,
                'priority': chunk.stream_metadata.priority.value,
                'properties': chunk.stream_metadata.properties,
            } if chunk.stream_metadata else None,
        }
        return json.dumps(chunk_dict).encode('utf-8')


class StreamReceiver:
    """Stream receiver for reassembling chunked data."""

    def __init__(
        self,
        stream_id: str,
        config: StreamConfig,
        ack_sender: asyncio.Queue[StreamAck],
    ):
        self.stream_id = stream_id
        self.config = config
        self.received_chunks: Dict[int, StreamChunk] = {}
        self.stream_metadata: Optional[StreamMetadata] = None
        self.ack_sender = ack_sender
        self.completion_future: Optional[asyncio.Future[bytes]] = None

    def set_completion_future(self, future: asyncio.Future[bytes]) -> None:
        """Set the future to complete when stream is fully received."""
        self.completion_future = future

    async def process_chunk(self, chunk: StreamChunk) -> bool:
        """Process a received chunk. Returns True if stream is complete."""
        # Verify checksum
        expected_checksum = StreamChunk._calculate_checksum(chunk.data)
        if chunk.checksum != expected_checksum:
            await self._send_ack(chunk.sequence, False, "Checksum mismatch")
            return False

        # Decompress if needed
        if chunk.compressed:
            try:
                chunk.data = gzip.decompress(chunk.data)
            except Exception as e:
                await self._send_ack(chunk.sequence, False, f"Decompression failed: {e}")
                return False

        # Store chunk
        self.received_chunks[chunk.sequence] = chunk

        # Store metadata from first chunk
        if chunk.sequence == 0 and chunk.stream_metadata:
            self.stream_metadata = chunk.stream_metadata

        # Send acknowledgment
        await self._send_ack(chunk.sequence, True)

        # Check if stream is complete
        if await self._check_completion(chunk):
            await self._finalize_stream()
            return True

        return False

    async def _check_completion(self, latest_chunk: StreamChunk) -> bool:
        """Check if the stream is complete."""
        if not latest_chunk.is_final:
            return False

        total_chunks = latest_chunk.total_chunks

        # Check if we have all chunks
        for i in range(total_chunks):
            if i not in self.received_chunks:
                return False

        return True

    async def _finalize_stream(self) -> None:
        """Finalize the stream by reassembling data."""
        # Sort chunks by sequence
        sorted_chunks = sorted(self.received_chunks.values(), key=lambda c: c.sequence)

        # Reassemble data
        reassembled_data = b''.join(chunk.data for chunk in sorted_chunks)

        # Complete the future if set
        if self.completion_future and not self.completion_future.done():
            self.completion_future.set_result(reassembled_data)

        logger.debug(f"Stream {self.stream_id} reassembled successfully ({len(reassembled_data)} bytes)")

    async def _send_ack(self, sequence: int, success: bool, error: Optional[str] = None) -> None:
        """Send an acknowledgment."""
        ack = StreamAck(
            stream_id=self.stream_id,
            sequence=sequence,
            success=success,
            error=error,
        )
        await self.ack_sender.put(ack)

    def _deserialize_chunk(self, data: bytes) -> StreamChunk:
        """Deserialize chunk from transmission data (simplified implementation)."""
        import json
        chunk_dict = json.loads(data.decode('utf-8'))

        metadata = None
        if chunk_dict['stream_metadata']:
            md = chunk_dict['stream_metadata']
            metadata = StreamMetadata(
                total_size=md['total_size'],
                content_type=md['content_type'],
                priority=StreamPriority(md['priority']),
                properties=md['properties'],
            )

        return StreamChunk(
            stream_id=chunk_dict['stream_id'],
            sequence=chunk_dict['sequence'],
            total_chunks=chunk_dict['total_chunks'],
            data=bytes.fromhex(chunk_dict['data']),
            compressed=chunk_dict['compressed'],
            checksum=chunk_dict['checksum'],
            is_final=chunk_dict['is_final'],
            stream_metadata=metadata,
        )


@dataclass
class PubSubMessage:
    """Pub/Sub message."""
    topic: str
    payload: bytes
    priority: StreamPriority = StreamPriority.NORMAL
    ttl: Optional[float] = None  # seconds
    publisher: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Subscription:
    """Topic subscription."""
    topic_pattern: str
    handler: Callable[[PubSubMessage], Awaitable[None]]
    include_history: bool = False
    max_queue_size: int = 1000


class PriorityMessageQueue:
    """Priority-based message queue."""

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.queues: Dict[StreamPriority, deque] = {
            priority: deque() for priority in StreamPriority
        }
        self.semaphore = asyncio.Semaphore(0)
        self._lock = asyncio.Lock()

    async def enqueue(self, message: EncodedMessage, priority: StreamPriority) -> None:
        """Enqueue a message with given priority."""
        async with self._lock:
            if self.size() >= self.max_size:
                raise MessageError("Queue is full")

            self.queues[priority].append(message)
            self.semaphore.release()

    async def dequeue(self) -> Optional[EncodedMessage]:
        """Dequeue the highest priority message."""
        await self.semaphore.acquire()

        async with self._lock:
            # Check queues in priority order (highest first)
            for priority in sorted(StreamPriority, reverse=True):
                if self.queues[priority]:
                    return self.queues[priority].popleft()

            return None

    def size(self) -> int:
        """Get total number of messages in all queues."""
        return sum(len(queue) for queue in self.queues.values())

    def is_empty(self) -> bool:
        """Check if all queues are empty."""
        return self.size() == 0


class RequestMultiplexer:
    """Request multiplexer for handling multiple concurrent requests."""

    def __init__(self, request_timeout: float = 30.0):
        self.request_timeout = request_timeout
        self.pending_requests: Dict[str, asyncio.Future[EncodedMessage]] = {}
        self._lock = asyncio.Lock()

    async def send_request(
        self,
        request: EncodedMessage,
        channel: MessageChannel,
    ) -> EncodedMessage:
        """Send a request and wait for response."""
        request_id = str(uuid.uuid4())

        # Create future for response
        response_future: asyncio.Future[EncodedMessage] = asyncio.Future()

        async with self._lock:
            self.pending_requests[request_id] = response_future

        try:
            # Add request ID to message metadata
            if hasattr(request, 'metadata') and request.metadata:
                request.metadata.properties = request.metadata.properties or {}
                request.metadata.properties['request_id'] = request_id

            # Send request
            await channel.send(request)

            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=self.request_timeout)
            return response

        except asyncio.TimeoutError:
            raise MessageError(f"Request {request_id} timed out")
        finally:
            async with self._lock:
                self.pending_requests.pop(request_id, None)

    async def handle_response(self, response: EncodedMessage, request_id: str) -> None:
        """Handle a response for a pending request."""
        async with self._lock:
            if request_id in self.pending_requests:
                future = self.pending_requests[request_id]
                if not future.done():
                    future.set_result(response)

    async def get_stats(self) -> Tuple[int, List[str]]:
        """Get statistics about pending requests."""
        async with self._lock:
            return len(self.pending_requests), list(self.pending_requests.keys()) 