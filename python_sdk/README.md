# PyWatt SDK for Python

Build powerful modules for the Wattson orchestrator using Python.

## Overview

The PyWatt SDK for Python provides a simple, decorator-based approach to building modules that integrate seamlessly with the Wattson orchestrator. With just a few lines of code, you can create modules that support:

- 🔗 **Multiple Communication Channels**: IPC, TCP, and HTTP
- 🔐 **Secret Management**: Automatic fetching and rotation
- 🌐 **Service Discovery**: Find and connect to other modules
- 📊 **Metrics & Monitoring**: Built-in Prometheus support
- 🛡️ **Security**: JWT authentication and authorization
- 💾 **Data Layer**: Database and cache integration
- 🔄 **Internal Messaging**: Inter-module communication

## Installation

```bash
pip install pywatt-sdk
```

Or install with specific framework support:

```bash
# For FastAPI support
pip install pywatt-sdk[fastapi]

# For Flask support
pip install pywatt-sdk[flask]

# For all features
pip install pywatt-sdk[all]
```

## Quick Start

Create a simple module using the `@pywatt_module` decorator:

```python
from pywatt_sdk import pywatt_module, AppState, AnnouncedEndpoint
from fastapi import FastAPI

@pywatt_module(
    endpoints=[
        AnnouncedEndpoint(path="/", methods=["GET"]),
        AnnouncedEndpoint(path="/health", methods=["GET"]),
    ],
    health="/health"
)
async def create_app(app_state: AppState) -> FastAPI:
    app = FastAPI(title="My Module")
    
    @app.get("/")
    async def root():
        return {"message": "Hello from PyWatt!"}
    
    @app.get("/health")
    async def health():
        return {"status": "healthy"}
    
    return app
```

That's it! The SDK handles:
- IPC handshake with the orchestrator
- Endpoint announcement
- Secret management
- Graceful shutdown
- And much more...

## Features

### 🎯 Simple Decorator-Based API

The `@pywatt_module` decorator is all you need:

```python
@pywatt_module(
    # Secret Management
    secrets=["DATABASE_URL", "API_KEY"],
    rotate=True,  # Enable automatic rotation
    
    # Endpoints to announce
    endpoints=[
        AnnouncedEndpoint(path="/api/users", methods=["GET", "POST"]),
        AnnouncedEndpoint(path="/api/admin", methods=["GET"], auth="jwt"),
    ],
    
    # Health check endpoint
    health="/health",
    
    # Enable metrics
    metrics=True,
    
    # Framework (fastapi or flask)
    framework="fastapi"
)
async def create_app(app_state: AppState) -> FastAPI:
    # Your app initialization code
    pass
```

### 🔐 Automatic Secret Management

Secrets are automatically fetched and made available:

```python
@pywatt_module(secrets=["DATABASE_URL", "JWT_SECRET"])
async def create_app(app_state: AppState) -> FastAPI:
    # Secrets are available in app_state
    db_url = await app_state.get_secret("DATABASE_URL")
    
    # Connect to database using the secret
    db = Database(db_url.expose_secret())
```

### 🌐 Service Discovery

Find and connect to other modules:

```python
# Discover database services
db_services = await app_state.discover_services("database")
for service in db_services:
    print(f"Found database at {service.address}")

# Register your own service
await app_state.register_service(
    name="my-api",
    service_type="api",
    address="127.0.0.1:8080"
)
```

### 📊 Built-in Metrics

Prometheus metrics are automatically exposed:

```python
@pywatt_module(metrics=True)
async def create_app(app_state: AppState) -> FastAPI:
    # Metrics available at /metrics endpoint
    # Custom metrics can be added:
    app_state.metrics.counter("requests_total").inc()
```

### 🛡️ JWT Authentication

Built-in JWT middleware for protected endpoints:

```python
@pywatt_module(
    endpoints=[
        AnnouncedEndpoint(path="/public", methods=["GET"]),
        AnnouncedEndpoint(path="/private", methods=["GET"], auth="jwt"),
    ],
    jwt_secret="your-secret"
)
```

