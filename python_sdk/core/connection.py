"""Connection management for PyWatt SDK.

This module provides the connection management functionality for PyWatt modules,
including automatic reconnection with exponential backoff and jitter.
"""

import asyncio
import logging
import random
from typing import Dict, Optional, Any, Callable, Awaitable, TypeVar, Generic, Union

from .error import ConnectionError, PyWattSDKError, NetworkError, Result

logger = logging.getLogger(__name__)

T = TypeVar('T')
ConnT = TypeVar('ConnT')

# Default retry configuration
DEFAULT_RETRY_CONFIG = {
    "max_attempts": 10,
    "initial_backoff_ms": 100,
    "max_backoff_ms": 30000,
    "backoff_multiplier": 1.5,
    "jitter": 0.2,
}


class ConnectionManager(Generic[ConnT]):
    """Connection manager with automatic reconnection capabilities.
    
    This class manages connections to external services, automatically handling
    reconnection with exponential backoff and jitter when the connection fails.
    
    Examples:
        ```python
        # Create a connection manager for orchestrator API
        manager = ConnectionManager(orchestrator_api, 
                                   connect_func=create_connection)
        
        # Get a connection, will automatically retry if needed
        conn = await manager.get_connection()
        
        # Use the connection
        result = await conn.call_api()
        ```
    """

    def __init__(
        self, 
        service_url: str, 
        connect_func: Callable[[str], Awaitable[ConnT]],
        retry_config: Optional[Dict[str, Any]] = None,
        health_check: Optional[Callable[[ConnT], Awaitable[bool]]] = None,
    ) -> None:
        """Initialize the connection manager.
        
        Args:
            service_url: URL of the service to connect to
            connect_func: Async function that creates a new connection to the service
            retry_config: Configuration for retry behavior (optional)
            health_check: Optional function to check if a connection is healthy
        """
        self.service_url = service_url
        self.connect_func = connect_func
        self.retry_config = retry_config or DEFAULT_RETRY_CONFIG.copy()
        self.health_check = health_check
        self.connection: Optional[ConnT] = None
        self.attempt = 0
        self._lock = asyncio.Lock()
    
    async def is_healthy(self) -> bool:
        """Check if the current connection is healthy.
        
        Returns:
            True if the connection is healthy, False otherwise
        """
        if self.connection is None:
            return False
            
        if self.health_check is None:
            # Without a health check, assume connection is valid
            return True
            
        try:
            return await self.health_check(self.connection)
        except Exception:
            return False
    
    async def get_connection(self) -> ConnT:
        """Get a connection to the service.
        
        If a healthy connection already exists, returns it.
        Otherwise, attempts to establish a new connection with retry logic.
        
        Returns:
            A connection to the service
            
        Raises:
            ConnectionError: If connection fails after all retry attempts
        """
        async with self._lock:
            # Return existing connection if healthy
            if self.connection and await self.is_healthy():
                return self.connection
                
            # Reset attempt counter
            self.attempt = 0
                
            # Try to connect with retries
            while self.attempt < self.retry_config["max_attempts"]:
                try:
                    self.connection = await self.connect_func(self.service_url)
                    if await self.is_healthy():
                        self.attempt = 0
                        return self.connection
                    else:
                        # Connection isn't healthy
                        raise ConnectionError("Connection health check failed")
                except Exception as e:
                    self.attempt += 1
                    backoff = self._calculate_backoff()
                    
                    if self.attempt >= self.retry_config["max_attempts"]:
                        raise ConnectionError(
                            f"Failed to connect to {self.service_url} after "
                            f"{self.retry_config['max_attempts']} attempts", 
                            cause=e
                        )
                        
                    logger.warning(
                        f"Connection attempt {self.attempt} to {self.service_url} "
                        f"failed: {e}. Retrying in {backoff}ms"
                    )
                    await asyncio.sleep(backoff / 1000)
                
            # This should never happen because we raise in the loop
            raise ConnectionError(f"Failed to connect to {self.service_url}")
    
    def _calculate_backoff(self) -> float:
        """Calculate the backoff time for the current retry attempt.
        
        Returns:
            Backoff time in milliseconds
        """
        backoff = self.retry_config["initial_backoff_ms"] * (
            self.retry_config["backoff_multiplier"] ** (self.attempt - 1)
        )
        backoff = min(backoff, self.retry_config["max_backoff_ms"])
        
        # Add jitter
        jitter_factor = 1 - self.retry_config["jitter"] + (
            random.random() * self.retry_config["jitter"] * 2
        )
        return backoff * jitter_factor
    
    async def close(self) -> None:
        """Close the connection, if it exists."""
        if self.connection and hasattr(self.connection, 'close'):
            close_method = getattr(self.connection, 'close')
            if callable(close_method):
                if asyncio.iscoroutinefunction(close_method):
                    await close_method()
                else:
                    close_method()
                    
        self.connection = None


class ServiceProvider(Generic[T]):
    """Provider for a service that can be registered with the orchestrator.
    
    This class manages service registration with the orchestrator and provides
    type-safe access to service properties.
    """
    
    def __init__(
        self,
        service_type: str,
        name: str,
        address: str,
        version: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> None:
        """Initialize a service provider.
        
        Args:
            service_type: Type of the service (e.g., "cache", "database")
            name: Name of the service provider
            address: Address of the service (URL or connection string)
            version: Optional version of the service
            metadata: Optional metadata about the service
        """
        self.service_type = service_type
        self.name = name
        self.address = address
        self.version = version
        self.metadata = metadata or {}
        self.provider_id: Optional[str] = None
        
    async def register(self, orchestrator_client: Any) -> Result[str]:
        """Register this service provider with the orchestrator.
        
        Args:
            orchestrator_client: Client to use for orchestrator API calls
            
        Returns:
            Result containing the provider ID if successful
        """
        try:
            self.provider_id = await orchestrator_client.register_provider(
                service_type=self.service_type,
                name=self.name,
                address=self.address,
                version=self.version,
                metadata=self.metadata
            )
            return Result.ok(self.provider_id)
        except PyWattSDKError as e:
            return Result.err(e)
        except Exception as e:
            return Result.err(NetworkError("Failed to register service provider", cause=e))
