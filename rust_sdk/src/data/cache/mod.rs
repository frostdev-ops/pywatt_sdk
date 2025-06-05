use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::fmt::Debug;
use std::time::Duration;
use thiserror::Error;
use uuid;

// Modules
pub mod file;
pub mod in_memory;
pub mod memcached;
pub mod patterns;
pub mod proxy_service;
pub mod redis;
pub mod tests;

// Re-exports
pub use file::FileCache;
pub use in_memory::InMemoryCache;
#[cfg(feature = "memcached")]
pub use memcached::MemcachedCache;
pub use redis::RedisCache;

/// Cache policy enum for different caching strategies
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CachePolicy {
    /// Least Recently Used policy
    LRU,
    /// First In First Out policy
    FIFO,
    /// Most Recently Used policy
    MRU,
    /// Least Frequently Used policy
    LFU,
    /// No eviction policy
    None,
}

impl Default for CachePolicy {
    fn default() -> Self {
        Self::LRU
    }
}

/// Cache type enum for different cache service implementations
#[derive(Default, Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CacheType {
    /// In-memory cache (preferred variant)
    #[default]
    InMemory,
    /// Redis cache
    Redis,
    /// Memcached cache
    Memcached,
    /// File-based cache
    File,
}

/// Cache configuration – aligned with test expectations.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheConfig {
    /// Cache implementation type
    pub cache_type: CacheType,
    /// Cache eviction policy
    pub policy: CachePolicy,
    /// Maximum size in bytes (optional)
    pub max_size_bytes: Option<usize>,

    // ------------------------------------------------------------------
    // TTL handling
    // ------------------------------------------------------------------
    /// Default TTL for cache entries, expressed as seconds – **primary field used by tests**
    pub default_ttl_seconds: u64,
    /// Optional `Duration` based representation kept for legacy code-paths.
    pub default_ttl: Option<Duration>,

    // ------------------------------------------------------------------
    // Connection parameters
    // ------------------------------------------------------------------
    pub hosts: Vec<String>,
    pub port: Option<u16>,
    /// Network dial timeout
    pub connection_timeout_seconds: u64,
    /// Per-operation timeout
    pub operation_timeout_seconds: u64,

    // ------------------------------------------------------------------
    // Authentication & security
    // ------------------------------------------------------------------
    pub username: Option<String>,
    pub password: Option<String>,
    /// Enable TLS/SSL if supported by backend
    pub tls_enabled: bool,

    // ------------------------------------------------------------------
    // Backend-specific options
    // ------------------------------------------------------------------
    pub database: Option<u8>,
    pub file_path: Option<String>,
    /// Optional key namespace/prefix
    pub namespace: Option<String>,

    // ------------------------------------------------------------------
    // Pool configuration (re-used from the database module)
    // ------------------------------------------------------------------
    #[cfg(feature = "database")]
    pub pool: crate::data::database::PoolConfig,
    #[cfg(not(feature = "database"))]
    pub pool: DefaultPoolConfig,

    /// Additional opaque parameters
    pub extra_params: std::collections::HashMap<String, String>,
}

/// Default pool configuration when database feature is not enabled
#[cfg(not(feature = "database"))]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DefaultPoolConfig {
    pub max_connections: u32,
    pub min_connections: u32,
    pub idle_timeout_seconds: u64,
    pub max_lifetime_seconds: u64,
    pub acquire_timeout_seconds: u64,
}

#[cfg(not(feature = "database"))]
impl Default for DefaultPoolConfig {
    fn default() -> Self {
        Self {
            max_connections: 10,
            min_connections: 1,
            idle_timeout_seconds: 300,
            max_lifetime_seconds: 1800,
            acquire_timeout_seconds: 30,
        }
    }
}

impl CacheConfig {
    /// Helper accessor to obtain an actual `Duration` for the default TTL.
    pub fn get_default_ttl(&self) -> Duration {
        self.default_ttl
            .unwrap_or_else(|| Duration::from_secs(self.default_ttl_seconds))
    }
}

impl Default for CacheConfig {
    fn default() -> Self {
        Self {
            cache_type: CacheType::InMemory,
            policy: CachePolicy::default(),
            max_size_bytes: Some(1024 * 1024 * 10), // 10 MB
            default_ttl_seconds: 300,
            default_ttl: None,
            hosts: vec!["localhost".to_string()],
            port: None,
            connection_timeout_seconds: 5,
            operation_timeout_seconds: 2,
            username: None,
            password: None,
            tls_enabled: false,
            database: None,
            file_path: None,
            namespace: None,
            #[cfg(feature = "database")]
            pool: crate::data::database::PoolConfig::default(),
            #[cfg(not(feature = "database"))]
            pool: DefaultPoolConfig::default(),
            extra_params: std::collections::HashMap::new(),
        }
    }
}

