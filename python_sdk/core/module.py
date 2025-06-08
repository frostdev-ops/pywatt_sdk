"""Module class for PyWatt SDK.

This module provides the core Module class that implements the functionality
required for PyWatt modules, including context manager support, lifecycle
management, and service registration.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Awaitable, TypeVar, Generic, Union

from .error import (
    PyWattSDKError, 
    BootstrapError, 
    HandshakeError, 
    AnnouncementError,
    ModuleError, 
    Result,
    ServiceDiscoveryError
)
from .connection import ConnectionManager, ServiceProvider

logger = logging.getLogger(__name__)

T = TypeVar('T')


class Module:
    """A Wattson module that can communicate with the orchestrator.
    
    This class provides the core functionality for implementing a module
    that can register with the Wattson orchestrator, handle requests,
    and discover other services.
    
    Examples:
        Basic usage:
        
        ```python
        from pywatt_sdk.core.module import Module
        
        async def main():
            module = Module(name="example-module", version="1.0.0")
            await module.start()
            
            # Register a service
            await module.register_service("cache", "example-cache", "redis://localhost:6379")
            
            # Register endpoints
            @module.endpoint("/api/data")
            async def handle_data(request):
                return {"data": "example"}
                
            try:
                await module.run_forever()
            finally:
                await module.shutdown()
        ```
        
        With context manager:
        
        ```python
        async with Module(name="example-module", version="1.0.0") as module:
            # Module is automatically started and will be shut down
            await module.run()
        ```
    """

    def __init__(
        self,
        name: str,
        version: str,
        config: Optional[Dict[str, Any]] = None,
        orchestrator_api: Optional[str] = None,
    ) -> None:
        """Initialize a PyWatt module.
        
        Args:
            name: Name of the module
            version: Version of the module
            config: Optional configuration for the module
            orchestrator_api: Optional URL of the orchestrator API
        """
        self.name = name
        self.version = version
        self.config = config or {}
        self.orchestrator_api = orchestrator_api
        self.module_id = f"{name}-{version}"
        self._is_started = False
        self._service_providers: Dict[str, ServiceProvider] = {}
        self._endpoints: Dict[str, Callable] = {}
        self._shutdown_event = asyncio.Event()
        
    async def __aenter__(self) -> "Module":
        """Async context manager entry.
        
        Starts the module when entering the context.
        
        Returns:
            The module instance
        """
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit.
        
        Shuts down the module when exiting the context.
        
        Args:
            exc_type: Exception type, if an exception was raised
            exc_val: Exception value, if an exception was raised
            exc_tb: Exception traceback, if an exception was raised
        """
        await self.shutdown()
    
    async def start(self) -> Result[None]:
        """Start the module.
        
        This performs the initial handshake with the orchestrator
        and sets up the module for operation.
        
        Returns:
            A Result indicating success or failure
        """
        if self._is_started:
            return Result.ok(None)
            
        try:
            # Perform handshake with orchestrator
            # This would use bootstrap functionality from core.bootstrap
            # For now, just set the flag
            self._is_started = True
            logger.info(f"Module {self.name} v{self.version} started")
            return Result.ok(None)
        except Exception as e:
            logger.error(f"Failed to start module: {e}")
            if isinstance(e, PyWattSDKError):
                return Result.err(e)
            return Result.err(BootstrapError(f"Failed to start module: {e}", cause=e))
    
    async def shutdown(self) -> Result[None]:
        """Shut down the module.
        
        This performs a graceful shutdown of the module, closing
        all connections and releasing resources.
        
        Returns:
            A Result indicating success or failure
        """
        if not self._is_started:
            return Result.ok(None)
            
        try:
            # Signal shutdown
            self._shutdown_event.set()
            
            # Clean up resources
            self._is_started = False
            logger.info(f"Module {self.name} v{self.version} shut down")
            return Result.ok(None)
        except Exception as e:
            logger.error(f"Error during module shutdown: {e}")
            if isinstance(e, PyWattSDKError):
                return Result.err(e)
            return Result.err(ModuleError(f"Error during module shutdown: {e}", cause=e))
    
    async def run(self) -> Result[None]:
        """Run the module until shutdown is signaled.
        
        This is a convenience method that starts the module if it's not
        already started, then waits for the shutdown signal.
        
        Returns:
            A Result indicating success or failure
        """
        if not self._is_started:
            start_result = await self.start()
            if start_result.is_err():
                return start_result
                
        try:
            await self._shutdown_event.wait()
            return Result.ok(None)
        except Exception as e:
            logger.error(f"Error while running module: {e}")
            if isinstance(e, PyWattSDKError):
                return Result.err(e)
            return Result.err(ModuleError(f"Error while running module: {e}", cause=e))
    
    async def register_service(
        self,
        service_type: str,
        name: str,
        address: str,
        version: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Result[str]:
        """Register a service provider with the orchestrator.
        
        Args:
            service_type: Type of the service (e.g., "cache", "database")
            name: Name of the service
            address: Address of the service (URL or connection string)
            version: Optional version of the service
            metadata: Optional metadata about the service
            
        Returns:
            A Result containing the provider ID if successful
        """
        if not self._is_started:
            return Result.err(ModuleError("Module not started"))
            
        try:
            provider = ServiceProvider(
                service_type=service_type,
                name=name,
                address=address,
                version=version,
                metadata=metadata
            )
            
            # Would call orchestrator API here
            # For now, just store the provider
            provider_id = f"{service_type}-{name}-{id(provider)}"
            provider.provider_id = provider_id
            self._service_providers[provider_id] = provider
            
            logger.info(f"Registered service provider: {service_type}/{name}")
            return Result.ok(provider_id)
        except Exception as e:
            logger.error(f"Failed to register service: {e}")
            if isinstance(e, PyWattSDKError):
                return Result.err(e)
            return Result.err(ServiceDiscoveryError(f"Failed to register service: {e}", cause=e))
    
    def endpoint(
        self,
        path: str,
        methods: Optional[List[str]] = None,
        auth: Optional[str] = None
    ) -> Callable:
        """Decorator to register an endpoint handler.
        
        Args:
            path: URL path for the endpoint
            methods: HTTP methods supported by the endpoint
            auth: Authentication requirement for the endpoint
            
        Returns:
            Decorator function that registers the endpoint
        """
        def decorator(func: Callable) -> Callable:
            self._endpoints[path] = func
            logger.debug(f"Registered endpoint handler for {path}")
            return func
        return decorator
    
    async def discover_service(
        self,
        service_type: str,
        name: Optional[str] = None,
        version: Optional[str] = None
    ) -> Result[Dict[str, Any]]:
        """Discover a service of the given type.
        
        Args:
            service_type: Type of the service to discover
            name: Optional name of the service to discover
            version: Optional version of the service to discover
            
        Returns:
            A Result containing the service information if found
        """
        if not self._is_started:
            return Result.err(ModuleError("Module not started"))
            
        try:
            # Would call orchestrator API here
            # For now, return a mock service
            service = {
                "service_type": service_type,
                "name": name or "mock-service",
                "address": f"http://localhost:8000/{service_type}",
                "version": version or "1.0.0",
                "metadata": {}
            }
            return Result.ok(service)
        except Exception as e:
            logger.error(f"Failed to discover service: {e}")
            if isinstance(e, PyWattSDKError):
                return Result.err(e)
            return Result.err(ServiceDiscoveryError(f"Failed to discover service: {e}", cause=e))
