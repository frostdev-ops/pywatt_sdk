"""
Secret Management System

This module provides secret management functionality including:
- Secret retrieval from various sources
- Secret caching and rotation
- Integration with the orchestrator secret service
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable, Awaitable, Union

try:
    from core.error import PyWattSDKError
except ImportError:
    class PyWattSDKError(Exception):
        pass
try:
    from communication.message_channel import MessageChannel
except ImportError:
    MessageChannel = None
try:
    from communication.tcp_channel import TcpChannel
except ImportError:
    TcpChannel = None

logger = logging.getLogger(__name__)

# Secret Error Classes
class SecretError(PyWattSDKError):
    """Base class for secret-related errors."""
    pass

class SecretNotFoundError(SecretError):
    """Raised when a requested secret is not found."""
    pass

class SecretRotationError(SecretError):
    """Raised when secret rotation fails."""
    pass

class SecretProviderError(SecretError):
    """Raised when secret provider operations fail."""
    pass

# Secret Configuration
@dataclass
class SecretConfig:
    """Configuration for secret management."""
    cache_ttl: timedelta = field(default_factory=lambda: timedelta(minutes=15))
    rotation_check_interval: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    max_cache_size: int = 1000
    enable_rotation: bool = True
    orchestrator_endpoint: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'SecretConfig':
        """Create SecretConfig from environment variables."""
        return cls(
            cache_ttl=timedelta(seconds=int(os.getenv("PYWATT_SECRET_CACHE_TTL", "900"))),
            rotation_check_interval=timedelta(seconds=int(os.getenv("PYWATT_SECRET_ROTATION_INTERVAL", "300"))),
            max_cache_size=int(os.getenv("PYWATT_SECRET_MAX_CACHE_SIZE", "1000")),
            enable_rotation=os.getenv("PYWATT_SECRET_ENABLE_ROTATION", "true").lower() == "true",
            orchestrator_endpoint=os.getenv("PYWATT_ORCHESTRATOR_ENDPOINT"),
        )

# Secret Value
@dataclass
class SecretValue:
    """Represents a secret value with metadata."""
    value: str
    key: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    version: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """Check if the secret has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def expose_secret(self) -> str:
        """Expose the secret value (use with caution)."""
        return self.value
    
    def __str__(self) -> str:
        """Return redacted string representation."""
        return f"SecretValue(key='{self.key}', value='[REDACTED]')"
    
    def __repr__(self) -> str:
        """Return redacted string representation."""
        return self.__str__()