/// Cache error type
#[derive(Debug, Error)]
pub enum CacheError {
    /// Connection error
    #[error("connection error: {0}")]
    Connection(String),

    /// Set operation error
    #[error("set error: {0}")]
    Set(String),

    /// Get operation error
    #[error("get error: {0}")]
    Get(String),

    /// Delete operation error
    #[error("delete error: {0}")]
    Delete(String),

    /// Flush operation error
    #[error("flush error: {0}")]
    Flush(String),

    /// Cache configuration error
    #[error("configuration error: {0}")]
    Configuration(String),

    /// Cache serialization/deserialization error
    #[error("serialization error: {0}")]
    Serialization(String),

    /// Cache IPC error
    #[error("IPC error: {0}")]
    Ipc(String),

    /// Operation error
    #[error("operation error: {0}")]
    Operation(String),

    /// Internal SDK implementation error
    #[error("internal error: {0}")]
    Internal(String),
}

/// Cache result type
pub type CacheResult<T> = std::result::Result<T, CacheError>;

/// Cache statistics – matches test expectations
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CacheStats {
    /// Number of cache hits
    pub hits: Option<u64>,
    /// Number of cache misses
    pub misses: Option<u64>,
    /// Number of set operations
    pub sets: Option<u64>,
    /// Number of delete operations
    pub deletes: Option<u64>,
    /// Total number of cached items
    pub item_count: Option<u64>,
    /// Memory usage in bytes (if provided by backend)
    pub memory_used_bytes: Option<u64>,
    /// Additional backend-specific metrics
    pub additional_metrics: std::collections::HashMap<String, String>,
}

/// Cache service interface
#[async_trait]
pub trait CacheService: Send + Sync {
    /// Get a value from the cache
    async fn get(&self, key: &str) -> CacheResult<Option<Vec<u8>>>;

    /// Set a value in the cache
    async fn set(&self, key: &str, value: &[u8], ttl: Option<Duration>) -> CacheResult<()>;

    /// Delete a value from the cache
    async fn delete(&self, key: &str) -> CacheResult<bool>;

    /// Delete all values from the cache
    async fn flush(&self) -> CacheResult<()>;

    /// Get cache statistics
    async fn stats(&self) -> CacheResult<CacheStats>;

    /// Ping the cache service
    async fn ping(&self) -> CacheResult<()>;

    /// Close the connection (if applicable)
    async fn close(&self) -> CacheResult<()>;

    // ------------------------------------------------------------------
    // Extended operations (required by tests) – default implementations
    // ------------------------------------------------------------------

    /// Check if a key exists without fetching its value
    async fn exists(&self, key: &str) -> CacheResult<bool> {
        // Fallback implementation – use `get` and map to boolean
        Ok(self.get(key).await?.is_some())
    }

    /// Set a value only if the key does not already exist (NX)
    async fn set_nx(&self, key: &str, value: &[u8], ttl: Option<Duration>) -> CacheResult<bool> {
        // Default implementation using get and set
        if self.exists(key).await? {
            Ok(false)
        } else {
            self.set(key, value, ttl).await?;
            Ok(true)
        }
    }

    /// Atomically fetch the current value and replace it
    async fn get_set(&self, key: &str, value: &[u8]) -> CacheResult<Option<Vec<u8>>> {
        // Default implementation using get and set
        let old_value = self.get(key).await?;
        self.set(key, value, None).await?;
        Ok(old_value)
    }

    /// Increment a numeric value (signed)
    async fn increment(&self, key: &str, delta: i64) -> CacheResult<i64> {
        // Default implementation using get, parse, increment, and set
        let current_value = match self.get(key).await? {
            Some(bytes) => {
                let value_str = String::from_utf8(bytes)
                    .map_err(|e| CacheError::Operation(format!("Invalid UTF-8: {}", e)))?;
                value_str.parse::<i64>()
                    .map_err(|e| CacheError::Operation(format!("Invalid integer: {}", e)))?
            }
            None => 0,
        };
        
        let new_value = current_value + delta;
        self.set(key, new_value.to_string().as_bytes(), None).await?;
        Ok(new_value)
    }

    /// Decrement convenience wrapper – default delegates to `increment`.
    async fn decrement(&self, key: &str, delta: i64) -> CacheResult<i64> {
        self.increment(key, -delta).await
    }

    /// Set multiple key/value pairs in a single operation
    async fn set_many(
        &self,
        items: &std::collections::HashMap<String, Vec<u8>>,
        ttl: Option<Duration>,
    ) -> CacheResult<()> {
        // Default implementation: set each item individually
        for (key, value) in items {
            self.set(key, value, ttl).await?;
        }
        Ok(())
    }

