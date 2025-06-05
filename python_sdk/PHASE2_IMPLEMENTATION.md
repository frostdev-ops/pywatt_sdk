# PyWatt Python SDK - Phase 2 Implementation

## Overview

Phase 2 of the PyWatt Python SDK introduces advanced communication capabilities, service integration, and comprehensive data layer abstractions. This implementation builds upon Phase 1's foundation while maintaining full backward compatibility.

## New Features Implemented

### 1. Advanced Communication Layer

#### TCP Channel (`pywatt_sdk/communication/tcp_channel.py`)
- **Connection pooling** with configurable pool sizes
- **Health monitoring** with automatic reconnection
- **Reconnection policies**: None, FixedInterval, ExponentialBackoff
- **TLS support** for secure communications
- **Async context manager** for proper resource management
- **Message framing** compatible with Rust SDK

#### IPC Channel (`pywatt_sdk/communication/ipc_channel.py`)
- **Unix Domain Socket** communication for local modules
- **Similar feature set** to TCP channel but optimized for local communication
- **Automatic socket cleanup** and management
- **Async/await support** throughout

#### Enhanced Message System (`pywatt_sdk/communication/message.py`)
- **Generic Message class** with type safety
- **Multiple encoding formats**: JSON, MessagePack, Bincode (for Rust interop)
- **Message framing protocol** with length prefixes
- **Streaming support** for large messages
- **Metadata support** for message routing and tracking

### 2. Service Layer

#### Module Registration (`pywatt_sdk/services/registration.py`)
- **Comprehensive module registration** with the orchestrator
- **Capability advertisement** (HTTP, WebSocket, streaming, custom)
- **Health status reporting** with automatic heartbeats
- **Endpoint registration** with authentication requirements
- **Graceful unregistration** on shutdown

#### Service Discovery (`pywatt_sdk/services/service_discovery.py`)
- **Service provider registration** for different service types
- **Dynamic service discovery** with real-time updates
- **Service provider builder** with fluent API
- **Service type enumeration** (USER_MANAGEMENT, ANALYTICS, etc.)
- **Provider metadata** and capability matching

### 3. Data Layer Abstractions

#### Database Abstraction (`pywatt_sdk/data/database.py`)
- **Multi-database support**: PostgreSQL, MySQL, SQLite
- **Connection pooling** with configurable parameters
- **Transaction management** with proper rollback handling
- **Async query execution** with parameter binding
- **Proxy connections** for orchestrator-managed databases
- **Factory pattern** for easy database creation
- **Comprehensive error handling** with specific error types

#### Cache Abstraction (`pywatt_sdk/data/cache.py`)
- **Multiple cache backends**: In-memory, Redis, Memcached, File-based
- **TTL support** with automatic expiration
- **Cache policies** (LRU, LFU, FIFO, Random)
- **Advanced operations**: exists, set_nx, get_set, increment, decrement
- **Proxy caching** through orchestrator
- **Batch operations** for efficiency
- **Cache statistics** and monitoring

### 4. Security Enhancements

#### JWT Authentication (`pywatt_sdk/security/jwt_auth.py`)
- **FastAPI and Flask middleware** support
- **Local and proxy validation** (when running as module)
- **Configurable JWT validation** (expiration, signature, audience, issuer)
- **Custom claims support** with type safety
- **Automatic secret redaction** for security
- **Generic claims types** for flexibility

#### Enhanced Secret Management (`pywatt_sdk/security/secrets.py`)
- **Multiple secret providers**: Environment, Memory, Orchestrator
- **Secret caching** with TTL and LRU eviction
- **Secret rotation** with callback notifications
- **Automatic redaction** in logs
- **Secret versioning** and metadata
- **Factory pattern** for provider selection

### 5. Internal Messaging System

#### Inter-Module Communication (`pywatt_sdk/internal/messaging.py`)
- **Request/response patterns** between modules
- **One-way notifications** for fire-and-forget messaging
- **Timeout handling** with configurable timeouts
- **Request tracking** with unique IDs
- **Automatic cleanup** of expired requests
- **Type-safe message serialization/deserialization
- **Error propagation** from target modules

### 6. Enhanced AppState

#### Comprehensive State Management (`python_sdk/pywatt_sdk/core/state.py`)
- **Integrated service clients** (registration, discovery, messaging)
- **Data layer services** (database, cache) 
- **Security services** (secret manager, JWT validator)
- **Communication channels** (TCP, IPC)
- **Convenience methods** for common operations:
  - `get_secret()`, `set_secret()`
  - `execute_query()`, `cache_get()`, `cache_set()`
  - `send_message()`, `send_request()`
  - `register_service_provider()`, `discover_service_providers()`
  - `validate_jwt_token()`
- **Resource cleanup** with `close()` method
- **Channel health monitoring** and capabilities reporting

### 7. Enhanced Module Decorator

#### Advanced @pywatt_module Decorator (`python_sdk/pywatt_sdk/module.py`)
- **Phase 2 feature flags** for selective enablement
- **Configuration injection** for all services
- **Automatic service initialization** based on configuration
- **Enhanced error handling** with graceful degradation
- **Service capability advertisement** 
- **Comprehensive logging** throughout initialization
- **Backward compatibility** with Phase 1 modules

## Configuration Examples

