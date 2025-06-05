"""
Redis cache implementation for PyWatt Python SDK.

This module provides a Redis-specific implementation of the CacheService
interface using redis-py for async Redis operations.
"""

import asyncio
import logging
from typing import Dict, List, Optional

import redis.asyncio as redis
from redis.asyncio import Redis, ConnectionPool

from .cache import (
    CacheService, CacheConfig, CacheType, CacheStats,
    CacheError, ConnectionError, SetError, GetError,
    DeleteError, FlushError, ConfigurationError, OperationError
)

logger = logging.getLogger(__name__)


class RedisCache(CacheService):
    """Redis cache implementation."""
    
    def __init__(self, client: Redis, config: CacheConfig):
        self.client = client
        self.config = config
        self._namespace = config.namespace or ""
    
    @classmethod
    async def connect(cls, config: CacheConfig) -> 'RedisCache':
        """Create a Redis cache connection from configuration."""
        try:
            # Build connection parameters
            host = config.hosts[0] if config.hosts else "localhost"
            port = config.port or 6379
            database = config.database or 0
            
            # Create connection pool
            pool = ConnectionPool(
                host=host,
                port=port,
                db=database,
                username=config.username,
                password=config.password,
                socket_connect_timeout=config.connection_timeout_seconds,
                socket_timeout=config.operation_timeout_seconds,
                ssl=config.tls_enabled,
                decode_responses=False,  # We handle bytes directly
                max_connections=20,
            )
            
            # Create Redis client
            client = Redis(connection_pool=pool)
            
            # Test connection
            await client.ping()
            
            return cls(client, config)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}")
    
    def _make_key(self, key: str) -> str:
        """Add namespace prefix to key if configured."""
        if self._namespace:
            return f"{self._namespace}:{key}"
        return key
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get a value from Redis."""
        try:
            redis_key = self._make_key(key)
            value = await self.client.get(redis_key)
            return value
        except Exception as e:
            raise GetError(f"Failed to get key '{key}': {e}")
    
    async def set(self, key: str, value: bytes, ttl: Optional[float] = None) -> None:
        """Set a value in Redis."""
        try:
            redis_key = self._make_key(key)
            
            if ttl is None:
                ttl = self.config.default_ttl_seconds
            
            if ttl > 0:
                await self.client.setex(redis_key, int(ttl), value)
            else:
                await self.client.set(redis_key, value)
        except Exception as e:
            raise SetError(f"Failed to set key '{key}': {e}")
    
    async def delete(self, key: str) -> bool:
        """Delete a value from Redis."""
        try:
            redis_key = self._make_key(key)
            result = await self.client.delete(redis_key)
            return result > 0
        except Exception as e:
            raise DeleteError(f"Failed to delete key '{key}': {e}")
    
    async def flush(self) -> None:
        """Delete all values from Redis."""
        try:
            if self._namespace:
                # Delete only keys with our namespace
                pattern = f"{self._namespace}:*"
                keys = await self.client.keys(pattern)
                if keys:
                    await self.client.delete(*keys)
            else:
                # Flush entire database
                await self.client.flushdb()
        except Exception as e:
            raise FlushError(f"Failed to flush cache: {e}")
    
    async def stats(self) -> CacheStats:
        """Get Redis statistics."""
        try:
            info = await self.client.info()
            
            # Extract relevant stats
            stats = CacheStats(
                hits=info.get('keyspace_hits'),
                misses=info.get('keyspace_misses'),
                item_count=info.get('db0', {}).get('keys') if 'db0' in info else None,
                memory_used_bytes=info.get('used_memory'),
                additional_metrics={
                    'redis_version': info.get('redis_version', ''),
                    'connected_clients': str(info.get('connected_clients', 0)),
                    'total_commands_processed': str(info.get('total_commands_processed', 0)),
                    'uptime_in_seconds': str(info.get('uptime_in_seconds', 0)),
                }
            )
            
            return stats
        except Exception as e:
            logger.warning(f"Failed to get Redis stats: {e}")
            return CacheStats()
    
    async def ping(self) -> None:
        """Ping Redis."""
        try:
            await self.client.ping()
        except Exception as e:
            raise ConnectionError(f"Failed to ping Redis: {e}")
    
    async def close(self) -> None:
        """Close Redis connection."""
        try:
            await self.client.close()
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")
    
    # Redis-specific optimized operations
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists using Redis EXISTS command."""
        try:
            redis_key = self._make_key(key)
            result = await self.client.exists(redis_key)
            return result > 0
        except Exception as e:
            raise GetError(f"Failed to check existence of key '{key}': {e}")
    
    async def set_nx(self, key: str, value: bytes, ttl: Optional[float] = None) -> bool:
        """Set a value only if the key does not exist using Redis SETNX."""
        try:
            redis_key = self._make_key(key)
            
            if ttl is None:
                ttl = self.config.default_ttl_seconds
            
            if ttl > 0:
                # Use SET with NX and EX options
                result = await self.client.set(redis_key, value, nx=True, ex=int(ttl))
            else:
                result = await self.client.setnx(redis_key, value)
            
            return result is not None and result
        except Exception as e:
            raise SetError(f"Failed to set key '{key}' with NX: {e}")
    
    async def get_set(self, key: str, value: bytes) -> Optional[bytes]:
        """Atomically get and set using Redis GETSET."""
        try:
            redis_key = self._make_key(key)
            old_value = await self.client.getset(redis_key, value)
            return old_value
        except Exception as e:
            raise OperationError(f"Failed to get-set key '{key}': {e}")
    
    async def increment(self, key: str, delta: int = 1) -> int:
        """Increment using Redis INCRBY."""
        try:
            redis_key = self._make_key(key)
            result = await self.client.incrby(redis_key, delta)
            return result
        except Exception as e:
            raise OperationError(f"Failed to increment key '{key}': {e}")
    
    async def decrement(self, key: str, delta: int = 1) -> int:
        """Decrement using Redis DECRBY."""
        try:
            redis_key = self._make_key(key)
            result = await self.client.decrby(redis_key, delta)
            return result
        except Exception as e:
            raise OperationError(f"Failed to decrement key '{key}': {e}")
    
    async def set_many(self, items: Dict[str, bytes], ttl: Optional[float] = None) -> None:
        """Set multiple values using Redis pipeline."""
        try:
            if not items:
                return
            
            async with self.client.pipeline() as pipe:
                for key, value in items.items():
                    redis_key = self._make_key(key)
                    
                    if ttl is None:
                        ttl = self.config.default_ttl_seconds
                    
                    if ttl > 0:
                        pipe.setex(redis_key, int(ttl), value)
                    else:
                        pipe.set(redis_key, value)
                
                await pipe.execute()
        except Exception as e:
            raise SetError(f"Failed to set multiple keys: {e}")
    
    async def get_many(self, keys: List[str]) -> Dict[str, bytes]:
        """Get multiple values using Redis MGET."""
        try:
            if not keys:
                return {}
            
            redis_keys = [self._make_key(key) for key in keys]
            values = await self.client.mget(redis_keys)
            
            result = {}
            for i, value in enumerate(values):
                if value is not None:
                    result[keys[i]] = value
            
            return result
        except Exception as e:
            raise GetError(f"Failed to get multiple keys: {e}")
    
    async def delete_many(self, keys: List[str]) -> int:
        """Delete multiple keys using Redis DEL."""
        try:
            if not keys:
                return 0
            
            redis_keys = [self._make_key(key) for key in keys]
            result = await self.client.delete(*redis_keys)
            return result
        except Exception as e:
            raise DeleteError(f"Failed to delete multiple keys: {e}")
    
    async def clear(self, namespace: Optional[str] = None) -> None:
        """Clear cache or namespace using Redis pattern deletion."""
        try:
            if namespace:
                pattern = f"{namespace}:*"
            elif self._namespace:
                pattern = f"{self._namespace}:*"
            else:
                # Clear entire database
                await self.client.flushdb()
                return
            
            # Delete keys matching pattern
            keys = await self.client.keys(pattern)
            if keys:
                await self.client.delete(*keys)
        except Exception as e:
            raise FlushError(f"Failed to clear cache: {e}")
    
    async def lock(self, key: str, ttl: float) -> Optional[str]:
        """Acquire a distributed lock using Redis."""
        import uuid
        lock_key = f"lock:{self._make_key(key)}"
        token = str(uuid.uuid4())
        
        try:
            # Use SET with NX and EX for atomic lock acquisition
            result = await self.client.set(lock_key, token, nx=True, ex=int(ttl))
            return token if result else None
        except Exception as e:
            raise OperationError(f"Failed to acquire lock for key '{key}': {e}")
    
    async def unlock(self, key: str, token: str) -> bool:
        """Release a distributed lock using Redis Lua script."""
        lock_key = f"lock:{self._make_key(key)}"
        
        # Lua script for atomic unlock
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        
        try:
            result = await self.client.eval(lua_script, 1, lock_key, token)
            return result == 1
        except Exception as e:
            raise OperationError(f"Failed to release lock for key '{key}': {e}")
    
    def get_cache_type(self) -> CacheType:
        """Get the cache type."""
        return CacheType.REDIS
    
    def get_default_ttl(self) -> float:
        """Get the default TTL."""
        return float(self.config.default_ttl_seconds) 