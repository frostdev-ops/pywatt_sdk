"""Server module for PyWatt Python SDK.

This module provides comprehensive module lifecycle management and serving functionality,
including HTTP server management, IPC communication, and port negotiation.
"""

import asyncio
import logging
import os
import sys
from typing import Optional, Callable, Any, List, Dict, Union, TypeVar, Generic
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from pathlib import Path
import subprocess
import tempfile
import signal

# Core imports
from ..core.error import PyWattSDKError, ServerError, BootstrapError, NetworkError
from ..core.state import AppState
from ..core.config import Config
from ..core.logging import init_module
from ..communication import read_init, send_announce, process_ipc_messages
from ..communication.ipc_types import (
    InitBlob, EndpointAnnounce, IpcPortNegotiation, IpcPortResponse, AnnounceBlob
)
from ..communication.port_negotiation import PortNegotiationManager
from ..security import get_module_secret_client, SecretClient
from ..security.typed_secret import TypedSecret

logger = logging.getLogger(__name__)

# Global state for pre-allocated port from InitBlob
_pre_allocated_port: Optional[int] = None


def set_pre_allocated_port(port: int) -> None:
    """Set the pre-allocated port from the InitBlob."""
    global _pre_allocated_port
    _pre_allocated_port = port
    logger.debug(f"Set pre-allocated port: {port}")


def get_pre_allocated_port() -> Optional[int]:
    """Get the pre-allocated port if available."""
    return _pre_allocated_port


@dataclass
class ServeOptions:
    """Options for serving a module."""
    
    # Whether to bind an HTTP server (if False, only IPC will be used)
    bind_http: bool = True
    
    # Specific port to request from orchestrator (if None, orchestrator will assign one)
    specific_port: Optional[int] = None
    
    # Alternative listen address (defaults to 127.0.0.1)
    listen_addr: Optional[str] = None
    
    # Additional server options
    options: Dict[str, Any] = field(default_factory=dict)


class ServerManager(ABC):
    """Abstract base class for server implementations."""
    
    @abstractmethod
    async def start_server(self, app: Any, addr: str, port: int) -> None:
        """Start the HTTP server."""
        pass
    
    @abstractmethod
    async def serve_ipc(self, app: Any) -> None:
        """Serve the application over IPC."""
        pass
    
    @abstractmethod
    def create_app(self, router_builder: Callable, app_state: AppState) -> Any:
        """Create the application instance."""
        pass


class FastAPIServerManager(ServerManager):
    """Server manager for FastAPI applications."""
    
    async def start_server(self, app: Any, addr: str, port: int) -> None:
        """Start the FastAPI server."""
        try:
            import uvicorn
            config = uvicorn.Config(
                app=app,
                host=addr,
                port=port,
                log_level="info",
                access_log=True
            )
            server = uvicorn.Server(config)
            await server.serve()
        except ImportError:
            raise ServerError("FastAPI/uvicorn not available. Install with: pip install fastapi uvicorn")
    
    async def serve_ipc(self, app: Any) -> None:
        """Serve FastAPI over IPC."""
        # For now, this is a placeholder - full IPC serving would require
        # integration with the HTTP-over-IPC communication layer
        logger.info("IPC serving for FastAPI not yet implemented")
        # Keep the task alive
        while True:
            await asyncio.sleep(1)
    
    def create_app(self, router_builder: Callable, app_state: AppState) -> Any:
        """Create FastAPI application."""
        try:
            from fastapi import FastAPI
            app = FastAPI()
            router = router_builder(app_state)
            app.include_router(router)
            return app
        except ImportError:
            raise ServerError("FastAPI not available. Install with: pip install fastapi")


class FlaskServerManager(ServerManager):
    """Server manager for Flask applications."""
    
    async def start_server(self, app: Any, addr: str, port: int) -> None:
        """Start the Flask server."""
        try:
            # Run Flask in a thread since it's not natively async
            import threading
            
            def run_flask():
                app.run(host=addr, port=port, debug=False)
            
            thread = threading.Thread(target=run_flask, daemon=True)
            thread.start()
            
            # Keep the async task alive
            while thread.is_alive():
                await asyncio.sleep(1)
                
        except ImportError:
            raise ServerError("Flask not available. Install with: pip install flask")
    
    async def serve_ipc(self, app: Any) -> None:
        """Serve Flask over IPC."""
        logger.info("IPC serving for Flask not yet implemented")
        while True:
            await asyncio.sleep(1)
    
    def create_app(self, router_builder: Callable, app_state: AppState) -> Any:
        """Create Flask application."""
        try:
            from flask import Flask
            app = Flask(__name__)
            router_builder(app, app_state)  # Flask uses different pattern
            return app
        except ImportError:
            raise ServerError("Flask not available. Install with: pip install flask")


def get_server_manager(framework: str = "fastapi") -> ServerManager:
    """Get the appropriate server manager for the framework."""
    if framework.lower() == "fastapi":
        return FastAPIServerManager()
    elif framework.lower() == "flask":
        return FlaskServerManager()
    else:
        raise ServerError(f"Unsupported framework: {framework}")


