"""IPC communication over stdin/stdout.

This module provides the basic IPC functionality for communicating with the
PyWatt orchestrator via stdin/stdout, following the same patterns as the Rust SDK.
"""

import sys
import json
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
import logging
import io

from .ipc_types import (
    InitBlob,
    AnnounceBlob,
    OrchestratorToModule,
    ModuleToOrchestrator,
)
try:
    from core.error import HandshakeError, AnnouncementError, NetworkError
except ImportError:
    class HandshakeError(Exception):
        pass
    class AnnouncementError(Exception):
        pass
    class NetworkError(Exception):
        pass

logger = logging.getLogger(__name__)


async def read_init() -> InitBlob:
    """Read initialization data from stdin.
    
    Returns:
        InitBlob: The initialization data from the orchestrator
        
    Raises:
        HandshakeError: If reading or parsing the init data fails
    """
    try:
        # Try to use async reading first (for real stdin)
        try:
            loop = asyncio.get_event_loop()
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            
            # Read one line
            line = await reader.readline()
            if not line:
                raise HandshakeError("Stdin closed unexpectedly during handshake")
            
            line_str = line.decode('utf-8').strip()
        except (AttributeError, io.UnsupportedOperation, OSError):
            # Fallback to sync reading for test mocks (StringIO)
            line_str = sys.stdin.readline().strip()
            if not line_str:
                raise HandshakeError("Stdin closed unexpectedly during handshake")
        
        if not line_str:
            raise HandshakeError("Empty line received during handshake")
        
        # Parse JSON
        try:
            data = json.loads(line_str)
            init_blob = InitBlob.model_validate(data)
            logger.info(
                "Received initialization data",
                extra={
                    "module_id": init_blob.module_id,
                    "orchestrator_api": init_blob.orchestrator_api,
                    "listen": init_blob.listen,
                }
            )
            return init_blob
        except json.JSONDecodeError as e:
            raise HandshakeError(f"Failed to parse init JSON: {e}")
        except Exception as e:
            raise HandshakeError(f"Failed to validate init data: {e}")
            
    except HandshakeError:
        raise
    except Exception as e:
        raise HandshakeError(f"Failed to read from stdin: {e}")


def send_announce(announce_blob: AnnounceBlob) -> None:
    """Send announcement data to stdout.
    
    Args:
        announce_blob: The announcement data to send
        
    Raises:
        AnnouncementError: If serializing or writing the announcement fails
    """
    try:
        # Serialize to JSON
        json_str = announce_blob.model_dump_json()
        
        # Write to stdout with newline
        sys.stdout.write(json_str + '\n')
        sys.stdout.flush()
        
        logger.info(
            "Sent module announcement",
            extra={
                "listen": announce_blob.listen,
                "endpoint_count": len(announce_blob.endpoints),
            }
        )
        
    except Exception as e:
        raise AnnouncementError(f"Failed to send announcement: {e}")


async def process_ipc_messages(
    message_handler: Optional[Callable[[OrchestratorToModule], Awaitable[None]]] = None
) -> None:
    """Process incoming IPC messages from stdin.
    
    Args:
        message_handler: Optional handler for processing messages
        
    Raises:
        NetworkError: If message processing fails
    """
    try:
        logger.info("Starting IPC message processing loop")
        
        # Try to use async reading first (for real stdin)
        try:
            loop = asyncio.get_event_loop()
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            
            while True:
                try:
                    # Read one line
                    line = await reader.readline()
                    if not line:
                        logger.info("Stdin closed, exiting IPC loop")
                        break
                    
                    line_str = line.decode('utf-8').strip()
                    if not line_str:
                        continue
                    
                    # Parse and handle message
                    await _process_message_line(line_str, message_handler)
                    
                except Exception as e:
                    logger.error(f"Error in IPC message loop: {e}")
                    # Continue processing other messages
                    continue
        except (AttributeError, io.UnsupportedOperation, OSError):
            # Fallback to sync reading for test mocks (StringIO)
            while True:
                try:
                    line_str = sys.stdin.readline()
                    if not line_str:
                        logger.info("Stdin closed, exiting IPC loop")
                        break
                    
                    line_str = line_str.strip()
                    if not line_str:
                        continue
                    
                    # Parse and handle message
                    await _process_message_line(line_str, message_handler)
                    
                except Exception as e:
                    logger.error(f"Error in IPC message loop: {e}")
                    # Continue processing other messages
                    continue
                
    except Exception as e:
        raise NetworkError(f"IPC message processing failed: {e}")


async def _process_message_line(
    line_str: str,
    message_handler: Optional[Callable[[OrchestratorToModule], Awaitable[None]]] = None
) -> None:
    """Process a single IPC message line.
    
    Args:
        line_str: The JSON message line
        message_handler: Optional handler for processing messages
    """
    try:
        data = json.loads(line_str)
        message = OrchestratorToModule.model_validate(data)
        
        logger.debug(
            "Received IPC message",
            extra={"message_type": type(message).__name__}
        )
        
        # Handle message
        if message_handler:
            await message_handler(message)
        else:
            await _default_message_handler(message)
            
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse IPC message JSON: {e}")
    except Exception as e:
        logger.error(f"Failed to process IPC message: {e}")


def send_ipc_message(message: ModuleToOrchestrator) -> None:
    """Send an IPC message to the orchestrator via stdout.
    
    Args:
        message: The message to send
        
    Raises:
        NetworkError: If sending the message fails
    """
    try:
        json_str = message.model_dump_json()
        sys.stdout.write(json_str + '\n')
        sys.stdout.flush()
        
        logger.debug(
            "Sent IPC message",
            extra={"message_type": type(message).__name__}
        )
        
    except Exception as e:
        raise NetworkError(f"Failed to send IPC message: {e}")


async def _default_message_handler(message: OrchestratorToModule) -> None:
    """Default handler for IPC messages.
    
    Args:
        message: The message to handle
    """
    # Import here to avoid circular imports
    try:
        from security.secret_client import get_global_secret_client
    except ImportError:
        def get_global_secret_client():
            return None
    
    if hasattr(message, 'secret') and message.secret:
        # Handle secret update
        client = get_global_secret_client()
        if client:
            await client._handle_secret_update(message.secret)
    
    elif hasattr(message, 'rotated') and message.rotated:
        # Handle secret rotation
        client = get_global_secret_client()
        if client:
            await client._handle_secret_rotation(message.rotated)
    
    elif hasattr(message, 'shutdown') and message.shutdown:
        # Handle shutdown request
        logger.info("Received shutdown request from orchestrator")
        # In a real implementation, this would trigger graceful shutdown
        
    else:
        logger.warning(f"Unhandled IPC message type: {type(message).__name__}") 