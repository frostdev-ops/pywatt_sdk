"""IPC communication for PyWatt modules.

This module provides functions for reading initialization data, sending announcements,
and processing runtime IPC messages, mirroring the Rust SDK's IPC implementation.
"""

import asyncio
import json
import sys
from typing import Any, Dict, Optional

try:
    from core.error import HandshakeError, AnnouncementError, PyWattSDKError
except ImportError:
    class HandshakeError(Exception):
        pass
    class AnnouncementError(Exception):
        pass
    class PyWattSDKError(Exception):
        pass

try:
    from core.logging import info, error, debug
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    info = logger.info
    error = logger.error
    debug = logger.debug

from .ipc_types import InitBlob, AnnounceBlob, OrchestratorToModule, ModuleToOrchestrator


async def read_init() -> InitBlob:
    """Read the Init message sent by the orchestrator over stdin.
    
    This function reads exactly one line from stdin to get the handshake message,
    ensuring that subsequent IPC messages remain available for the runtime loop.
    
    Returns:
        InitBlob: The initialization data from the orchestrator
        
    Raises:
        HandshakeError: If the handshake fails or data is invalid
    """
    try:
        # Read one line from stdin
        stdin = sys.stdin
        line = stdin.readline()
        
        if not line:
            raise HandshakeError("stdin closed unexpectedly during handshake")
        
        # Remove trailing newline
        line = line.rstrip('\n\r')
        
        if not line:
            raise HandshakeError("received empty line during handshake")
        
        # Protect against extremely long handshake lines
        if len(line) > 1_048_576:  # 1 MiB
            raise HandshakeError("init line exceeded 1 MiB - possible protocol corruption")
        
        debug(f"Received handshake line: {line[:100]}...")
        
        # Parse JSON
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            raise HandshakeError(f"failed to parse Init JSON: {e}")
        
        # Validate and create InitBlob
        try:
            init_blob = InitBlob(**data)
            info(f"Successfully parsed handshake for module {init_blob.module_id}")
            return init_blob
        except Exception as e:
            raise HandshakeError(f"failed to validate Init data: {e}")
            
    except HandshakeError:
        raise
    except Exception as e:
        raise HandshakeError(f"unexpected error during handshake: {e}")


def send_announce(announce: AnnounceBlob) -> None:
    """Send the module announcement to the orchestrator via stdout.
    
    Args:
        announce: The announcement data to send
        
    Raises:
        AnnouncementError: If the announcement fails to send
    """
    try:
        # Serialize to JSON
        json_data = announce.model_dump_json()
        
        # Write to stdout with newline
        print(json_data, flush=True)
        
        info(f"Successfully sent announcement: {announce.listen} with {len(announce.endpoints)} endpoints")
        
    except Exception as e:
        raise AnnouncementError(f"failed to send announcement: {e}")


async def process_ipc_messages(
    secret_client: Optional[Any] = None,
    message_handlers: Optional[Dict[str, Any]] = None,
) -> None:
    """Process runtime IPC messages from the orchestrator over stdin.
    
    This loop handles secret responses, rotation notifications, shutdown commands,
    and other runtime messages by delegating to appropriate handlers.
    
    Args:
        secret_client: Optional secret client for handling secret messages
        message_handlers: Optional dictionary of message handlers
    """
    info("Starting IPC message processing loop")
    
    try:
        # Use asyncio to read from stdin
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        
        while True:
            try:
                # Read one line
                line_bytes = await reader.readline()
                
                if not line_bytes:
                    # EOF - orchestrator closed stdin
                    info("Stdin closed by orchestrator (EOF). Terminating IPC loop.")
                    break
                
                line = line_bytes.decode('utf-8').strip()
                if not line:
                    continue
                
                debug(f"Received IPC message: {line[:100]}...")
                
                # Parse the message
                try:
                    message_data = json.loads(line)
                    message = OrchestratorToModule(**message_data)
                except Exception as e:
                    error(f"Failed to parse IPC message: {e}. Raw: {line[:200]}")
                    continue
                
                # Handle the message based on operation type
                await _handle_ipc_message(message, secret_client, message_handlers)
                
            except Exception as e:
                error(f"Error processing IPC message: {e}")
                # Continue processing other messages
                continue
                
    except Exception as e:
        error(f"Fatal error in IPC message processing: {e}")
    finally:
        info("Exited IPC message processing loop")