async def negotiate_port(specific_port: Optional[int] = None) -> int:
    """Request a port from the orchestrator via IPC."""
    # Check for pre-allocated port first
    if pre_allocated := get_pre_allocated_port():
        logger.info(f"Using pre-allocated port from InitBlob: {pre_allocated}")
        return pre_allocated
    
    # If no pre-allocated port, try to negotiate
    if specific_port:
        logger.warning(f"No pre-allocated port found, attempting to negotiate specific port: {specific_port}")
    else:
        logger.warning("No pre-allocated port found, attempting to negotiate dynamic port")
    
    try:
        # Use the port negotiation manager
        manager = PortNegotiationManager()
        port = await manager.negotiate_port(specific_port)
        logger.info(f"Received port from orchestrator: {port}")
        return port
    except Exception as e:
        raise ServerError(f"Port negotiation failed: {e}")


async def serve_with_options(
    app: Any,
    options: ServeOptions,
    framework: str = "fastapi"
) -> None:
    """Serve the given application with the specified options."""
    
    # Set environment variables for IPC-only mode
    if not options.bind_http:
        os.environ["IPC_ONLY"] = "true"
        os.environ["PYWATT_IPC_ONLY"] = "true"
        logger.info("Set IPC_ONLY environment variables for SDK components")
    
    server_manager = get_server_manager(framework)
    
    # Always set up IPC serving
    ipc_task = asyncio.create_task(server_manager.serve_ipc(app))
    
    # If HTTP binding is requested, negotiate a port and start HTTP server
    if options.bind_http:
        try:
            # Negotiate port with orchestrator
            port = await negotiate_port(options.specific_port)
            
            # Bind HTTP server
            listen_addr = options.listen_addr or "127.0.0.1"
            
            logger.info(f"Starting HTTP server on {listen_addr}:{port}")
            
            # Start the server
            server_task = asyncio.create_task(
                server_manager.start_server(app, listen_addr, port)
            )
            
            # Run both tasks
            done, pending = await asyncio.wait(
                [server_task, ipc_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Check for exceptions
            for task in done:
                if task.exception():
                    raise task.exception()
                    
        except Exception as e:
            ipc_task.cancel()
            raise ServerError(f"Server error: {e}")
    else:
        # Only serve via IPC
        logger.info("Module serving via IPC only")
        await ipc_task


async def serve_module(app: Any, framework: str = "fastapi") -> None:
    """Serve the given application with default options."""
    await serve_with_options(app, ServeOptions(), framework)


async def serve_module_full(
    secret_keys: List[str],
    endpoints: List[EndpointAnnounce],
    state_builder: Callable[[InitBlob, List[TypedSecret]], Any],
    router_builder: Callable[[AppState], Any],
    framework: str = "fastapi",
    options: Optional[ServeOptions] = None
) -> None:
    """Serve a module with comprehensive lifecycle management.
    
    This function implements the complete module lifecycle:
    1. Initialize logging
    2. Perform handshake with orchestrator
    3. Fetch initial secrets
    4. Build user state
    5. Build router/app
    6. Announce endpoints
    7. Start IPC processing
    8. Serve the module
    
    Args:
        secret_keys: List of secret keys to fetch at startup
        endpoints: List of endpoints to announce to the orchestrator
        state_builder: Function that builds user state from init and secrets
        router_builder: Function that builds the router/app from app state
        framework: Web framework to use ("fastapi" or "flask")
        options: Serving options (defaults to ServeOptions())
    """
    from ..core.bootstrap import bootstrap_module
    
    try:
        # Bootstrap the module to get AppState and IPC handle
        app_state, ipc_handle = await bootstrap_module(
            secret_keys=secret_keys,
            endpoints=endpoints,
            state_builder=state_builder,
            channel_preferences=None  # Use default channel preferences
        )
        
        # Get server manager and create the application
        server_manager = get_server_manager(framework)
        app = server_manager.create_app(router_builder, app_state)
        
        # Use provided options or defaults
        serve_options = options or ServeOptions()
        
        # Start the server with shutdown handling
        serve_task = asyncio.create_task(
            serve_with_options(app, serve_options, framework)
        )
        
        # Wait for either the server to complete or the IPC handle (shutdown signal)
        done, pending = await asyncio.wait(
            [serve_task, ipc_handle],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Check results
        for task in done:
            if task == serve_task:
                if task.exception():
                    logger.error(f"HTTP server error: {task.exception()}")
                    raise task.exception()
                else:
                    logger.info("HTTP server completed successfully")
            elif task == ipc_handle:
                if task.exception():
                    logger.warning(f"IPC processing ended with error: {task.exception()}")
                else:
                    logger.info("IPC processing completed (shutdown signal received)")
        
        logger.info("Module shutting down gracefully")
        
    except Exception as e:
        logger.error(f"Module serving failed: {e}")
        raise ServerError(f"Module serving failed: {e}")


# Alias for backward compatibility
serve_module_with_lifecycle = serve_module_full


__all__ = [
    "ServeOptions",
    "ServerManager",
    "FastAPIServerManager", 
    "FlaskServerManager",
    "get_server_manager",
    "set_pre_allocated_port",
    "get_pre_allocated_port",
    "negotiate_port",
    "serve_module",
    "serve_with_options",
    "serve_module_full",
    "serve_module_with_lifecycle",
] 