"""
Memcached cache implementation for PyWatt Python SDK.

This module provides a Memcached-specific implementation of the CacheService
interface using aiomcache for async Memcached operations.
"""

import asyncio
import logging
from typing import Dict, List, Optional

import aiomcache

from .cache import (
    CacheService, CacheConfig, CacheType, CacheStats,
    CacheError, ConnectionError, SetError, GetError,
    DeleteError, FlushError, ConfigurationError, OperationError
)

logger = logging.getLogger(__name__)


class MemcachedCache(CacheService):
    """Memcached cache implementation."""
    
    def __init__(self, client: aiomcache.Client, config: CacheConfig):
        self.client = client
        self.config = config
        self._namespace = config.namespace or ""
    
    @classmethod
    async def connect(cls, config: CacheConfig) -> 'MemcachedCache':
        """Create a Memcached cache connection from configuration."""
        try:
            # Build connection parameters
            host = config.hosts[0] if config.hosts else "localhost"
            port = config.port or 11211
            
            # Create Memcached client
            client = aiomcache.Client(
                host=host,
                port=port,
                pool_size=10,
                pool_minsize=1,
            )
            
            # Test connection by getting stats
            try:
                await client.stats()
            except Exception as e:
                raise ConnectionError(f"Failed to connect to Memcached: {e}")
            
            return cls(client, config)
        except Exception as e:
            raise ConnectionError(f"Failed to create Memcached connection: {e}")
    
    def _make_key(self, key: str) -> bytes:
        """Add namespace prefix to key and convert to bytes."""
        if self._namespace:
            full_key = f"{self._namespace}:{key}"
        else:
            full_key = key
        
        # Memcached keys must be bytes and have length restrictions
        key_bytes = full_key.encode('utf-8')
        if len(key_bytes) > 250:
            # Hash long keys to fit Memcached's 250 byte limit
            import hashlib
            hash_key = hashlib.sha256(key_bytes).hexdigest()
            if self._namespace:
                key_bytes = f"{self._namespace}:hash:{hash_key}".encode('utf-8')
            else:
                key_bytes = f"hash:{hash_key}".encode('utf-8')
        
        return key_bytes
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get a value from Memcached."""
        try:
            memcached_key = self._make_key(key)
            value = await self.client.get(memcached_key)
            return value
        except Exception as e:
            raise GetError(f"Failed to get key '{key}': {e}")
    
    async def set(self, key: str, value: bytes, ttl: Optional[float] = None) -> None:
        """Set a value in Memcached."""
        try:
            memcached_key = self._make_key(key)
            
            if ttl is None:
                ttl = self.config.default_ttl_seconds
            
            # Memcached expects exptime as int (0 means no expiration)
            exptime = int(ttl) if ttl > 0 else 0
            
            await self.client.set(memcached_key, value, exptime=exptime)
        except Exception as e:
            raise SetError(f"Failed to set key '{key}': {e}")
    
    async def delete(self, key: str) -> bool:
        """Delete a value from Memcached."""
        try:
            memcached_key = self._make_key(key)
            result = await self.client.delete(memcached_key)
            return result
        except Exception as e:
            raise DeleteError(f"Failed to delete key '{key}': {e}")
    
    async def flush(self) -> None:
        """Delete all values from Memcached."""
        try:
            await self.client.flush_all()
        except Exception as e:
            raise FlushError(f"Failed to flush cache: {e}")
    
    async def stats(self) -> CacheStats:
        """Get Memcached statistics."""
        try:
            stats_data = await self.client.stats()
            
            # Parse stats (aiomcache returns dict-like stats)
            stats = CacheStats(
                hits=int(stats_data.get(b'get_hits', 0)),
                misses=int(stats_data.get(b'get_misses', 0)),
                item_count=int(stats_data.get(b'curr_items', 0)),
                memory_used_bytes=int(stats_data.get(b'bytes', 0)),
                additional_metrics={
                    'version': stats_data.get(b'version', b'').decode('utf-8'),
                    'uptime': str(stats_data.get(b'uptime', 0)),
                    'curr_connections': str(stats_data.get(b'curr_connections', 0)),
                    'total_connections': str(stats_data.get(b'total_connections', 0)),
                    'cmd_get': str(stats_data.get(b'cmd_get', 0)),
                    'cmd_set': str(stats_data.get(b'cmd_set', 0)),
                }
            )
            
            return stats
        except Exception as e:
            logger.warning(f"Failed to get Memcached stats: {e}")
            return CacheStats()
    
    async def ping(self) -> None:
        """Ping Memcached by getting stats."""
        try:
            await self.client.stats()
        except Exception as e:
            raise ConnectionError(f"Failed to ping Memcached: {e}")
    
    async def close(self) -> None:
        """Close Memcached connection."""
        try:
            await self.client.close()
        except Exception as e:
            logger.warning(f"Error closing Memcached connection: {e}")
    
    # Memcached-specific operations
    
    async def set_nx(self, key: str, value: bytes, ttl: Optional[float] = None) -> bool:
        """Set a value only if the key does not exist using Memcached ADD."""
        try:
            memcached_key = self._make_key(key)
            
            if ttl is None:
                ttl = self.config.default_ttl_seconds
            
            exptime = int(ttl) if ttl > 0 else 0
            
            # Use ADD command which only sets if key doesn't exist
            result = await self.client.add(memcached_key, value, exptime=exptime)
            return result
        except Exception as e:
            raise SetError(f"Failed to set key '{key}' with NX: {e}")
    
    async def increment(self, key: str, delta: int = 1) -> int:
        """Increment using Memcached INCR."""
        try:
            memcached_key = self._make_key(key)
            
            # Try to increment
            try:
                result = await self.client.incr(memcached_key, delta)
                return result
            except Exception:
                # Key doesn't exist or isn't numeric, set it to delta
                await self.client.set(memcached_key, str(delta).encode('utf-8'))
                return delta
        except Exception as e:
            raise OperationError(f"Failed to increment key '{key}': {e}")
    
    async def decrement(self, key: str, delta: int = 1) -> int:
        """Decrement using Memcached DECR."""
        try:
            memcached_key = self._make_key(key)
            
            # Try to decrement
            try:
                result = await self.client.decr(memcached_key, delta)
                return result
            except Exception:
                # Key doesn't exist or isn't numeric, set it to -delta (or 0 if negative)
                new_value = max(0, -delta)
                await self.client.set(memcached_key, str(new_value).encode('utf-8'))
                return new_value
        except Exception as e:
            raise OperationError(f"Failed to decrement key '{key}': {e}")
    
    async def set_many(self, items: Dict[str, bytes], ttl: Optional[float] = None) -> None:
        """Set multiple values (Memcached doesn't have native multi-set, so we use individual sets)."""
        try:
            if not items:
                return
            
            if ttl is None:
                ttl = self.config.default_ttl_seconds
            
            exptime = int(ttl) if ttl > 0 else 0
            
            # Execute sets concurrently
            tasks = []
            for key, value in items.items():
                memcached_key = self._make_key(key)
                task = self.client.set(memcached_key, value, exptime=exptime)
                tasks.append(task)
            
            await asyncio.gather(*tasks)
        except Exception as e:
            raise SetError(f"Failed to set multiple keys: {e}")
    
    async def get_many(self, keys: List[str]) -> Dict[str, bytes]:
        """Get multiple values using Memcached multi-get."""
        try:
            if not keys:
                return {}
            
            memcached_keys = [self._make_key(key) for key in keys]
            
            # Use multi-get
            values = await self.client.multi_get(*memcached_keys)
            
            # Map back to original keys
            result = {}
            for i, key in enumerate(keys):
                memcached_key = memcached_keys[i]
                if memcached_key in values and values[memcached_key] is not None:
                    result[key] = values[memcached_key]
            
            return result
        except Exception as e:
            raise GetError(f"Failed to get multiple keys: {e}")
    
    async def delete_many(self, keys: List[str]) -> int:
        """Delete multiple keys (Memcached doesn't have native multi-delete)."""
        try:
            if not keys:
                return 0
            
            # Execute deletes concurrently
            tasks = []
            for key in keys:
                memcached_key = self._make_key(key)
                task = self.client.delete(memcached_key)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successful deletes
            count = 0
            for result in results:
                if not isinstance(result, Exception) and result:
                    count += 1
            
            return count
        except Exception as e:
            raise DeleteError(f"Failed to delete multiple keys: {e}")
    
    async def clear(self, namespace: Optional[str] = None) -> None:
        """Clear cache (Memcached doesn't support namespace-specific clearing)."""
        try:
            if namespace and namespace != self._namespace:
                raise OperationError(
                    "Memcached doesn't support namespace-specific clearing. "
                    "Use flush() to clear entire cache."
                )
            
            await self.client.flush_all()
        except Exception as e:
            raise FlushError(f"Failed to clear cache: {e}")
    
    async def lock(self, key: str, ttl: float) -> Optional[str]:
        """Acquire a simple lock using Memcached ADD."""
        import uuid
        lock_key = f"lock:{key}"
        token = str(uuid.uuid4())
        
        try:
            # Use ADD to atomically acquire lock
            memcached_key = self._make_key(lock_key)
            exptime = int(ttl) if ttl > 0 else 0
            
            result = await self.client.add(memcached_key, token.encode('utf-8'), exptime=exptime)
            return token if result else None
        except Exception as e:
            raise OperationError(f"Failed to acquire lock for key '{key}': {e}")
    
    async def unlock(self, key: str, token: str) -> bool:
        """Release a lock (best effort - Memcached doesn't have atomic compare-and-delete)."""
        lock_key = f"lock:{key}"
        
        try:
            memcached_key = self._make_key(lock_key)
            
            # Get current token
            stored_token_bytes = await self.client.get(memcached_key)
            if stored_token_bytes is None:
                return False
            
            try:
                stored_token = stored_token_bytes.decode('utf-8')
                if stored_token == token:
                    # Delete the lock (not atomic, but best we can do with Memcached)
                    await self.client.delete(memcached_key)
                    return True
            except UnicodeDecodeError:
                pass
            
            return False
        except Exception as e:
            raise OperationError(f"Failed to release lock for key '{key}': {e}")
    
    def get_cache_type(self) -> CacheType:
        """Get the cache type."""
        return CacheType.MEMCACHED
    
    def get_default_ttl(self) -> float:
        """Get the default TTL."""
        return float(self.config.default_ttl_seconds) 