async def _handle_ipc_message(
    message: OrchestratorToModule,
    secret_client: Optional[Any] = None,
    message_handlers: Optional[Dict[str, Any]] = None,
) -> None:
    """Handle a single IPC message from the orchestrator.
    
    Args:
        message: The parsed message from the orchestrator
        secret_client: Optional secret client for handling secret messages
        message_handlers: Optional dictionary of message handlers
    """
    op = message.op
    
    if op == "secret" and message.secret:
        debug(f"Received secret message for key: {message.secret.name}")
        if secret_client and hasattr(secret_client, 'process_secret_message'):
            await secret_client.process_secret_message(message.secret)
        else:
            debug("No secret client available to handle secret message")
    
    elif op == "rotated" and message.rotated:
        info(f"Received rotation notification for {len(message.rotated.keys)} keys")
        if secret_client and hasattr(secret_client, 'process_rotation_message'):
            await secret_client.process_rotation_message(message.rotated)
        else:
            debug("No secret client available to handle rotation message")
    
    elif op == "shutdown":
        info("Received shutdown command from orchestrator")
        # The caller should handle this by breaking out of their main loop
        # We could use a global flag or callback here
        
    elif op == "heartbeat":
        debug("Received heartbeat from orchestrator")
        # Send heartbeat ack
        ack = ModuleToOrchestrator.heartbeat_ack_msg()
        await _send_ipc_message(ack)
    
    elif op == "http_request" and message.http_request:
        debug(f"Received HTTP request: {message.http_request.method} {message.http_request.uri}")
        # This would be handled by HTTP-over-IPC router in Phase 2
        if message_handlers and 'http_request' in message_handlers:
            await message_handlers['http_request'](message.http_request)
        else:
            debug("No HTTP request handler available")
    
    elif op == "port_response" and message.port_response:
        info(f"Received port response: success={message.port_response.success}, port={message.port_response.port}")
        # This would be handled by port negotiation manager in Phase 2
        if message_handlers and 'port_response' in message_handlers:
            await message_handlers['port_response'](message.port_response)
        else:
            debug("No port response handler available")
    
    elif op == "routed_module_message" and message.routed_module_message:
        debug("Received routed module message")
        # This would be handled by internal messaging system in Phase 2
        if message_handlers and 'routed_module_message' in message_handlers:
            await message_handlers['routed_module_message'](message.routed_module_message)
        else:
            debug("No routed module message handler available")
    
    elif op == "routed_module_response" and message.routed_module_response:
        debug("Received routed module response")
        # This would be handled by internal messaging system in Phase 2
        if message_handlers and 'routed_module_response' in message_handlers:
            await message_handlers['routed_module_response'](message.routed_module_response)
        else:
            debug("No routed module response handler available")
    
    else:
        debug(f"Received unhandled message type: {op}")


async def _send_ipc_message(message: ModuleToOrchestrator) -> None:
    """Send an IPC message to the orchestrator via stdout.
    
    Args:
        message: The message to send
    """
    try:
        json_data = message.model_dump_json()
        print(json_data, flush=True)
        debug(f"Sent IPC message: {message.op}")
    except Exception as e:
        error(f"Failed to send IPC message: {e}")


async def send_ipc_message(message: Any) -> Dict[str, Any]:
    """Send an IPC message and wait for response.
    
    This is a simplified implementation for proxy services.
    In a real implementation, this would handle request/response correlation.
    
    Args:
        message: The message to send
        
    Returns:
        Response dictionary
    """
    try:
        # For now, this is a placeholder that simulates sending a message
        # In a real implementation, this would:
        # 1. Send the message via stdout
        # 2. Wait for a correlated response via stdin
        # 3. Return the response data
        
        if hasattr(message, 'model_dump_json'):
            json_data = message.model_dump_json()
        elif hasattr(message, 'json'):
            json_data = message.json()  # Fallback for older Pydantic
        else:
            json_data = json.dumps(message.__dict__ if hasattr(message, '__dict__') else message)
        
        print(json_data, flush=True)
        debug(f"Sent IPC message: {getattr(message, 'op', 'unknown')}")
        
        # For proxy services, we simulate a successful response
        # In reality, this would be handled by the orchestrator
        return {
            "success": True,
            "connection_id": f"conn_{hash(json_data) % 10000}",
            "result": None
        }
        
    except Exception as e:
        error(f"Failed to send IPC message: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def send_ipc_message_sync(message: ModuleToOrchestrator) -> None:
    """Send an IPC message synchronously.
    
    Args:
        message: The message to send
        
    Raises:
        PyWattSDKError: If the message fails to send
    """
    try:
        json_data = message.model_dump_json()
        print(json_data, flush=True)
        debug(f"Sent IPC message: {message.op}")
    except Exception as e:
        raise PyWattSDKError(f"Failed to send IPC message: {e}")


# Convenience functions for common IPC operations

def send_get_secret_request(secret_name: str) -> None:
    """Send a get secret request to the orchestrator.
    
    Args:
        secret_name: Name of the secret to request
    """
    from .ipc_types import GetSecretRequest
    
    request = GetSecretRequest(name=secret_name)
    message = ModuleToOrchestrator.get_secret_msg(request)
    send_ipc_message_sync(message)


def send_rotation_ack(rotation_id: str, status: str = "success", message_text: Optional[str] = None) -> None:
    """Send a rotation acknowledgment to the orchestrator.
    
    Args:
        rotation_id: ID of the rotation batch
        status: Status of the rotation processing
        message_text: Optional message text
    """
    from .ipc_types import RotationAckRequest
    
    ack = RotationAckRequest(
        rotation_id=rotation_id,
        status=status,
        message=message_text
    )
    message = ModuleToOrchestrator.rotation_ack_msg(ack)
    send_ipc_message_sync(message)


def send_port_request(request_id: str, specific_port: Optional[int] = None) -> None:
    """Send a port negotiation request to the orchestrator.
    
    Args:
        request_id: Unique request ID
        specific_port: Optional specific port to request
    """
    from .ipc_types import IpcPortNegotiation
    
    request = IpcPortNegotiation(
        request_id=request_id,
        specific_port=specific_port
    )
    message = ModuleToOrchestrator.port_request_msg(request)
    send_ipc_message_sync(message) 