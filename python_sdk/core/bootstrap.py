"""Bootstrap module for PyWatt Python SDK.

This module provides comprehensive module lifecycle management and initialization functionality,
including handshake, secret fetching, state building, and communication channel setup.
"""

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Union, TypeVar, Generic
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import signal
import uuid
from typing import Optional, Callable, Any, List, Dict, Union, Tuple
from dataclasses import dataclass
from .logging import init_module

# Core imports
from .error import PyWattSDKError, BootstrapError
from .state import AppState
from ..communication.ipc_types import (
    InitBlob, EndpointAnnounce, AnnounceBlob, 
    OrchestratorToModule, ModuleToOrchestrator
)
from ..communication.ipc_stdio import read_init, send_announce
from ..communication.tcp_channel import TcpChannel, ConnectionConfig, ReconnectPolicy
from ..communication.message_channel import ChannelPreferences, ChannelType
from ..security.secret_client import SecretClient, get_module_secret_client
from ..security.typed_secret import TypedSecret

logger = logging.getLogger(__name__)


@dataclass
class BootstrapResult:
    """Result of module bootstrap process."""
    app_state: AppState
    ipc_handle: asyncio.Task
    tcp_channel: Optional[TcpChannel] = None


async def bootstrap_module(
    secret_keys: List[str],
    endpoints: List[EndpointAnnounce],
    state_builder: Callable[[InitBlob, List[TypedSecret]], Any],
    channel_preferences: Optional[ChannelPreferences] = None
) -> Tuple[AppState, asyncio.Task]:
    """Bootstrap a PyWatt module with comprehensive lifecycle management.
    
    This function implements the complete module bootstrap process:
    1. Initialize logging
    2. Perform handshake with orchestrator
    3. Fetch initial secrets
    4. Build user state
    5. Setup communication channels
    6. Announce endpoints
    7. Start IPC processing
    
    Args:
        secret_keys: List of secret keys to fetch at startup
        endpoints: List of endpoints to announce to the orchestrator
        state_builder: Function that builds user state from init and secrets
        channel_preferences: Optional channel preferences for communication
        
    Returns:
        Tuple of (AppState, IPC processing task handle)
        
    Raises:
        BootstrapError: If any step of the bootstrap process fails
    """
    try:
        # 1. Initialize logging
        init_module()
        logger.info("Starting module bootstrap process")
        
        # 2. Perform handshake with orchestrator
        logger.debug("Reading initialization data from orchestrator")
        init_data = await read_init()
        logger.info(f"Received init data for module: {init_data.module_id}")
        
        # 3. Setup secret client and fetch secrets
        logger.debug("Setting up secret client")
        secret_client = await get_module_secret_client(
            init_data.orchestrator_api,
            init_data.module_id
        )
        
        # Fetch initial secrets
        secrets = []
        if secret_keys:
            logger.debug(f"Fetching {len(secret_keys)} secrets")
            for key in secret_keys:
                try:
                    secret = await secret_client.get_secret(key)
                    secrets.append(secret)
                    logger.debug(f"Successfully fetched secret: {key}")
                except Exception as e:
                    logger.error(f"Failed to fetch secret {key}: {e}")
                    raise BootstrapError(f"Failed to fetch secret {key}: {e}")
        
        # 4. Build user state
        logger.debug("Building user state")
        user_state = state_builder(init_data, secrets)
        
        # 5. Create AppState
        app_state = AppState(
            module_id=init_data.module_id,
            orchestrator_api=init_data.orchestrator_api,
            secret_client=secret_client,
            user_state=user_state
        )
        
        # 6. Setup communication channels based on preferences
        tcp_channel = None
        
        # Check if TCP channel config is provided in InitBlob
        if init_data.tcp_channel:
            # TCP channel available in InitBlob - connect unless explicitly disabled
            should_connect_tcp = True
            
            # Only skip TCP if preferences explicitly disable it
            if channel_preferences and not channel_preferences.use_tcp:
                should_connect_tcp = False
                logger.info("TCP channel available but disabled by preferences")
            
            if should_connect_tcp:
                try:
                    logger.debug("Setting up TCP channel from InitBlob configuration")
                    tcp_channel = await setup_tcp_channel(init_data)
                    app_state.tcp_channel = tcp_channel
                    logger.info("TCP channel established successfully")
                except Exception as e:
                    logger.warning(f"Failed to setup TCP channel: {e}")
                    # Check if it's required
                    if init_data.tcp_channel.required:
                        raise BootstrapError(f"Required TCP channel failed: {e}")
        else:
            # Legacy: Check preferences for TCP setup
            if channel_preferences and ChannelType.TCP in channel_preferences.preferred_channels:
                logger.warning("No TCP channel config in InitBlob but requested via preferences")
        
        # 7. Announce endpoints to orchestrator
        logger.debug(f"Announcing {len(endpoints)} endpoints")
        announcement = AnnounceBlob(
            listen=getattr(init_data, 'listen', '127.0.0.1:0'),
            endpoints=endpoints
        )
        await send_announce(announcement)
        logger.info("Successfully announced endpoints to orchestrator")
        
        # Send Identify message via IPC for IPC-only modules
        if not tcp_channel:
            logger.debug(f"Sending Identify message via IPC with module_id: {init_data.module_id}")
            identify_msg = ModuleToOrchestrator.identify_msg(init_data.module_id)
            # Send via stdout
            import json
            json_str = identify_msg.model_dump_json()
            sys.stdout.write(json_str + '\n')
            sys.stdout.flush()
            logger.info(f"Successfully sent Identify message via IPC for module: {init_data.module_id}")
        
        # 8. Start IPC processing task
        logger.debug("Starting IPC processing task")
        ipc_task = asyncio.create_task(
            process_ipc_messages(app_state, tcp_channel)
        )
        
        logger.info("Module bootstrap completed successfully")
        return app_state, ipc_task
        
    except Exception as e:
        logger.error(f"Module bootstrap failed: {e}")
        if isinstance(e, BootstrapError):
            raise
        else:
            raise BootstrapError(f"Bootstrap failed: {e}")