### Basic Phase 2 Module
```python
@pywatt_module(
    secrets=["DATABASE_URL", "JWT_SECRET"],
    rotate=True,
    endpoints=[
        AnnouncedEndpoint(path="/users", methods=["GET", "POST"], auth="jwt"),
        AnnouncedEndpoint(path="/health", methods=["GET"], auth=None),
    ],
    # Phase 2 features
    enable_database=True,
    enable_cache=True,
    enable_jwt=True,
    database_config={
        "type": DatabaseType.POSTGRESQL,
        "host": "localhost",
        "database": "myapp",
    },
    cache_config={
        "type": CacheType.REDIS,
        "host": "localhost",
        "port": 6379,
    },
    jwt_config={
        "secret_key": "your-secret-key",
        "algorithm": "HS256",
    }
)
async def create_app(state: AppState[MyUserState]):
    # Your app logic here
    pass
```

### Advanced Configuration
```python
@pywatt_module(
    # Enable all Phase 2 features
    enable_tcp=True,
    enable_ipc=True,
    enable_service_discovery=True,
    enable_module_registration=True,
    enable_database=True,
    enable_cache=True,
    enable_jwt=True,
    enable_internal_messaging=True,
    
    # Advanced configurations
    tcp_config={
        "host": "127.0.0.1",
        "port": 0,
        "pool_size": 10,
        "timeout": 30,
        "enable_tls": True,
    },
    database_config={
        "type": DatabaseType.POSTGRESQL,
        "host": "db.example.com",
        "database": "production",
        "pool_config": {
            "min_connections": 5,
            "max_connections": 20,
        }
    },
    service_capabilities=[
        "user_management",
        "real_time_analytics",
        "data_export",
    ]
)
async def create_app(state: AppState[MyUserState]):
    # Full-featured app with all Phase 2 capabilities
    pass
```

## Usage Examples

### Database Operations
```python
# Execute queries
users = await state.execute_query("SELECT * FROM users WHERE active = ?", [True])

# Use transactions (when available)
async with state.database.transaction() as tx:
    await tx.execute("INSERT INTO users (name) VALUES (?)", ["Alice"])
    await tx.execute("INSERT INTO logs (action) VALUES (?)", ["user_created"])
    await tx.commit()
```

### Cache Operations
```python
# Basic caching
await state.cache_set("user:123", user_data, ttl=3600)
user = await state.cache_get("user:123")

# Advanced operations
exists = await state.cache.exists("user:123")
new_count = await state.cache.increment("user_count")
```

### Inter-Module Communication
```python
# Send notification
await state.send_message(
    "analytics:user_event",
    {"event": "login", "user_id": 123}
)

# Send request and get response
config = await state.send_request(
    "config:get_setting",
    {"key": "max_users"},
    response_type=dict
)
```

### Service Discovery
```python
# Register as service provider
await state.register_service_provider(
    ServiceType.USER_MANAGEMENT,
    {
        "version": "1.0.0",
        "endpoints": ["/users", "/auth"],
        "capabilities": ["crud", "authentication"]
    }
)

# Discover other services
analytics_providers = await state.discover_service_providers(ServiceType.ANALYTICS)
```

### JWT Authentication
```python
# In FastAPI
from pywatt_sdk.security import create_jwt_middleware

jwt_config = JwtConfig(secret_key="your-secret", algorithm="HS256")
middleware = create_jwt_middleware("fastapi", jwt_config)
app.add_middleware(middleware)

# In handlers
claims = extract_jwt_claims(request, "fastapi")
user_id = claims.sub
```

## Backward Compatibility

Phase 2 maintains full backward compatibility with Phase 1:

- **All Phase 1 APIs** continue to work unchanged
- **Graceful degradation** when Phase 2 features are not available
- **Optional imports** prevent errors in Phase 1 environments
- **Feature flags** allow selective enablement
- **Default configurations** provide sensible defaults

## Error Handling

Comprehensive error handling throughout:

- **Specific error types** for different failure modes
- **Error propagation** with context preservation
- **Graceful degradation** when services are unavailable
- **Detailed logging** for debugging
- **Recovery mechanisms** for transient failures

## Testing and Examples

- **Comprehensive example** in `examples/phase2_example.py`
- **Feature demonstration** showing all capabilities
- **Mock implementations** for testing
- **Integration patterns** with popular frameworks

## Performance Considerations

- **Connection pooling** for database and cache connections
- **Async/await** throughout for non-blocking operations
- **Message framing** for efficient network communication
- **Caching layers** to reduce external service calls
- **Resource cleanup** to prevent memory leaks

## Security Features

- **Automatic secret redaction** in logs
- **TLS support** for encrypted communication
- **JWT validation** with configurable options
- **Secret rotation** with automatic updates
- **Proxy validation** when running as module

## Future Extensibility

The Phase 2 implementation provides a solid foundation for future enhancements:

- **Plugin architecture** for custom providers
- **Middleware system** for request/response processing
- **Event system** for reactive programming
- **Metrics collection** and monitoring
- **Distributed tracing** support

## Migration Guide

For existing Phase 1 modules:

1. **No changes required** for basic functionality
2. **Add Phase 2 features** incrementally by enabling flags
3. **Update configurations** to use new service options
4. **Enhance error handling** to use new error types
5. **Leverage new APIs** for improved functionality

Phase 2 represents a significant advancement in the PyWatt Python SDK, providing enterprise-grade features while maintaining the simplicity and ease of use that made Phase 1 successful. 