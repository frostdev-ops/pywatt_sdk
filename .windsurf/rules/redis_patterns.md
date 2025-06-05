---
trigger: model_decision
description: This rule documents the Redis integration patterns in the PyWatt-Rust project, including best practices for handling Redis connections, commands, queries, and error handling.
globs: 
---
# Redis Integration Patterns

<context>
This rule documents the Redis integration patterns in the PyWatt-Rust project, including best practices for handling Redis connections, commands, queries, and error handling.
</context>

<rules>

## Connection Management
- Use the RedisClient wrapper from the project to manage connections
- Always release connections back to the pool after use
- Use scoped connection management with Redis transactions
- Consider connection timeouts for operations

## Command Execution
- For commands that don't return values, use `execute_async` instead of `query_async`
- Specify the return type explicitly for `query_async` calls
- Use the appropriate Redis data structure for the use case
- Chain commands efficiently when working with transactions

## Type Safety
- Always specify the return type for `query_async` calls to avoid type inference issues
- For commands that don't return meaningful values, use `()` as the return type
- Use `Option<T>` for commands that might return null values
- Use the appropriate Redis serialization/deserialization traits

## Error Handling
- Handle Redis errors gracefully with proper error mapping
- Add context to Redis errors for better debugging
- Consider retries for transient Redis errors
- Log Redis errors with appropriate detail

## Caching Strategies
- Define clear TTL (Time To Live) policies for cached data
- Use consistent key naming conventions
- Implement cache invalidation strategies
- Consider cache stampede protection for frequently accessed keys

</rules>

<patterns>

## Basic Redis Command Execution
```rust
// For commands that don't return a value, use execute_async() with ()
let mut conn = redis_client.get_async_connection().await?;
redis::cmd("SET")
    .arg(&[key, value])
    .arg("EX")
    .arg(expiry_seconds)
    .execute_async(&mut conn)
    .await?;

// For commands that return a value, use query_async() with explicit type
let result: Option<String> = redis::cmd("GET")
    .arg(key)
    .query_async(&mut conn)
    .await?;
```

## Redis Command with Explicit Return Type
```rust
// Always specify the return type for query_async
let exists: bool = redis::cmd("EXISTS")
    .arg(key)
    .query_async(&mut conn)
    .await?;

// For commands that return multiple values
let values: Vec<String> = redis::cmd("MGET")
    .arg(&keys)
    .query_async(&mut conn)
    .await?;
```

## Redis Transactions
```rust
let mut conn = redis_client.get_async_connection().await?;

// Start transaction
redis::cmd("MULTI").execute_async(&mut conn).await?;

// Queue commands
redis::cmd("SET")
    .arg(&["key1", "value1"])
    .execute_async(&mut conn)
    .await?;
    
redis::cmd("SET")
    .arg(&["key2", "value2"])
    .execute_async(&mut conn)
    .await?;

// Execute transaction
let _: () = redis::cmd("EXEC")
    .query_async(&mut conn)
    .await?;
```

## Redis Pipeline
```rust
let mut conn = redis_client.get_async_connection().await?;
let mut pipe = redis::pipe();

// Add commands to pipeline
pipe.set("key1", "value1")
    .set("key2", "value2")
    .expire("key1", 60)
    .expire("key2", 120);

// Execute pipeline
let _: () = pipe.query_async(&mut conn).await?;
```

## Redis Key Expiration
```rust
pub async fn set_with_expiry<T: ToRedisArgs + Send + Sync>(
    &self,
    key: &str,
    value: T,
    expiry_seconds: u64,
) -> AppResult<()> {
    let mut conn = self.client.get_async_connection().await?;
    
    let _: () = redis::cmd("SET")
        .arg(key)
        .arg(value)
        .arg("EX")
        .arg(expiry_seconds)
        .query_async(&mut conn)
        .await
        .map_err(|e| AppError::RedisError(format!("Failed to set key {}: {}", key, e)))?;
    
    Ok(())
}
```

</patterns>

<examples>

## Session Storage Example
```rust
pub async fn store_session(&self, session_id: &str, user_id: Uuid, expires_in: u64) -> AppResult<()> {
    let mut conn = self.redis.get_async_connection().await?;
    
    // Store the session with expiry
    let _: () = redis::cmd("SET")
        .arg(format!("session:{}", session_id))
        .arg(user_id.to_string())
        .arg("EX")
        .arg(expires_in)
        .query_async(&mut conn)
        .await
        .map_err(|e| AppError::RedisError(format!("Failed to store session: {}", e)))?;
    
    // Add to user's sessions set
    let _: () = redis::cmd("SADD")
        .arg(format!("user:{}:sessions", user_id))
        .arg(session_id)
        .query_async(&mut conn)
        .await
        .map_err(|e| AppError::RedisError(format!("Failed to add to user sessions: {}", e)))?;
    
    Ok(())
}
```

