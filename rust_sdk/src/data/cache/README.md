# Cache Module

This module provides a flexible and extensible caching framework for the PyWatt SDK. It defines a core `CacheService` trait and offers several implementations, along with common caching patterns and utilities.

## Core Components

-   **`CacheService` Trait (`mod.rs`)**: Defines the standard interface for all cache implementations. It includes methods for common cache operations like `get`, `set`, `delete`, `exists`, `increment`, `lock`, `unlock`, etc.
-   **`CacheConfig` Struct (`mod.rs`)**: A comprehensive configuration structure for initializing cache services. It allows specifying cache type, policies, TTLs, connection parameters, authentication, and backend-specific options.
-   **`CacheError` Enum (`mod.rs`)**: Defines a set of errors that can occur during cache operations, such as connection errors, serialization issues, or operation-specific failures.
-   **`CachePolicy` Enum (`mod.rs`)**: Specifies different cache eviction policies like LRU, FIFO, MRU, LFU, or None.
-   **`CacheType` Enum (`mod.rs`)**: Enumerates the available cache backend implementations (`InMemory`, `Redis`, `Memcached`, `File`).
-   **`CacheStats` Struct (`mod.rs`)**: Represents statistics for a cache instance, such as hits, misses, current size, etc.
-   **`create_cache_service` Function (`mod.rs`)**: A factory function to create a `CacheService` instance based on a given `CacheConfig`.

## Cache Implementations

The module provides the following concrete cache implementations:

-   **`InMemoryCache` (`in_memory.rs`)**: A thread-safe in-memory cache utilizing `DashMap`. It supports TTL-based expiration with a background cleanup task and an optional maximum item count with a simple random eviction strategy.
-   **`FileCache` (`file.rs`)**: A cache that stores entries as files on the local filesystem. It handles key-to-path mapping, expiration checks, and basic file operations. File locking is supported via a feature flag (`file_cache`).
-   **`RedisCache` (`redis.rs`)**: An implementation that interacts with a Redis server using the `redis-rs` crate. This is available when the `redis_cache` feature is enabled. It supports connection management, key prefixing, and error conversion.
-   **`MemcachedCache` (`memcached.rs`)**: An implementation that interacts with a Memcached server using the `memcache` crate. This is available when the `memcached` feature is enabled. It handles connections, key prefixing, and command mapping.

## Caching Patterns and Utilities

-   **`patterns.rs`**: This file implements several common caching patterns and utilities:
    -   **Cache-Aside**: Fetches from cache; if missed, fetches from source and populates cache.
    -   **Write-Through**: Writes to both cache and source synchronously.
    -   **Write-Behind**: Writes to cache immediately and to source asynchronously.
    -   **Invalidation Strategies**: Includes `TtlInvalidationStrategy`, `EventInvalidationStrategy` (with optional versioning), and `LruInvalidationStrategy` (primarily for in-memory).
    -   **`DistributedLock`**: A distributed lock implementation using the cache backend, with retry capabilities.

## Proxy Service

-   **`ProxyCacheService` (`proxy_service.rs`)**: Implements the `CacheService` trait by acting as a client to a remote cache service. It communicates via IPC, translating local cache calls into messages for an orchestrator or dedicated cache server. This allows modules to use caching facilities provided by a central service.

## Usage

To use a cache, you typically:

1.  Create a `CacheConfig` instance, specifying the desired `CacheType` and other parameters.
2.  Call `create_cache_service(&config)` to obtain a `Box<dyn CacheService>`.
3.  Use the methods defined in the `CacheService` trait to interact with the cache.

Alternatively, for remote caching, a `ProxyCacheService` can be instantiated and used if the environment provides an IPC-based cache service.

Caching patterns from `patterns.rs` can be used to further structure cache interactions with data sources.
