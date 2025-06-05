"""Secret client for PyWatt modules.

This module provides the SecretClient class for communicating with the orchestrator's
secret provider, including caching, rotation handling, and typed secret retrieval.
"""

import asyncio
from typing import Any, Dict, List, Optional, Callable, Awaitable
from enum import Enum
import weakref

try:
    from core.error import SecretError
except ImportError:
    class SecretError(Exception):
        pass

try:
    from core.logging import info, debug, error, register_secret_for_redaction
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    info = logger.info
    debug = logger.debug
    error = logger.error
    def register_secret_for_redaction(secret):
        pass

try:
    from communication.ipc import send_get_secret_request, send_rotation_ack
except ImportError:
    def send_get_secret_request(*args, **kwargs):
        raise NotImplementedError("IPC not available")
    def send_rotation_ack(*args, **kwargs):
        raise NotImplementedError("IPC not available")

try:
    from communication.ipc_types import SecretValueResponse, RotatedNotification
except ImportError:
    SecretValueResponse = None
    RotatedNotification = None

from .typed_secret import Secret, SecretString


class RequestMode(Enum):
    """Request handling mode for secret retrieval."""
    CACHE_THEN_REMOTE = "cache_then_remote"
    FORCE_REMOTE = "force_remote"
    CACHE_ONLY = "cache_only"