### 💾 Database & Cache Integration

Easy database and cache connections:

```python
@pywatt_module(
    enable_database=True,
    enable_cache=True,
    database_config={"type": "postgresql", "url": "..."},
    cache_config={"type": "redis", "url": "..."}
)
async def create_app(app_state: AppState) -> FastAPI:
    # Use database
    async with app_state.db.acquire() as conn:
        result = await conn.fetch("SELECT * FROM users")
    
    # Use cache
    await app_state.cache.set("key", "value", expire=60)
    value = await app_state.cache.get("key")
```

## Advanced Features

### Custom State Builder

Provide custom initialization logic:

```python
def build_custom_state(init_data, secret_values):
    return MyCustomState(
        module_id=init_data.module_id,
        secrets=secret_values
    )

@pywatt_module(
    state_builder=build_custom_state,
    secrets=["API_KEY"]
)
async def create_app(app_state: AppState) -> FastAPI:
    # app_state.user_state is your MyCustomState instance
    pass
```

### Multiple Communication Channels

Enable different communication methods:

```python
@pywatt_module(
    enable_tcp=True,
    enable_ipc=True,
    tcp_config={"host": "0.0.0.0", "port": 9000}
)
```

### Internal Messaging

Send messages between modules:

```python
# Send a message
await app_state.send_message(
    target="other-module",
    message={"type": "notification", "data": "..."}
)

# Handle incoming messages
@app_state.on_message("notification")
async def handle_notification(message):
    print(f"Received: {message}")
```

## Framework Support

### FastAPI (Recommended)

```python
from fastapi import FastAPI, Depends
from pywatt_sdk import pywatt_module, AppState

@pywatt_module(framework="fastapi")
async def create_app(app_state: AppState) -> FastAPI:
    app = FastAPI()
    
    # Use dependency injection
    async def get_state():
        return app_state
    
    @app.get("/")
    async def root(state: AppState = Depends(get_state)):
        return {"module_id": state.module_id}
    
    return app
```

### Flask

```python
from flask import Flask
from pywatt_sdk import pywatt_module, AppState

@pywatt_module(framework="flask")
def create_app(app_state: AppState) -> Flask:
    app = Flask(__name__)
    
    @app.route("/")
    def root():
        return {"module_id": app_state.module_id}
    
    return app
```

## Testing

Test your modules locally:

```python
# test_module.py
import asyncio
from mymodule import create_app

async def test():
    # Mock orchestrator init
    init_data = {
        "orchestrator_api": "http://localhost:9900",
        "module_id": "test-module",
        "listen": "127.0.0.1:8080"
    }
    
    # Create and run app
    app = await create_app(init_data)
    # Test your endpoints...

asyncio.run(test())
```

## Best Practices

1. **Use Type Hints**: The SDK is fully typed for better IDE support
2. **Handle Errors**: Use proper error handling for robustness
3. **Log Appropriately**: Use structured logging (logs go to stderr)
4. **Test Locally**: Test modules before deploying to Wattson
5. **Monitor Performance**: Use built-in metrics for monitoring

## Examples

See the `examples/` directory for complete examples:

- `basic_module.py` - Simple HTTP API module
- `database_module.py` - Module with database integration
- `service_discovery.py` - Inter-module communication
- `websocket_module.py` - WebSocket support
- `background_tasks.py` - Long-running tasks

## API Reference

### Decorator Parameters

- `secrets`: List of secret keys to fetch
- `rotate`: Enable automatic secret rotation
- `endpoints`: List of endpoints to announce
- `health`: Health check endpoint path
- `metrics`: Enable Prometheus metrics
- `framework`: Web framework ("fastapi" or "flask")
- `state_builder`: Custom state initialization function
- `enable_*`: Enable specific features (tcp, ipc, database, etc.)

### AppState Methods

- `get_secret(key)`: Get a secret value
- `discover_services(type)`: Find services by type
- `register_service(...)`: Register this module as a service
- `send_message(...)`: Send internal message
- `on_message(type)`: Register message handler

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](LICENSE) for details. 