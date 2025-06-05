"""
Cache abstraction layer for PyWatt Python SDK.

This module provides a unified interface for cache operations across different
cache types (in-memory, Redis, Memcached) with support for proxy caching
through the orchestrator.
"""

import asyncio
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..core.error import PyWattSDKError


class CacheType(Enum):
    """Cache implementation types."""
    IN_MEMORY = "in_memory"
    REDIS = "redis"
    MEMCACHED = "memcached"
    FILE = "file"


class CachePolicy(Enum):
    """Cache eviction policies."""
    LRU = "lru"  # Least Recently Used
    FIFO = "fifo"  # First In First Out
    MRU = "mru"  # Most Recently Used
    LFU = "lfu"  # Least Frequently Used
    NONE = "none"  # No eviction


@dataclass
class CacheStats:
    """Cache statistics."""
    hits: Optional[int] = None
    misses: Optional[int] = None
    sets: Optional[int] = None
    deletes: Optional[int] = None
    item_count: Optional[int] = None
    memory_used_bytes: Optional[int] = None
    additional_metrics: Dict[str, str] = field(default_factory=dict)


@dataclass
class CacheConfig:
    """Cache configuration."""
    cache_type: CacheType = CacheType.IN_MEMORY
    policy: CachePolicy = CachePolicy.LRU
    max_size_bytes: Optional[int] = 10 * 1024 * 1024  # 10 MB
    default_ttl_seconds: int = 300  # 5 minutes
    
    # Connection parameters
    hosts: List[str] = field(default_factory=lambda: ["localhost"])
    port: Optional[int] = None
    connection_timeout_seconds: int = 5
    operation_timeout_seconds: int = 2
    
    # Authentication & security
    username: Optional[str] = None
    password: Optional[str] = None
    tls_enabled: bool = False
    
    # Backend-specific options
    database: Optional[int] = None  # Redis database number
    file_path: Optional[str] = None  # File cache path
    namespace: Optional[str] = None  # Key namespace/prefix
    
    # Additional parameters
    extra_params: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def in_memory(cls, max_size_mb: int = 10, ttl_seconds: int = 300) -> 'CacheConfig':
        """Create in-memory cache configuration."""
        return cls(
            cache_type=CacheType.IN_MEMORY,
            max_size_bytes=max_size_mb * 1024 * 1024,
            default_ttl_seconds=ttl_seconds
        )
    
    @classmethod
    def redis(cls, host: str = "localhost", port: int = 6379, database: int = 0) -> 'CacheConfig':
        """Create Redis cache configuration."""
        return cls(
            cache_type=CacheType.REDIS,
            hosts=[host],
            port=port,
            database=database
        )
    
    @classmethod
    def memcached(cls, host: str = "localhost", port: int = 11211) -> 'CacheConfig':
        """Create Memcached cache configuration."""
        return cls(
            cache_type=CacheType.MEMCACHED,
            hosts=[host],
            port=port
        )
    
    @classmethod
    def file_cache(cls, file_path: str, max_size_mb: int = 100) -> 'CacheConfig':
        """Create file cache configuration."""
        return cls(
            cache_type=CacheType.FILE,
            file_path=file_path,
            max_size_bytes=max_size_mb * 1024 * 1024
        )


class CacheError(PyWattSDKError):
    """Base class for cache-related errors."""
    pass


class ConnectionError(CacheError):
    """Cache connection error."""
    pass


class SetError(CacheError):
    """Cache set operation error."""
    pass


class GetError(CacheError):
    """Cache get operation error."""
    pass


class DeleteError(CacheError):
    """Cache delete operation error."""
    pass


class FlushError(CacheError):
    """Cache flush operation error."""
    pass


class ConfigurationError(CacheError):
    """Cache configuration error."""
    pass


class SerializationError(CacheError):
    """Cache serialization/deserialization error."""
    pass


class IpcError(CacheError):
    """Cache IPC error."""
    pass


class OperationError(CacheError):
    """Cache operation error."""
    pass


class InternalError(CacheError):
    """Internal SDK implementation error."""
    pass