## Rate Limiting Example
```rust
pub async fn check_rate_limit(
    &self,
    key: &str,
    max_requests: u32,
    window_seconds: u32,
) -> AppResult<bool> {
    let mut conn = self.redis.get_async_connection().await?;
    let now = Utc::now().timestamp();
    
    // Remove old entries
    let _: () = redis::cmd("ZREMRANGEBYSCORE")
        .arg(key)
        .arg("-inf")
        .arg(now - window_seconds as i64)
        .query_async(&mut conn)
        .await
        .map_err(|e| AppError::RedisError(format!("Failed to clean rate limit entries: {}", e)))?;
    
    // Count current entries
    let count: u32 = redis::cmd("ZCARD")
        .arg(key)
        .query_async(&mut conn)
        .await
        .map_err(|e| AppError::RedisError(format!("Failed to count rate limit entries: {}", e)))?;
    
    // Check if under limit
    if count < max_requests {
        // Add new entry
        let _: () = redis::cmd("ZADD")
            .arg(key)
            .arg(now)
            .arg(format!("{}", Uuid::new_v4()))
            .query_async(&mut conn)
            .await
            .map_err(|e| AppError::RedisError(format!("Failed to add rate limit entry: {}", e)))?;
        
        // Set expiry on the whole key
        let _: () = redis::cmd("EXPIRE")
            .arg(key)
            .arg(window_seconds)
            .query_async(&mut conn)
            .await
            .map_err(|e| AppError::RedisError(format!("Failed to set rate limit expiry: {}", e)))?;
        
        Ok(true)
    } else {
        Ok(false)
    }
}
```

## Cache with JSON Serialization
```rust
pub async fn get_cached_json<T: DeserializeOwned>(
    &self,
    key: &str,
) -> AppResult<Option<T>> {
    let mut conn = self.redis.get_async_connection().await?;
    
    // Try to get from cache
    let json: Option<String> = redis::cmd("GET")
        .arg(key)
        .query_async(&mut conn)
        .await
        .map_err(|e| AppError::RedisError(format!("Failed to get cached value: {}", e)))?;
    
    // Parse JSON if found
    if let Some(json_str) = json {
        let value = serde_json::from_str(&json_str)
            .map_err(|e| AppError::SerializationError(format!("Failed to deserialize cached value: {}", e)))?;
        Ok(Some(value))
    } else {
        Ok(None)
    }
}

pub async fn set_cached_json<T: Serialize>(
    &self,
    key: &str,
    value: &T,
    expiry_seconds: u64,
) -> AppResult<()> {
    let mut conn = self.redis.get_async_connection().await?;
    
    // Serialize to JSON
    let json = serde_json::to_string(value)
        .map_err(|e| AppError::SerializationError(format!("Failed to serialize value: {}", e)))?;
    
    // Store with expiry
    let _: () = redis::cmd("SET")
        .arg(key)
        .arg(json)
        .arg("EX")
        .arg(expiry_seconds)
        .query_async(&mut conn)
        .await
        .map_err(|e| AppError::RedisError(format!("Failed to cache value: {}", e)))?;
    
    Ok(())
}
```

</examples>

<common_issues>

## Missing Return Type for query_async
```rust
// Incorrect: Missing return type
redis::cmd("SET")
    .arg(&[key, value])
    .query_async(&mut conn)
    .await?;

// Correct: Explicit return type
let _: () = redis::cmd("SET")
    .arg(&[key, value])
    .query_async(&mut conn)
    .await?;
```

## Connection Not Released
```rust
// Incorrect: Connection might not be released on error
let conn = redis_client.get_async_connection().await?;
redis::cmd("SET").arg(&[key, value]).query_async(&conn).await?;
redis::cmd("EXPIRE").arg(&[key, "60"]).query_async(&conn).await?;

// Correct: Use scoped blocks or drop connection explicitly
let mut conn = redis_client.get_async_connection().await?;
let result = redis::cmd("SET").arg(&[key, value]).query_async(&mut conn).await;
// Connection dropped here, returning to pool
result?;
```

## Not Handling Redis Null Values
```rust
// Incorrect: Not handling null values
let value: String = redis::cmd("GET")
    .arg(key)
    .query_async(&mut conn)
    .await?; // Will fail if key doesn't exist

// Correct: Using Option<T>
let value: Option<String> = redis::cmd("GET")
    .arg(key)
    .query_async(&mut conn)
    .await?; // Returns None if key doesn't exist
```

## Incorrect Transaction Handling
```rust
// Incorrect: Not checking EXEC result
redis::cmd("MULTI").execute_async(&mut conn).await?;
redis::cmd("SET").arg(&["key", "value"]).execute_async(&mut conn).await?;
redis::cmd("EXEC").execute_async(&mut conn).await?; // Should be query_async

// Correct: Properly executing and checking transaction
redis::cmd("MULTI").execute_async(&mut conn).await?;
redis::cmd("SET").arg(&["key", "value"]).execute_async(&mut conn).await?;
let results: Vec<redis::Value> = redis::cmd("EXEC")
    .query_async(&mut conn)
    .await?;

if results.iter().any(|v| v.is_error()) {
    return Err(AppError::RedisError("Transaction failed".to_string()));
}
```

</common_issues>

<dependencies>

## Required Crates
- `redis`: For Redis client functionality
- `serde`: For serialization/deserialization support
- `serde_json`: For JSON serialization
- `uuid`: For generating unique identifiers
- `chrono`: For timestamp handling

</dependencies>
