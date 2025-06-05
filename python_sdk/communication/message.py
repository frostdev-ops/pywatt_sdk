"""
Message encoding and decoding module for PyWatt Python SDK.

This module provides a standardized structure for encoding and decoding
messages between modules and the orchestration component. It offers a simple
API for creating, encoding, decoding, and streaming messages.
"""

import asyncio
import json
import struct
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generic, Optional, TypeVar, Union, BinaryIO
from io import BytesIO

import msgpack


T = TypeVar('T')


class MessageError(Exception):
    """Base class for message-related errors."""
    pass


class JsonSerializationError(MessageError):
    """Failed to serialize message to JSON."""
    pass


class BinaryConversionError(MessageError):
    """Failed to convert message to binary format."""
    pass


class BinaryDecodingError(MessageError):
    """Failed to decode message from binary format."""
    pass


class UnsupportedFormat(MessageError):
    """Unsupported encoding format."""
    def __init__(self, format_type: 'EncodingFormat'):
        self.format_type = format_type
        super().__init__(f"Unsupported encoding format: {format_type}")


class NoContent(MessageError):
    """Message lacks required content."""
    pass


class InvalidFormat(MessageError):
    """Invalid message format."""
    pass


class EncodingFormat(Enum):
    """The encoding format for a message."""
    JSON = "json"
    MSGPACK = "msgpack"  # Python-friendly binary format
    AUTO = "auto"


@dataclass
class MessageMetadata:
    """Metadata for a message."""
    id: Optional[str] = None
    timestamp: Optional[int] = None
    source: Optional[str] = None
    destination: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None
    
    def with_id(self, msg_id: str) -> 'MessageMetadata':
        """Set the message ID."""
        self.id = msg_id
        return self
    
    def with_timestamp(self, timestamp: int) -> 'MessageMetadata':
        """Set the timestamp."""
        self.timestamp = timestamp
        return self
    
    def with_source(self, source: str) -> 'MessageMetadata':
        """Set the source."""
        self.source = source
        return self
    
    def with_destination(self, destination: str) -> 'MessageMetadata':
        """Set the destination."""
        self.destination = destination
        return self
    
    def with_property(self, key: str, value: Any) -> 'MessageMetadata':
        """Add a property."""
        if self.properties is None:
            self.properties = {}
        self.properties[key] = value
        return self