class CacheService(ABC):
    """Cache service interface."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[bytes]:
        """Get a value from the cache."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: bytes, ttl: Optional[float] = None) -> None:
        """Set a value in the cache."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a value from the cache."""
        pass
    
    @abstractmethod
    async def flush(self) -> None:
        """Delete all values from the cache."""
        pass
    
    @abstractmethod
    async def stats(self) -> CacheStats:
        """Get cache statistics."""
        pass
    
    @abstractmethod
    async def ping(self) -> None:
        """Ping the cache service."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the connection (if applicable)."""
        pass
    
    # Extended operations with default implementations
    async def exists(self, key: str) -> bool:
        """Check if a key exists without fetching its value."""
        result = await self.get(key)
        return result is not None
    
    async def set_nx(self, key: str, value: bytes, ttl: Optional[float] = None) -> bool:
        """Set a value only if the key does not already exist (NX)."""
        if await self.exists(key):
            return False
        await self.set(key, value, ttl)
        return True
    
    async def get_set(self, key: str, value: bytes) -> Optional[bytes]:
        """Atomically fetch the current value and replace it."""
        old_value = await self.get(key)
        await self.set(key, value, None)
        return old_value
    
    async def increment(self, key: str, delta: int = 1) -> int:
        """Increment a numeric value."""
        current_bytes = await self.get(key)
        if current_bytes is None:
            current_value = 0
        else:
            try:
                current_value = int(current_bytes.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                raise OperationError(f"Cannot increment non-numeric value for key '{key}'")
        
        new_value = current_value + delta
        await self.set(key, str(new_value).encode('utf-8'), None)
        return new_value
    
    async def decrement(self, key: str, delta: int = 1) -> int:
        """Decrement a numeric value."""
        return await self.increment(key, -delta)
    
    async def set_many(self, items: Dict[str, bytes], ttl: Optional[float] = None) -> None:
        """Set multiple key/value pairs in a single operation."""
        for key, value in items.items():
            await self.set(key, value, ttl)
    
    async def get_many(self, keys: List[str]) -> Dict[str, bytes]:
        """Fetch many keys at once."""
        result = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value
        return result
    
    async def delete_many(self, keys: List[str]) -> int:
        """Delete many keys at once."""
        count = 0
        for key in keys:
            if await self.delete(key):
                count += 1
        return count
    
    async def clear(self, namespace: Optional[str] = None) -> None:
        """Clear the cache or a namespace."""
        if namespace is None:
            await self.flush()
        else:
            raise OperationError("Namespace-specific clear not implemented for this backend")
    
    async def lock(self, key: str, ttl: float) -> Optional[str]:
        """Acquire a simple lock."""
        import uuid
        lock_key = f"lock:{key}"
        token = str(uuid.uuid4())
        
        if await self.set_nx(lock_key, token.encode('utf-8'), ttl):
            return token
        return None
    
    async def unlock(self, key: str, token: str) -> bool:
        """Release a lock."""
        lock_key = f"lock:{key}"
        
        stored_token_bytes = await self.get(lock_key)
        if stored_token_bytes is None:
            return False
        
        try:
            stored_token = stored_token_bytes.decode('utf-8')
            if stored_token == token:
                await self.delete(lock_key)
                return True
        except UnicodeDecodeError:
            pass
        
        return False
    
    def get_cache_type(self) -> CacheType:
        """Get the cache type."""
        return CacheType.IN_MEMORY
    
    def get_default_ttl(self) -> float:
        """Get the default TTL."""
        return 0.0
    
    async def get_string(self, key: str) -> Optional[str]:
        """Get a value as UTF-8 string."""
        value = await self.get(key)
        if value is None:
            return None
        try:
            return value.decode('utf-8')
        except UnicodeDecodeError:
            raise GetError(f"Value for key '{key}' is not valid UTF-8")
    
    async def set_string(self, key: str, value: str, ttl: Optional[float] = None) -> None:
        """Set a value as UTF-8 string."""
        await self.set(key, value.encode('utf-8'), ttl)


class InMemoryCache(CacheService):
    """In-memory cache implementation."""
    
    def __init__(self, config: CacheConfig):
        self.config = config
        self._cache: Dict[str, tuple] = {}  # key -> (value, expiry_time)
        self._stats = CacheStats(hits=0, misses=0, sets=0, deletes=0)
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get a value from the cache."""
        async with self._lock:
            if key not in self._cache:
                self._stats.misses = (self._stats.misses or 0) + 1
                return None
            
            value, expiry_time = self._cache[key]
            
            # Check if expired
            if expiry_time is not None and time.time() > expiry_time:
                del self._cache[key]
                self._stats.misses = (self._stats.misses or 0) + 1
                return None
            
            self._stats.hits = (self._stats.hits or 0) + 1
            return value
    
    async def set(self, key: str, value: bytes, ttl: Optional[float] = None) -> None:
        """Set a value in the cache."""
        async with self._lock:
            if ttl is None:
                ttl = self.config.default_ttl_seconds
            
            expiry_time = None
            if ttl > 0:
                expiry_time = time.time() + ttl
            
            self._cache[key] = (value, expiry_time)
            self._stats.sets = (self._stats.sets or 0) + 1
            
            # Simple size-based eviction (if configured)
            await self._evict_if_needed()
    
    async def delete(self, key: str) -> bool:
        """Delete a value from the cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats.deletes = (self._stats.deletes or 0) + 1
                return True
            return False
    
    async def flush(self) -> None:
        """Delete all values from the cache."""
        async with self._lock:
            self._cache.clear()
    
    async def stats(self) -> CacheStats:
        """Get cache statistics."""
        async with self._lock:
            self._stats.item_count = len(self._cache)
            # Estimate memory usage
            memory_used = sum(len(k.encode('utf-8')) + len(v[0]) for k, v in self._cache.items())
            self._stats.memory_used_bytes = memory_used
            return self._stats
    
    async def ping(self) -> None:
        """Ping the cache service."""
        # In-memory cache is always available
        pass
    
    async def close(self) -> None:
        """Close the connection."""
        # Nothing to close for in-memory cache
        pass
    
    async def _evict_if_needed(self) -> None:
        """Evict items if cache is too large."""
        if self.config.max_size_bytes is None:
            return
        
        # Calculate current size
        current_size = sum(len(k.encode('utf-8')) + len(v[0]) for k, v in self._cache.items())
        
        if current_size <= self.config.max_size_bytes:
            return
        
        # Implement eviction based on configured policy
        if self.config.policy == CachePolicy.FIFO:
            # First In First Out - remove oldest entries
            keys_to_remove = list(self._cache.keys())[:len(self._cache) // 4]  # Remove 25%
            for key in keys_to_remove:
                if key in self._cache:
                    del self._cache[key]
        elif self.config.policy == CachePolicy.LRU:
            # Least Recently Used - for simplicity, use FIFO approximation
            # In a production implementation, this would track access times
            keys_to_remove = list(self._cache.keys())[:len(self._cache) // 4]
            for key in keys_to_remove:
                if key in self._cache:
                    del self._cache[key]
        else:
            # Default to FIFO for other policies
            keys_to_remove = list(self._cache.keys())[:len(self._cache) // 4]
            for key in keys_to_remove:
                if key in self._cache:
                    del self._cache[key]
    
    def get_cache_type(self) -> CacheType:
        """Get the cache type."""
        return CacheType.IN_MEMORY
    
    def get_default_ttl(self) -> float:
        """Get the default TTL."""
        return float(self.config.default_ttl_seconds)


class ProxyCacheService(CacheService):
    """Cache service that proxies operations through the orchestrator."""
    
    def __init__(self, config: CacheConfig, connection_id: str):
        self.config = config
        self.connection_id = connection_id
    
    @classmethod
    async def connect(cls, config: CacheConfig) -> 'ProxyCacheService':
        """Create a proxy cache service."""
        from ..communication.ipc_types import ServiceRequest, ServiceType
        from ..communication.ipc import send_ipc_message
        import uuid
        
        # Create a unique ID for this connection request
        request_id = f"cache_request_{uuid.uuid4()}"
        
        # Create a service request
        request = ServiceRequest(
            id=request_id,
            service_type=ServiceType.CACHE,
            config=config.__dict__
        )
        
        # Send the request to the orchestrator
        try:
            response = await send_ipc_message(request)
            
            # Parse the response
            if not response.get("success", False):
                raise ConnectionError(f"Failed to connect to cache: {response.get('error', 'Unknown error')}")
            
            connection_id = response.get("connection_id")
            if not connection_id:
                raise ConnectionError("No connection ID returned from orchestrator")
            
            return cls(config, connection_id)
            
        except Exception as e:
            raise ConnectionError(f"Failed to establish proxy cache connection: {e}")
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get a value via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.CACHE,
            operation="get",
            params={"key": key}
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise GetError(f"Cache get failed: {result.get('error', 'Unknown error')}")
            
            value = result.get("result")
            if value is None:
                return None
            
            # Decode base64 if it's a string
            if isinstance(value, str):
                import base64
                try:
                    return base64.b64decode(value)
                except Exception:
                    raise GetError(f"Invalid base64 value for key '{key}'")
            elif isinstance(value, bytes):
                return value
            else:
                return str(value).encode('utf-8')
                
        except Exception as e:
            raise GetError(f"Failed to get value via proxy: {e}")
    
    async def set(self, key: str, value: bytes, ttl: Optional[float] = None) -> None:
        """Set a value via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        import base64
        
        # Encode value as base64 for transmission
        encoded_value = base64.b64encode(value).decode('utf-8')
        
        params = {
            "key": key,
            "value": encoded_value
        }
        
        if ttl is not None:
            params["ttl"] = ttl
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.CACHE,
            operation="set",
            params=params
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise SetError(f"Cache set failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            raise SetError(f"Failed to set value via proxy: {e}")
    
    async def delete(self, key: str) -> bool:
        """Delete a value via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.CACHE,
            operation="delete",
            params={"key": key}
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise DeleteError(f"Cache delete failed: {result.get('error', 'Unknown error')}")
            
            return result.get("result", False)
                
        except Exception as e:
            raise DeleteError(f"Failed to delete value via proxy: {e}")
    
    async def flush(self) -> None:
        """Flush via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.CACHE,
            operation="flush",
            params={}
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise FlushError(f"Cache flush failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            raise FlushError(f"Failed to flush cache via proxy: {e}")
    
    async def stats(self) -> CacheStats:
        """Get stats via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.CACHE,
            operation="stats",
            params={}
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                return CacheStats()  # Return empty stats on error
            
            stats_data = result.get("result", {})
            return CacheStats(
                hits=stats_data.get("hits"),
                misses=stats_data.get("misses"),
                sets=stats_data.get("sets"),
                deletes=stats_data.get("deletes"),
                item_count=stats_data.get("item_count"),
                memory_used_bytes=stats_data.get("memory_used_bytes"),
                additional_metrics=stats_data.get("additional_metrics", {})
            )
                
        except Exception:
            return CacheStats()  # Return empty stats on error
    
    async def ping(self) -> None:
        """Ping via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.CACHE,
            operation="ping",
            params={}
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise ConnectionError(f"Cache ping failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            raise ConnectionError(f"Failed to ping cache via proxy: {e}")
    
    async def close(self) -> None:
        """Close the proxy connection."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.CACHE,
            operation="close",
            params={}
        )
        
        try:
            await send_ipc_message(operation)
        except:
            pass  # Ignore close errors
    
    def get_cache_type(self) -> CacheType:
        """Get the cache type."""
        return self.config.cache_type
    
    def get_default_ttl(self) -> float:
        """Get the default TTL."""
        return float(self.config.default_ttl_seconds)


def _is_running_as_module() -> bool:
    """Check if running as a module under orchestrator."""
    return os.getenv("PYWATT_MODULE_ID") is not None


async def create_cache_service(config: CacheConfig) -> CacheService:
    """Create a cache service based on configuration."""
    # Check if we're running as a module (under orchestrator)
    if _is_running_as_module():
        # Create an IPC-based proxy service
        return await ProxyCacheService.connect(config)
    
    # If not running as a module, use direct connections
    if config.cache_type == CacheType.IN_MEMORY:
        return InMemoryCache(config)
    elif config.cache_type == CacheType.REDIS:
        try:
            from .redis_cache import RedisCache
            return await RedisCache.connect(config)
        except ImportError:
            raise ConfigurationError(
                "Redis cache support requires redis. Install with: pip install redis"
            )
    elif config.cache_type == CacheType.MEMCACHED:
        try:
            from .memcached_cache import MemcachedCache
            return await MemcachedCache.connect(config)
        except ImportError:
            raise ConfigurationError(
                "Memcached cache support requires aiomcache. Install with: pip install aiomcache"
            )
    elif config.cache_type == CacheType.FILE:
        # File cache is not implemented in this version
        # Users should use in-memory, Redis, or Memcached instead
        raise ConfigurationError("File cache support not implemented. Use in-memory, Redis, or Memcached instead.")
    else:
        raise ConfigurationError(f"Unsupported cache type: {config.cache_type}") 