    /// Fetch many keys at once – implementation should skip missing keys
    async fn get_many(
        &self,
        keys: &[String],
    ) -> CacheResult<std::collections::HashMap<String, Vec<u8>>> {
        // Default implementation: get each key individually
        let mut result = std::collections::HashMap::new();
        for key in keys {
            if let Some(value) = self.get(key).await? {
                result.insert(key.clone(), value);
            }
        }
        Ok(result)
    }

    /// Delete many keys at once – return number of keys removed
    async fn delete_many(&self, keys: &[String]) -> CacheResult<u64> {
        // Default implementation: delete each key individually
        let mut count = 0;
        for key in keys {
            if self.delete(key).await? {
                count += 1;
            }
        }
        Ok(count)
    }

    /// Clear the cache or a namespace
    async fn clear(&self, namespace: Option<&str>) -> CacheResult<()> {
        // Default implementation: This operation is complex and backend-specific
        // For safety, we'll provide a basic flush if no namespace is specified
        if namespace.is_none() {
            self.flush().await
        } else {
            Err(CacheError::Operation(
                "Namespace-specific clear not implemented for this backend. Use flush() to clear all.".to_string(),
            ))
        }
    }

    /// Acquire a simple lock – returns token if lock acquired
    async fn lock(&self, key: &str, ttl: Duration) -> CacheResult<Option<String>> {
        // Default implementation using set_nx
        let lock_key = format!("lock:{}", key);
        let token = uuid::Uuid::new_v4().to_string();
        
        if self.set_nx(&lock_key, token.as_bytes(), Some(ttl)).await? {
            Ok(Some(token))
        } else {
            Ok(None)
        }
    }

    /// Release a lock
    async fn unlock(&self, key: &str, token: &str) -> CacheResult<bool> {
        // Default implementation: check token and delete if matches
        let lock_key = format!("lock:{}", key);
        
        // Check if the lock exists and has the correct token
        if let Some(stored_token_bytes) = self.get(&lock_key).await? {
            let stored_token = String::from_utf8(stored_token_bytes)
                .map_err(|e| CacheError::Operation(format!("Invalid UTF-8 in stored token: {}", e)))?;
            
            if stored_token == token {
                self.delete(&lock_key).await?;
                Ok(true)
            } else {
                Ok(false) // Token mismatch
            }
        } else {
            Ok(false) // Lock doesn't exist
        }
    }

    /// Expose backend type – useful for down-casting & diagnostics
    fn get_cache_type(&self) -> CacheType {
        CacheType::InMemory
    }

    /// Helper accessor for the backend default TTL
    fn get_default_ttl(&self) -> Duration {
        Duration::from_secs(0)
    }

    /// Convenience helper: fetch value as UTF-8 string
    async fn get_string(&self, key: &str) -> CacheResult<Option<String>> {
        match self.get(key).await? {
            Some(bytes) => match String::from_utf8(bytes) {
                Ok(s) => Ok(Some(s)),
                Err(e) => Err(CacheError::Get(format!("Invalid UTF-8: {}", e))),
            },
            None => Ok(None),
        }
    }

    /// Convenience helper: set value as UTF-8 string
    async fn set_string(&self, key: &str, value: &str, ttl: Option<Duration>) -> CacheResult<()> {
        self.set(key, value.as_bytes(), ttl).await
    }
}

/// Create a cache service from a configuration
pub async fn create_cache_service(config: &CacheConfig) -> CacheResult<Box<dyn CacheService>> {
    match config.cache_type {
        CacheType::InMemory => {
            let cache = InMemoryCache::new(config);
            Ok(Box::new(cache) as Box<dyn CacheService>)
        }
        CacheType::Redis => {
            #[cfg(feature = "redis_cache")]
            {
                let cache = RedisCache::connect(config).await?;
                Ok(Box::new(cache) as Box<dyn CacheService>)
            }
            #[cfg(not(feature = "redis_cache"))]
            {
                Err(CacheError::Configuration(
                    "Redis cache support is not enabled. Enable the 'redis_cache' feature."
                        .to_string(),
                ))
            }
        }
        CacheType::Memcached => {
            #[cfg(feature = "memcached")]
            {
                let cache = MemcachedCache::connect(config).await?;
                Ok(Box::new(cache) as Box<dyn CacheService>)
            }
            #[cfg(not(feature = "memcached"))]
            {
                Err(CacheError::Configuration(
                    "Memcached support is not enabled. Enable the 'memcached' feature.".to_string(),
                ))
            }
        }
        CacheType::File => {
            #[cfg(feature = "file_cache")]
            {
                let cache = FileCache::new(config).await?;
                Ok(Box::new(cache) as Box<dyn CacheService>)
            }
            #[cfg(not(feature = "file_cache"))]
            {
                Err(CacheError::Configuration(
                    "File cache support is not enabled. Enable the 'file_cache' feature."
                        .to_string(),
                ))
            }
        }
    }
}