class SecretClient:
    """A client for communicating with the orchestrator's secret provider.
    
    This client handles secret caching, rotation notifications, and provides
    both raw and typed secret access methods.
    """
    
    def __init__(self, orchestrator_api: str, module_id: str) -> None:
        """Initialize the secret client.
        
        Args:
            orchestrator_api: URL of the orchestrator API
            module_id: ID of the module requesting secrets
        """
        self.orchestrator_api = orchestrator_api
        self.module_id = module_id
        
        # Cache for secrets
        self._cache: Dict[str, SecretString] = {}
        self._cache_lock = asyncio.Lock()
        
        # Rotation tracking
        self._rotation_tracking: Dict[str, str] = {}
        self._last_ack: Optional[str] = None
        
        # Rotation subscribers
        self._rotation_subscribers: List[Callable[[List[str]], Awaitable[None]]] = []
        
        # Pending secret requests
        self._pending_requests: Dict[str, asyncio.Future[SecretString]] = {}
        self._pending_lock = asyncio.Lock()
    
    async def get_secret(
        self,
        key: str,
        mode: RequestMode = RequestMode.CACHE_THEN_REMOTE,
    ) -> SecretString:
        """Get a secret value with caching based on mode.
        
        Args:
            key: The secret key to retrieve
            mode: How to handle caching for this request
            
        Returns:
            The secret value wrapped in a SecretString
            
        Raises:
            SecretError: If the secret cannot be retrieved
        """
        async with self._cache_lock:
            # Check cache first if not forcing remote
            if mode != RequestMode.FORCE_REMOTE:
                if key in self._cache:
                    debug(f"Found secret '{key}' in cache")
                    return self._cache[key]
                elif mode == RequestMode.CACHE_ONLY:
                    raise SecretError(f"secret '{key}' not found in cache")
            
            # Check if there's already a pending request for this key
            async with self._pending_lock:
                if key in self._pending_requests:
                    debug(f"Waiting for pending request for secret '{key}'")
                    return await self._pending_requests[key]
                
                # Create a future for this request
                future = asyncio.Future()
                self._pending_requests[key] = future
            
            try:
                # Request from orchestrator
                debug(f"Requesting secret '{key}' from orchestrator")
                send_get_secret_request(key)
                
                # Wait for the response (with timeout)
                try:
                    secret = await asyncio.wait_for(future, timeout=30.0)
                    
                    # Cache the secret
                    self._cache[key] = secret
                    
                    return secret
                    
                except asyncio.TimeoutError:
                    raise SecretError(f"timeout waiting for secret '{key}' from orchestrator")
                
            finally:
                # Clean up pending request
                async with self._pending_lock:
                    self._pending_requests.pop(key, None)
    
    async def get_secrets(self, keys: List[str]) -> List[SecretString]:
        """Get multiple secrets efficiently.
        
        Args:
            keys: List of secret keys to retrieve
            
        Returns:
            List of secret values in the same order as keys
        """
        # For now, request them individually
        # In Phase 2, we could implement batch requests
        secrets = []
        for key in keys:
            secret = await self.get_secret(key)
            secrets.append(secret)
        return secrets
    
    async def process_secret_message(self, message: SecretValueResponse) -> None:
        """Process a secret message from the orchestrator.
        
        Args:
            message: The secret response message
        """
        debug(f"Processing secret message for key: {message.name}")
        
        # Create secret and register for redaction
        secret = SecretString(message.value)
        register_secret_for_redaction(message.value)
        
        # Update cache
        async with self._cache_lock:
            self._cache[message.name] = secret
        
        # Track rotation if present
        if message.rotation_id:
            self._rotation_tracking[message.name] = message.rotation_id
        
        # Resolve any pending requests
        async with self._pending_lock:
            if message.name in self._pending_requests:
                future = self._pending_requests[message.name]
                if not future.done():
                    future.set_result(secret)
    
    async def process_rotation_message(self, message: RotatedNotification) -> None:
        """Process a rotation notification from the orchestrator.
        
        Args:
            message: The rotation notification message
        """
        info(f"Processing rotation notification for {len(message.keys)} keys with ID {message.rotation_id}")
        
        # Invalidate cache for rotated keys
        async with self._cache_lock:
            for key in message.keys:
                self._cache.pop(key, None)
        
        # Notify subscribers
        for subscriber in self._rotation_subscribers:
            try:
                await subscriber(message.keys)
            except Exception as e:
                error(f"Error in rotation subscriber: {e}")
        
        # Auto-acknowledge the rotation
        try:
            send_rotation_ack(message.rotation_id, "success")
            self._last_ack = message.rotation_id
        except Exception as e:
            error(f"Failed to acknowledge rotation {message.rotation_id}: {e}")
            send_rotation_ack(message.rotation_id, "error", str(e))
    
    def subscribe_to_rotations(self, callback: Callable[[List[str]], Awaitable[None]]) -> None:
        """Subscribe to rotation events.
        
        Args:
            callback: Function to call when secrets are rotated
        """
        self._rotation_subscribers.append(callback)
    
    async def acknowledge_rotation(self, rotation_id: str, status: str = "success", message: Optional[str] = None) -> None:
        """Manually acknowledge a rotation.
        
        Args:
            rotation_id: ID of the rotation to acknowledge
            status: Status of the rotation processing
            message: Optional message
        """
        try:
            send_rotation_ack(rotation_id, status, message)
            self._last_ack = rotation_id
        except Exception as e:
            raise SecretError(f"failed to acknowledge rotation {rotation_id}: {e}")
    
    # Convenience methods for typed secrets
    
    async def get_typed(self, key: str, target_type: type) -> Secret[Any]:
        """Get a secret and parse it to the specified type.
        
        Args:
            key: The secret key to retrieve
            target_type: The type to parse the secret value to
            
        Returns:
            A Secret wrapper containing the parsed value
        """
        from .typed_secret import get_typed_secret
        return await get_typed_secret(self, key, target_type)
    
    async def get_string(self, key: str) -> Secret[str]:
        """Get a secret as a string.
        
        Args:
            key: The secret key to retrieve
            
        Returns:
            A Secret wrapper containing the string value
        """
        from .typed_secret import get_string_secret
        return await get_string_secret(self, key)
    
    async def get_bool(self, key: str) -> Secret[bool]:
        """Get a secret as a boolean.
        
        Args:
            key: The secret key to retrieve
            
        Returns:
            A Secret wrapper containing the boolean value
        """
        from .typed_secret import get_bool_secret
        return await get_bool_secret(self, key)
    
    async def get_int(self, key: str) -> Secret[int]:
        """Get a secret as an integer.
        
        Args:
            key: The secret key to retrieve
            
        Returns:
            A Secret wrapper containing the integer value
        """
        from .typed_secret import get_int_secret
        return await get_int_secret(self, key)
    
    async def get_float(self, key: str) -> Secret[float]:
        """Get a secret as a float.
        
        Args:
            key: The secret key to retrieve
            
        Returns:
            A Secret wrapper containing the float value
        """
        from .typed_secret import get_float_secret
        return await get_float_secret(self, key)
    
    async def _handle_secret_update(self, message: SecretValueResponse) -> None:
        """Handle secret update from orchestrator.
        
        Args:
            message: The secret update message
        """
        await self.process_secret_message(message)
    
    async def _handle_secret_rotation(self, message: RotatedNotification) -> None:
        """Handle secret rotation from orchestrator.
        
        Args:
            message: The rotation notification message
        """
        await self.process_rotation_message(message)
    
    def __repr__(self) -> str:
        """String representation of the SecretClient."""
        return (
            f"SecretClient(module_id='{self.module_id}', "
            f"cache_size={len(self._cache)}, "
            f"subscribers={len(self._rotation_subscribers)})"
        )