async def setup_tcp_channel(init_data: InitBlob) -> TcpChannel:
    """Setup TCP channel for communication with orchestrator."""
    try:
        # Use TCP channel configuration from InitBlob
        if not init_data.tcp_channel:
            raise BootstrapError("No TCP channel configuration in InitBlob")
        
        tcp_config = init_data.tcp_channel
        
        # Configure connection with exponential backoff retry
        config = ConnectionConfig(
            host=tcp_config.host,
            port=tcp_config.port,
            use_tls=tcp_config.tls_enabled,
            timeout=5.0,  # 5 second connection timeout
            reconnect_policy=ReconnectPolicy.EXPONENTIAL_BACKOFF,
            initial_delay=0.5,  # Start with 500ms delay
            max_delay=5.0,     # Max 5 seconds between retries
            multiplier=1.5     # 1.5x backoff multiplier
        )
        
        logger.info(f"Connecting to TCP channel at {tcp_config.host}:{tcp_config.port} with exponential backoff retry")
        
        channel = TcpChannel(config)
        await channel.connect()
        
        # Send Identify message immediately after connecting
        logger.debug(f"Sending Identify message with module_id: {init_data.module_id}")
        identify_msg = ModuleToOrchestrator.identify_msg(init_data.module_id)
        from ..communication.message import Message, EncodedMessage
        msg = Message.new(identify_msg)
        encoded = EncodedMessage.from_message(msg)
        await channel.send(encoded)
        logger.info(f"Successfully sent Identify message for module: {init_data.module_id}")
        
        return channel
        
    except Exception as e:
        raise BootstrapError(f"Failed to setup TCP channel: {e}")