# Secret Provider Interface
class SecretProvider(ABC):
    """Abstract base class for secret providers."""
    
    @abstractmethod
    async def get_secret(self, key: str) -> SecretValue:
        """Retrieve a secret by key."""
        pass
    
    @abstractmethod
    async def set_secret(self, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Store a secret."""
        pass
    
    @abstractmethod
    async def delete_secret(self, key: str) -> None:
        """Delete a secret."""
        pass
    
    @abstractmethod
    async def list_keys(self) -> List[str]:
        """List all available secret keys."""
        pass
    
    async def secret_exists(self, key: str) -> bool:
        """Check if a secret exists."""
        try:
            await self.get_secret(key)
            return True
        except SecretNotFoundError:
            return False

# Environment Variable Provider
class EnvironmentSecretProvider(SecretProvider):
    """Secret provider that reads from environment variables."""
    
    def __init__(self, prefix: str = "PYWATT_SECRET_"):
        self.prefix = prefix
    
    async def get_secret(self, key: str) -> SecretValue:
        """Get secret from environment variable."""
        env_key = f"{self.prefix}{key.upper()}"
        value = os.getenv(env_key)
        
        if value is None:
            raise SecretNotFoundError(f"Secret '{key}' not found in environment")
        
        return SecretValue(
            value=value,
            key=key,
            metadata={"source": "environment", "env_key": env_key}
        )
    
    async def set_secret(self, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Set environment variable (not persistent)."""
        env_key = f"{self.prefix}{key.upper()}"
        os.environ[env_key] = value
    
    async def delete_secret(self, key: str) -> None:
        """Delete environment variable."""
        env_key = f"{self.prefix}{key.upper()}"
        if env_key in os.environ:
            del os.environ[env_key]
    
    async def list_keys(self) -> List[str]:
        """List all secret keys from environment."""
        keys = []
        for env_key in os.environ:
            if env_key.startswith(self.prefix):
                key = env_key[len(self.prefix):].lower()
                keys.append(key)
        return keys

# Memory Provider
class MemorySecretProvider(SecretProvider):
    """In-memory secret provider for testing and development."""
    
    def __init__(self):
        self._secrets: Dict[str, SecretValue] = {}
    
    async def get_secret(self, key: str) -> SecretValue:
        """Get secret from memory."""
        if key not in self._secrets:
            raise SecretNotFoundError(f"Secret '{key}' not found in memory")
        
        secret = self._secrets[key]
        if secret.is_expired():
            del self._secrets[key]
            raise SecretNotFoundError(f"Secret '{key}' has expired")
        
        return secret
    
    async def set_secret(self, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Store secret in memory."""
        self._secrets[key] = SecretValue(
            value=value,
            key=key,
            metadata=metadata or {}
        )
    
    async def delete_secret(self, key: str) -> None:
        """Delete secret from memory."""
        if key in self._secrets:
            del self._secrets[key]
    
    async def list_keys(self) -> List[str]:
        """List all secret keys in memory."""
        # Clean up expired secrets
        expired_keys = [k for k, v in self._secrets.items() if v.is_expired()]
        for key in expired_keys:
            del self._secrets[key]
        
        return list(self._secrets.keys())

# Orchestrator Provider
class OrchestratorSecretProvider(SecretProvider):
    """Secret provider that communicates with the orchestrator."""
    
    def __init__(self, channel: MessageChannel):
        self.channel = channel
    
    @classmethod
    async def connect(cls, endpoint: str) -> 'OrchestratorSecretProvider':
        """Connect to the orchestrator secret service."""
        from ..communication.ipc import send_ipc_message
        from ..communication.ipc_types import ServiceRequest, ServiceType
        import uuid
        
        # For modules, we use IPC communication instead of direct TCP
        if _is_running_as_module():
            # Create a dummy channel for IPC-based communication
            return cls(None)
        
        # For standalone mode, parse endpoint and create TCP connection
        if ":" in endpoint:
            host, port_str = endpoint.rsplit(":", 1)
            port = int(port_str)
        else:
            host = endpoint
            port = 9900  # Default orchestrator port
        
        try:
            from ..communication.tcp_channel import TcpChannel, ConnectionConfig
            config = ConnectionConfig(host=host, port=port)
            channel = TcpChannel(config)
            await channel.connect()
            return cls(channel)
        except ImportError:
            # Fall back to IPC if TCP channel not available
            return cls(None)
    
    async def get_secret(self, key: str) -> SecretValue:
        """Get secret from orchestrator."""
        if _is_running_as_module():
            # Use IPC communication for modules
            from ..communication.ipc import send_ipc_message
            from ..communication.ipc_types import ModuleToOrchestrator, GetSecretRequest
            
            try:
                request = GetSecretRequest(name=key)
                message = ModuleToOrchestrator.GetSecret(request)
                
                response = await send_ipc_message(message)
                
                if response.get("success", False):
                    value = response.get("value")
                    if value is not None:
                        return SecretValue(
                            value=value,
                            key=key,
                            metadata={"source": "orchestrator"}
                        )
                
                raise SecretNotFoundError(f"Secret '{key}' not found in orchestrator")
                
            except Exception as e:
                if isinstance(e, SecretNotFoundError):
                    raise
                raise SecretProviderError(f"Failed to get secret from orchestrator: {e}")
        
        elif self.channel is not None:
            # Use TCP communication for standalone mode
            try:
                from ..communication.message import Message
                from ..communication.ipc_types import GetSecretRequest
                
                request = GetSecretRequest(name=key)
                message = Message(content=request)
                
                await self.channel.send(message)
                response_message = await self.channel.receive()
                
                if response_message and hasattr(response_message.content, 'value'):
                    return SecretValue(
                        value=response_message.content.value,
                        key=key,
                        metadata={"source": "orchestrator_tcp"}
                    )
                
                raise SecretNotFoundError(f"Secret '{key}' not found in orchestrator")
                
            except Exception as e:
                if isinstance(e, SecretNotFoundError):
                    raise
                raise SecretProviderError(f"Failed to get secret from orchestrator: {e}")
        
        else:
            # Fall back to environment
            env_provider = EnvironmentSecretProvider()
            return await env_provider.get_secret(key)
    
    async def set_secret(self, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Set secret through orchestrator."""
        if _is_running_as_module():
            # Modules typically don't set secrets directly
            raise SecretProviderError("Setting secrets not supported for modules")
        
        elif self.channel is not None:
            # Use TCP communication for standalone mode
            try:
                from ..communication.message import Message
                
                # Create a set secret request (would need to be defined in IPC types)
                request = {
                    "operation": "set_secret",
                    "key": key,
                    "value": value,
                    "metadata": metadata or {}
                }
                message = Message(content=request)
                
                await self.channel.send(message)
                response_message = await self.channel.receive()
                
                if not response_message or not response_message.content.get("success", False):
                    raise SecretProviderError(f"Failed to set secret '{key}'")
                    
            except Exception as e:
                raise SecretProviderError(f"Failed to set secret in orchestrator: {e}")
        
        else:
            # Fall back to environment (not persistent)
            env_provider = EnvironmentSecretProvider()
            await env_provider.set_secret(key, value, metadata)
    
    async def delete_secret(self, key: str) -> None:
        """Delete secret through orchestrator."""
        if _is_running_as_module():
            # Modules typically don't delete secrets directly
            raise SecretProviderError("Deleting secrets not supported for modules")
        
        elif self.channel is not None:
            # Use TCP communication for standalone mode
            try:
                from ..communication.message import Message
                
                request = {
                    "operation": "delete_secret",
                    "key": key
                }
                message = Message(content=request)
                
                await self.channel.send(message)
                response_message = await self.channel.receive()
                
                if not response_message or not response_message.content.get("success", False):
                    raise SecretProviderError(f"Failed to delete secret '{key}'")
                    
            except Exception as e:
                raise SecretProviderError(f"Failed to delete secret in orchestrator: {e}")
        
        else:
            # Fall back to environment
            env_provider = EnvironmentSecretProvider()
            await env_provider.delete_secret(key)
    
    async def list_keys(self) -> List[str]:
        """List secret keys from orchestrator."""
        if _is_running_as_module():
            # Modules typically don't list all secrets
            return []
        
        elif self.channel is not None:
            # Use TCP communication for standalone mode
            try:
                from ..communication.message import Message
                
                request = {"operation": "list_secrets"}
                message = Message(content=request)
                
                await self.channel.send(message)
                response_message = await self.channel.receive()
                
                if response_message and response_message.content.get("success", False):
                    return response_message.content.get("keys", [])
                
                return []
                    
            except Exception as e:
                logger.warning(f"Failed to list secrets from orchestrator: {e}")
                return []
        
        else:
            # Fall back to environment
            env_provider = EnvironmentSecretProvider()
            return await env_provider.list_keys()

# Secret Cache
class SecretCache:
    """Cache for secret values with TTL support."""
    
    def __init__(self, max_size: int = 1000, default_ttl: timedelta = timedelta(minutes=15)):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, SecretValue] = {}
        self._access_times: Dict[str, datetime] = {}
    
    def get(self, key: str) -> Optional[SecretValue]:
        """Get secret from cache."""
        if key not in self._cache:
            return None
        
        secret = self._cache[key]
        if secret.is_expired():
            self.remove(key)
            return None
        
        self._access_times[key] = datetime.utcnow()
        return secret
    
    def set(self, key: str, secret: SecretValue) -> None:
        """Store secret in cache."""
        # Set expiration if not set
        if secret.expires_at is None:
            secret.expires_at = datetime.utcnow() + self.default_ttl
        
        # Evict if cache is full
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._evict_lru()
        
        self._cache[key] = secret
        self._access_times[key] = datetime.utcnow()
    
    def remove(self, key: str) -> None:
        """Remove secret from cache."""
        self._cache.pop(key, None)
        self._access_times.pop(key, None)
    
    def clear(self) -> None:
        """Clear all cached secrets."""
        self._cache.clear()
        self._access_times.clear()
    
    def _evict_lru(self) -> None:
        """Evict least recently used secret."""
        if not self._access_times:
            return
        
        lru_key = min(self._access_times, key=self._access_times.get)
        self.remove(lru_key)

# Secret Manager
class SecretManager:
    """Main secret management class."""
    
    def __init__(self, config: SecretConfig, provider: SecretProvider):
        self.config = config
        self.provider = provider
        self.cache = SecretCache(config.max_cache_size, config.cache_ttl)
        self._rotation_callbacks: Dict[str, List[Callable[[str, SecretValue], Awaitable[None]]]] = {}
        self._rotation_task: Optional[asyncio.Task] = None
        self._redacted_secrets: set = set()
        
        if config.enable_rotation:
            self._start_rotation_monitoring()
    
    def _start_rotation_monitoring(self) -> None:
        """Start background task for monitoring secret rotation."""
        if self._rotation_task is None or self._rotation_task.done():
            self._rotation_task = asyncio.create_task(self._rotation_monitor())
    
    async def _rotation_monitor(self) -> None:
        """Background task to monitor for secret rotation."""
        while True:
            try:
                await asyncio.sleep(self.config.rotation_check_interval.total_seconds())
                
                # Check for expired secrets in cache
                await self._cleanup_expired_secrets()
                
                # For modules, listen for rotation notifications from orchestrator
                if _is_running_as_module():
                    await self._check_orchestrator_rotations()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in rotation monitor: {e}")
    
    async def _check_orchestrator_rotations(self) -> None:
        """Check for rotation notifications from orchestrator."""
        try:
            # This would typically be handled by the main IPC loop
            # For now, we just refresh any cached secrets that are close to expiring
            current_time = datetime.utcnow()
            refresh_threshold = timedelta(minutes=2)  # Refresh if expiring in 2 minutes
            
            keys_to_refresh = []
            for key, secret in self.cache._cache.items():
                if (secret.expires_at and 
                    secret.expires_at - current_time < refresh_threshold):
                    keys_to_refresh.append(key)
            
            for key in keys_to_refresh:
                try:
                    await self.refresh_secret(key)
                    logger.info(f"Refreshed secret '{key}' due to upcoming expiration")
                except Exception as e:
                    logger.warning(f"Failed to refresh secret '{key}': {e}")
                    
        except Exception as e:
            logger.error(f"Error checking orchestrator rotations: {e}")
    
    async def _cleanup_expired_secrets(self) -> None:
        """Clean up expired secrets from cache."""
        expired_keys = []
        for key, secret in self.cache._cache.items():
            if secret.is_expired():
                expired_keys.append(key)
        
        for key in expired_keys:
            self.cache.remove(key)
    
    async def get_secret(self, key: str, use_cache: bool = True) -> SecretValue:
        """Get a secret value."""
        # Try cache first
        if use_cache:
            cached_secret = self.cache.get(key)
            if cached_secret is not None:
                return cached_secret
        
        # Get from provider
        try:
            secret = await self.provider.get_secret(key)
            
            # Cache the secret
            if use_cache:
                self.cache.set(key, secret)
            
            # Register for redaction
            self.register_for_redaction(secret.value)
            
            return secret
            
        except Exception as e:
            if isinstance(e, SecretError):
                raise
            raise SecretProviderError(f"Failed to get secret '{key}': {e}")
    
    async def set_secret(self, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Set a secret value."""
        await self.provider.set_secret(key, value, metadata)
        
        # Update cache
        secret = SecretValue(value=value, key=key, metadata=metadata or {})
        self.cache.set(key, secret)
        
        # Register for redaction
        self.register_for_redaction(value)
        
        # Notify rotation callbacks
        await self._notify_rotation_callbacks(key, secret)
    
    async def delete_secret(self, key: str) -> None:
        """Delete a secret."""
        await self.provider.delete_secret(key)
        self.cache.remove(key)
    
    async def list_keys(self) -> List[str]:
        """List all available secret keys."""
        return await self.provider.list_keys()
    
    def register_for_redaction(self, secret_value: str) -> None:
        """Register a secret value for redaction in logs."""
        # Store in weak set for memory efficiency
        self._redacted_secrets.add(secret_value)
        
        # Also register globally for log redaction
        _register_global_redaction(secret_value)
    
    def subscribe_to_rotation(self, key: str, callback: Callable[[str, SecretValue], Awaitable[None]]) -> None:
        """Subscribe to secret rotation events."""
        if key not in self._rotation_callbacks:
            self._rotation_callbacks[key] = []
        self._rotation_callbacks[key].append(callback)
    
    async def _notify_rotation_callbacks(self, key: str, new_secret: SecretValue) -> None:
        """Notify callbacks about secret rotation."""
        if key in self._rotation_callbacks:
            for callback in self._rotation_callbacks[key]:
                try:
                    await callback(key, new_secret)
                except Exception as e:
                    logger.error(f"Error in rotation callback for key '{key}': {e}")
    
    async def refresh_secret(self, key: str) -> SecretValue:
        """Force refresh a secret from the provider."""
        self.cache.remove(key)
        return await self.get_secret(key, use_cache=True)
    
    def close(self) -> None:
        """Close the secret manager and cleanup resources."""
        if self._rotation_task and not self._rotation_task.done():
            self._rotation_task.cancel()
        self.cache.clear()

# Factory Functions
def create_secret_manager(config: Optional[SecretConfig] = None) -> SecretManager:
    """Create a SecretManager with appropriate provider."""
    if config is None:
        config = SecretConfig.from_env()
    
    # Determine provider based on environment
    if _is_running_as_module() and config.orchestrator_endpoint:
        # Use orchestrator provider when running as a module
        provider = OrchestratorSecretProvider(None)  # Will be connected later
    else:
        # Use environment provider for standalone mode
        provider = EnvironmentSecretProvider()
    
    return SecretManager(config, provider)

# Global redaction registry
_GLOBAL_REDACTED_SECRETS: set = set()

def _register_global_redaction(secret_value: str) -> None:
    """Register a secret value for global redaction."""
    _GLOBAL_REDACTED_SECRETS.add(secret_value)

def redact_secrets(text: str) -> str:
    """Redact known secrets from text."""
    redacted_text = text
    for secret in _GLOBAL_REDACTED_SECRETS:
        if secret and len(secret) > 3:  # Only redact non-trivial secrets
            redacted_text = redacted_text.replace(secret, "[REDACTED]")
    return redacted_text

class SecretRedactionFilter(logging.Filter):
    """Logging filter that redacts secrets from log messages."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log record to redact secrets."""
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        
        if hasattr(record, 'args') and record.args:
            redacted_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    redacted_args.append(redact_secrets(arg))
                else:
                    redacted_args.append(arg)
            record.args = tuple(redacted_args)
        
        return True

def install_secret_redaction_filter() -> None:
    """Install the secret redaction filter on the root logger."""
    root_logger = logging.getLogger()
    
    # Check if filter is already installed
    for filter_obj in root_logger.filters:
        if isinstance(filter_obj, SecretRedactionFilter):
            return
    
    # Install the filter
    redaction_filter = SecretRedactionFilter()
    root_logger.addFilter(redaction_filter)

def _is_running_as_module() -> bool:
    """Check if running as a PyWatt module."""
    return os.getenv("PYWATT_MODULE_ID") is not None 