@dataclass
class Message(Generic[T]):
    """
    Generic message type to be used for communication
    between modules and the orchestrator.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: T = None
    metadata: MessageMetadata = field(default_factory=MessageMetadata)
    
    @classmethod
    def new(cls, content: T) -> 'Message[T]':
        """Create a new message with the given content."""
        return cls(content=content)
    
    @classmethod
    def with_metadata(cls, content: T, metadata: MessageMetadata) -> 'Message[T]':
        """Create a new message with metadata."""
        return cls(content=content, metadata=metadata)
    
    def encode(self, format_type: EncodingFormat = EncodingFormat.JSON) -> 'EncodedMessage':
        """Encode the message to an EncodedMessage."""
        return EncodedMessage.from_message(self, format_type)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the message to a dictionary."""
        return {
            'id': self.id,
            'content': self.content,
            'metadata': {
                'id': self.metadata.id,
                'timestamp': self.metadata.timestamp,
                'source': self.metadata.source,
                'destination': self.metadata.destination,
                'properties': self.metadata.properties,
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message[Any]':
        """Create a message from a dictionary."""
        metadata_data = data.get('metadata', {})
        metadata = MessageMetadata(
            id=metadata_data.get('id'),
            timestamp=metadata_data.get('timestamp'),
            source=metadata_data.get('source'),
            destination=metadata_data.get('destination'),
            properties=metadata_data.get('properties'),
        )
        
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            content=data.get('content'),
            metadata=metadata
        )


class EncodedMessage:
    """An encoded message ready for transmission."""
    
    def __init__(self, data: bytes, format_type: EncodingFormat):
        self.data = data
        self.format = format_type
    
    @classmethod
    def from_message(cls, message: Message[T], format_type: EncodingFormat = EncodingFormat.JSON) -> 'EncodedMessage':
        """Create an encoded message from a Message."""
        try:
            if format_type == EncodingFormat.JSON:
                data = json.dumps(message.to_dict()).encode('utf-8')
            elif format_type == EncodingFormat.MSGPACK:
                data = msgpack.packb(message.to_dict())
            elif format_type == EncodingFormat.AUTO:
                # Default to JSON for auto
                data = json.dumps(message.to_dict()).encode('utf-8')
                format_type = EncodingFormat.JSON
            else:
                raise UnsupportedFormat(format_type)
            
            return cls(data, format_type)
        except (json.JSONEncodeError, TypeError) as e:
            raise JsonSerializationError(f"Failed to serialize message: {e}")
        except Exception as e:
            raise BinaryConversionError(f"Failed to encode message: {e}")
    
    def decode(self) -> Message[Any]:
        """Decode the message to a Message object."""
        try:
            if self.format == EncodingFormat.JSON:
                data_dict = json.loads(self.data.decode('utf-8'))
            elif self.format == EncodingFormat.MSGPACK:
                data_dict = msgpack.unpackb(self.data, raw=False)
            else:
                raise UnsupportedFormat(self.format)
            
            return Message.from_dict(data_dict)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise JsonSerializationError(f"Failed to deserialize message: {e}")
        except Exception as e:
            raise BinaryDecodingError(f"Failed to decode message: {e}")
    
    def decode_payload(self) -> Any:
        """Decode just the payload content."""
        message = self.decode()
        return message.content
    
    def to_format(self, new_format: EncodingFormat) -> 'EncodedMessage':
        """Convert the message to a different format."""
        if self.format == new_format:
            return self
        
        # Decode and re-encode
        message = self.decode()
        return EncodedMessage.from_message(message, new_format)
    
    def to_string(self) -> str:
        """Convert the encoded message to a string representation."""
        if self.format == EncodingFormat.JSON:
            return self.data.decode('utf-8')
        else:
            # For binary formats, return a JSON representation
            message = self.decode()
            return json.dumps(message.to_dict(), indent=2)
    
    async def write_to_async(self, writer) -> None:
        """Write the message to an async writer with length-prefixed framing."""
        # Write length (4 bytes, big-endian)
        length = len(self.data)
        await writer.write(struct.pack('>I', length))
        
        # Write format byte (1 byte)
        format_byte = self._format_to_byte()
        await writer.write(bytes([format_byte]))
        
        # Write data
        await writer.write(self.data)
        await writer.drain()
    
    @classmethod
    async def read_from_async(cls, reader) -> 'EncodedMessage':
        """Read a message from an async reader with length-prefixed framing."""
        # Read length (4 bytes)
        length_bytes = await reader.readexactly(4)
        length = struct.unpack('>I', length_bytes)[0]
        
        # Read format byte (1 byte)
        format_bytes = await reader.readexactly(1)
        format_type = cls._byte_to_format(format_bytes[0])
        
        # Read data
        data = await reader.readexactly(length)
        
        return cls(data, format_type)
    
    def write_to(self, writer: BinaryIO) -> None:
        """Write the message to a binary writer with length-prefixed framing."""
        # Write length (4 bytes, big-endian)
        length = len(self.data)
        writer.write(struct.pack('>I', length))
        
        # Write format byte (1 byte)
        format_byte = self._format_to_byte()
        writer.write(bytes([format_byte]))
        
        # Write data
        writer.write(self.data)
    
    @classmethod
    def read_from(cls, reader: BinaryIO) -> 'EncodedMessage':
        """Read a message from a binary reader with length-prefixed framing."""
        # Read length (4 bytes)
        length_bytes = reader.read(4)
        if len(length_bytes) != 4:
            raise InvalidFormat("Incomplete length header")
        length = struct.unpack('>I', length_bytes)[0]
        
        # Read format byte (1 byte)
        format_bytes = reader.read(1)
        if len(format_bytes) != 1:
            raise InvalidFormat("Incomplete format byte")
        format_type = cls._byte_to_format(format_bytes[0])
        
        # Read data
        data = reader.read(length)
        if len(data) != length:
            raise InvalidFormat("Incomplete message data")
        
        return cls(data, format_type)
    
    def _format_to_byte(self) -> int:
        """Convert format enum to byte representation."""
        if self.format == EncodingFormat.JSON:
            return 0
        elif self.format == EncodingFormat.MSGPACK:
            return 1
        else:
            return 0  # Default to JSON
    
    @classmethod
    def _byte_to_format(cls, byte_val: int) -> EncodingFormat:
        """Convert byte representation to format enum."""
        if byte_val == 0:
            return EncodingFormat.JSON
        elif byte_val == 1:
            return EncodingFormat.MSGPACK
        else:
            return EncodingFormat.JSON  # Default to JSON


class EncodedStream:
    """A stream of encoded messages."""
    
    def __init__(self):
        self._queue = asyncio.Queue()
        self._closed = False
    
    async def send(self, message: Message[T]) -> None:
        """Send a message to the stream."""
        if self._closed:
            raise RuntimeError("Stream is closed")
        
        encoded = message.encode()
        await self._queue.put(encoded)
    
    async def send_encoded(self, message: EncodedMessage) -> None:
        """Send an encoded message to the stream."""
        if self._closed:
            raise RuntimeError("Stream is closed")
        
        await self._queue.put(message)
    
    async def receive(self) -> EncodedMessage:
        """Receive a message from the stream."""
        if self._closed and self._queue.empty():
            raise RuntimeError("Stream is closed and empty")
        
        return await self._queue.get()
    
    def close(self) -> None:
        """Close the stream."""
        self._closed = True
    
    @property
    def closed(self) -> bool:
        """Check if the stream is closed."""
        return self._closed 