async def process_ipc_messages(
    app_state: AppState,
    tcp_channel: Optional[TcpChannel] = None
) -> None:
    """Process IPC messages from the orchestrator.
    
    This task runs in the background and handles:
    - Heartbeat messages
    - Shutdown signals
    - Module-to-module routing
    - HTTP requests over IPC
    """
    logger.debug("IPC message processing task started")
    
    try:
        # Import here to avoid circular imports
        from ..communication.ipc_stdio import process_ipc_messages as process_stdio_ipc
        
        # Start stdio IPC processing
        await process_stdio_ipc()
        
    except Exception as e:
        logger.error(f"IPC processing error: {e}")
    finally:
        logger.debug("IPC message processing task finished")


async def process_orchestrator_message(
    message: OrchestratorToModule,
    app_state: AppState,
    channel_name: str = "IPC"
) -> bool:
    """Process a message from the orchestrator.
    
    Args:
        message: The message from the orchestrator
        app_state: The application state
        channel_name: Name of the channel for logging
        
    Returns:
        True if processing should continue, False if shutdown requested
    """
    try:
        if message.type == "Heartbeat":
            logger.debug(f"{channel_name}: Received heartbeat, sending ack")
            # Send heartbeat ack back
            ack = ModuleToOrchestrator(type="HeartbeatAck")
            # In a full implementation, we'd send this back through the appropriate channel
            return True
            
        elif message.type == "Shutdown":
            logger.warning(f"{channel_name}: Received shutdown signal")
            return False
            
        elif message.type == "RoutedModuleResponse":
            logger.debug(f"{channel_name}: Received routed module response")
            # Handle module-to-module response
            return True
            
        elif message.type == "RoutedModuleMessage":
            logger.debug(f"{channel_name}: Received routed module message")
            # Handle module-to-module message
            return True
            
        elif message.type == "HttpRequest":
            logger.debug(f"{channel_name}: Received HTTP request")
            # Handle HTTP-over-IPC request
            return True
            
        else:
            logger.debug(f"{channel_name}: Received unhandled message type: {message.type}")
            return True
            
    except Exception as e:
        logger.error(f"{channel_name}: Error processing message: {e}")
        return True


class AppStateExt:
    """Extension methods for AppState to support module-to-module messaging."""
    
    def __init__(self, app_state: AppState):
        self.app_state = app_state
        self._message_handlers: Dict[str, Callable] = {}
    
    async def register_module_message_handler(
        self,
        source_module_id: str,
        handler: Callable[[str, uuid.UUID, bytes], asyncio.Future[None]]
    ) -> None:
        """Register a handler for module-to-module messages from a specific source module."""
        self._message_handlers[source_module_id] = handler
        logger.debug(f"Registered message handler for module: {source_module_id}")
    
    async def remove_module_message_handler(self, source_module_id: str) -> None:
        """Remove a registered handler for a specific source module."""
        if source_module_id in self._message_handlers:
            del self._message_handlers[source_module_id]
            logger.debug(f"Removed message handler for module: {source_module_id}")
    
    async def handle_module_message(
        self,
        source_module_id: str,
        request_id: uuid.UUID,
        payload: bytes
    ) -> None:
        """Handle an incoming module-to-module message."""
        if source_module_id in self._message_handlers:
            handler = self._message_handlers[source_module_id]
            try:
                await handler(source_module_id, request_id, payload)
            except Exception as e:
                logger.error(f"Error handling message from {source_module_id}: {e}")
        else:
            logger.info(f"No handler registered for messages from {source_module_id}")


# Legacy bootstrap function for backward compatibility
async def bootstrap_module_legacy(
    secret_keys: List[str],
    endpoints: List[EndpointAnnounce],
    state_builder: Callable[[InitBlob, List[TypedSecret]], Any]
) -> Tuple[AppState, asyncio.Task]:
    """Legacy bootstrap function for backward compatibility."""
    return await bootstrap_module(secret_keys, endpoints, state_builder, None)


__all__ = [
    "BootstrapResult",
    "bootstrap_module",
    "bootstrap_module_legacy",
    "setup_tcp_channel",
    "process_ipc_messages",
    "process_orchestrator_message",
    "AppStateExt",
] 