# Global client instance (optional, for convenience)
_global_client: Optional[SecretClient] = None


async def get_module_secret_client(orchestrator_api: str, module_id: str) -> SecretClient:
    """Get a secret client for the module.
    
    Args:
        orchestrator_api: URL of the orchestrator API
        module_id: ID of the module
        
    Returns:
        A configured SecretClient instance
    """
    global _global_client
    
    if _global_client is None:
        _global_client = SecretClient(orchestrator_api, module_id)
        info(f"Created secret client for module {module_id}")
    
    return _global_client


async def get_secret(key: str, mode: RequestMode = RequestMode.CACHE_THEN_REMOTE) -> SecretString:
    """Get a secret using the global client.
    
    Args:
        key: The secret key to retrieve
        mode: How to handle caching for this request
        
    Returns:
        The secret value
        
    Raises:
        SecretError: If no global client is available or secret cannot be retrieved
    """
    if _global_client is None:
        raise SecretError("no global secret client available - call get_module_secret_client first")
    
    return await _global_client.get_secret(key, mode)


async def get_secrets(keys: List[str]) -> List[SecretString]:
    """Get multiple secrets using the global client.
    
    Args:
        keys: List of secret keys to retrieve
        
    Returns:
        List of secret values
        
    Raises:
        SecretError: If no global client is available or secrets cannot be retrieved
    """
    if _global_client is None:
        raise SecretError("no global secret client available - call get_module_secret_client first")
    
    return await _global_client.get_secrets(keys)


async def subscribe_secret_rotations(
    client: SecretClient,
    keys: List[str],
    callback: Callable[[str, str], Awaitable[None]],
) -> None:
    """Subscribe to secret rotation events.
    
    Args:
        client: The secret client to use
        keys: List of secret keys to monitor (for filtering)
        callback: Function to call when monitored secrets are rotated
    """
    async def filtered_callback(rotated_keys: List[str]) -> None:
        """Filter rotation events to only monitored keys."""
        for key in rotated_keys:
            if key in keys:
                # Get the new secret value
                try:
                    new_secret = await client.get_secret(key, RequestMode.FORCE_REMOTE)
                    await callback(key, new_secret.expose_secret())
                except Exception as e:
                    error(f"Error handling rotation for key {key}: {e}")
    
    client.subscribe_to_rotations(filtered_callback)


def get_global_secret_client() -> Optional[SecretClient]:
    """Get the global secret client instance.
    
    Returns:
        The global secret client or None if not initialized
    """
    return _global_client 