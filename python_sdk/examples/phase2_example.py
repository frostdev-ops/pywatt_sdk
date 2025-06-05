#!/usr/bin/env python3
"""
Comprehensive Phase 2 PyWatt SDK Example

This example demonstrates all the advanced features available in Phase 2:
- TCP and IPC communication channels
- Service registration and discovery
- Database and cache integration
- JWT authentication
- Internal messaging between modules
- Secret management with rotation
- Enhanced AppState with all services
"""

import asyncio
import logging
from typing import Dict, Any, List
from dataclasses import dataclass

from pywatt_sdk import pywatt_module, AppState, AppConfig, AnnouncedEndpoint
from pywatt_sdk.communication import ChannelType, ChannelPreferences
from pywatt_sdk.services import ServiceType
from pywatt_sdk.data import DatabaseType, CacheType
from pywatt_sdk.security import JwtClaims

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class UserData:
    """Custom user state for our module."""
    user_count: int = 0
    active_sessions: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.active_sessions is None:
            self.active_sessions = {}

async def build_user_state(init_data, secret_values) -> UserData:
    """Build custom user state with initialization data and secrets."""
    logger.info(f"Building user state for module {init_data.module_id}")
    
    # Use secrets if available
    initial_count = 0
    if secret_values:
        # Example: use a secret to set initial user count
        for secret in secret_values:
            if secret.key == "INITIAL_USER_COUNT":
                try:
                    initial_count = int(secret.expose_secret())
                except ValueError:
                    pass
    
    return UserData(user_count=initial_count)

# Define endpoints to announce
endpoints = [
    AnnouncedEndpoint(path="/users", methods=["GET", "POST"], auth="jwt"),
    AnnouncedEndpoint(path="/users/{user_id}", methods=["GET", "PUT", "DELETE"], auth="jwt"),
    AnnouncedEndpoint(path="/sessions", methods=["GET"], auth="jwt"),
    AnnouncedEndpoint(path="/public/info", methods=["GET"], auth=None),
]

# Configuration for Phase 2 features
tcp_config = {
    "host": "127.0.0.1",
    "port": 0,  # Auto-assign port
    "pool_size": 10,
    "timeout": 30,
    "enable_tls": False,
}

ipc_config = {
    "socket_path": "/tmp/phase2_example.sock",
    "timeout": 30,
}

database_config = {
    "type": DatabaseType.SQLITE,
    "database": "phase2_example.db",
    "pool_config": {
        "min_connections": 1,
        "max_connections": 5,
    }
}

cache_config = {
    "type": CacheType.IN_MEMORY,
    "max_size": 1000,
    "default_ttl": 300,  # 5 minutes
}

jwt_config = {
    "secret_key": "your-secret-key-here",  # In production, use a secret
    "algorithm": "HS256",
    "verify_exp": True,
}

service_capabilities = [
    "user_management",
    "session_tracking",
    "data_analytics",
]

@pywatt_module(
    # Basic configuration
    secrets=["DATABASE_URL", "JWT_SECRET", "INITIAL_USER_COUNT"],
    rotate=True,
    endpoints=endpoints,
    health="/health",
    metrics=True,
    version="v1",
    state_builder=build_user_state,
    
    # Phase 2 enhancements
    enable_tcp=True,
    enable_ipc=True,
    enable_service_discovery=True,
    enable_module_registration=True,
    enable_database=True,
    enable_cache=True,
    enable_jwt=True,
    enable_internal_messaging=True,
    
    # Configuration
    tcp_config=tcp_config,
    ipc_config=ipc_config,
    database_config=database_config,
    cache_config=cache_config,
    jwt_config=jwt_config,
    service_capabilities=service_capabilities,
)
async def create_app(state: AppState[UserData]):
    """Create the application with all Phase 2 features."""
    
    # Example FastAPI application (you would import fastapi here)
    # from fastapi import FastAPI, HTTPException, Depends
    # app = FastAPI(title="Phase 2 Example", version="1.0.0")
    
    # For this example, we'll create a simple mock app
    class MockApp:
        def __init__(self):
            self.routes = []
            self.state = state
        
        def add_route(self, path: str, handler, methods: List[str]):
            self.routes.append({"path": path, "handler": handler, "methods": methods})
    
    app = MockApp()
    
    # Demonstrate Phase 2 features
    await demonstrate_features(state)
    
    # Add route handlers that use Phase 2 features
    async def get_users():
        """Get all users from database."""
        try:
            users = await state.execute_query("SELECT * FROM users")
            return {"users": users}
        except Exception as e:
            logger.error(f"Failed to get users: {e}")
            return {"error": str(e)}
    
    async def create_user(user_data: Dict[str, Any]):
        """Create a new user."""
        try:
            # Validate JWT token (in real app, this would be middleware)
            # token = request.headers.get("Authorization", "").replace("Bearer ", "")
            # claims = await state.validate_jwt_token(token, JwtClaims)
            
            # Insert user into database
            await state.execute_query(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                [user_data["name"], user_data["email"]]
            )
            
            # Update cache
            await state.cache_set(f"user:{user_data['email']}", user_data, ttl=3600)
            
            # Update user state
            state.custom().user_count += 1
            
            # Send notification to other modules
            await state.send_message(
                "analytics:user_created",
                {"user": user_data, "timestamp": "2024-01-01T00:00:00Z"}
            )
            
            return {"message": "User created successfully"}
            
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return {"error": str(e)}
    
    async def get_user_sessions():
        """Get active user sessions."""
        try:
            # Get from cache first
            sessions = await state.cache_get("active_sessions")
            if sessions is None:
                # Fallback to database
                sessions = await state.execute_query("SELECT * FROM sessions WHERE active = 1")
                await state.cache_set("active_sessions", sessions, ttl=60)
            
            return {"sessions": sessions}
            
        except Exception as e:
            logger.error(f"Failed to get sessions: {e}")
            return {"error": str(e)}
    
    async def get_public_info():
        """Get public information (no auth required)."""
        return {
            "module_id": state.module_id,
            "version": "1.0.0",
            "user_count": state.custom().user_count,
            "available_channels": state.available_channels(),
            "features": {
                "database": state.database is not None,
                "cache": state.cache is not None,
                "jwt": state.jwt_validator is not None,
                "messaging": state.internal_messaging_client is not None,
            }
        }
    
    # Register routes
    app.add_route("/v1/users", get_users, ["GET"])
    app.add_route("/v1/users", create_user, ["POST"])
    app.add_route("/v1/sessions", get_user_sessions, ["GET"])
    app.add_route("/v1/public/info", get_public_info, ["GET"])
    
    return app

async def demonstrate_features(state: AppState[UserData]):
    """Demonstrate all Phase 2 features."""
    logger.info("=== Demonstrating Phase 2 Features ===")
    
    # 1. Secret Management
    logger.info("1. Secret Management")
    try:
        # Get a secret (will use cache if available)
        db_url = await state.get_secret("DATABASE_URL")
        logger.info(f"Retrieved database URL: {db_url[:20]}...")
        
        # Set a new secret
        await state.set_secret("TEMP_SECRET", "temporary_value", {"source": "demo"})
        logger.info("Set temporary secret")
        
    except Exception as e:
        logger.error(f"Secret management demo failed: {e}")
    
    # 2. Database Operations
    logger.info("2. Database Operations")
    try:
        # Create tables if they don't exist
        await state.execute_query("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await state.execute_query("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                session_token TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        logger.info("Database tables created/verified")
        
    except Exception as e:
        logger.error(f"Database demo failed: {e}")
    
    # 3. Cache Operations
    logger.info("3. Cache Operations")
    try:
        # Set some cache values
        await state.cache_set("demo_key", {"message": "Hello from cache!"}, ttl=300)
        await state.cache_set("user_count", state.custom().user_count)
        
        # Get cache values
        demo_value = await state.cache_get("demo_key")
        user_count = await state.cache_get("user_count")
        
        logger.info(f"Cache demo value: {demo_value}")
        logger.info(f"Cached user count: {user_count}")
        
    except Exception as e:
        logger.error(f"Cache demo failed: {e}")
    
    # 4. Service Discovery
    logger.info("4. Service Discovery")
    try:
        # Register as a service provider
        await state.register_service_provider(
            ServiceType.USER_MANAGEMENT,
            {
                "module_id": state.module_id,
                "version": "1.0.0",
                "endpoints": ["/v1/users", "/v1/sessions"],
                "capabilities": service_capabilities,
            }
        )
        logger.info("Registered as user management service provider")
        
        # Discover other service providers
        providers = await state.discover_service_providers(ServiceType.ANALYTICS)
        logger.info(f"Found {len(providers)} analytics service providers")
        
    except Exception as e:
        logger.error(f"Service discovery demo failed: {e}")
    
    # 5. Internal Messaging
    logger.info("5. Internal Messaging")
    try:
        # Send a notification to another module (if it exists)
        await state.send_message(
            "analytics:event",
            {
                "event_type": "module_started",
                "module_id": state.module_id,
                "timestamp": "2024-01-01T00:00:00Z",
                "metadata": {"user_count": state.custom().user_count}
            }
        )
        logger.info("Sent notification to analytics module")
        
        # Example of sending a request (would need target module to respond)
        # response = await state.send_request(
        #     "config:get_setting",
        #     {"setting_name": "max_users"},
        #     response_type=dict
        # )
        # logger.info(f"Got config response: {response}")
        
    except Exception as e:
        logger.error(f"Internal messaging demo failed: {e}")
    
    # 6. Channel Information
    logger.info("6. Communication Channels")
    available_channels = state.available_channels()
    logger.info(f"Available channels: {available_channels}")
    
    for channel_type in available_channels:
        capabilities = state.channel_capabilities(channel_type)
        logger.info(f"{channel_type} capabilities: {capabilities}")
    
    # 7. JWT Validation (if enabled)
    if state.jwt_validator:
        logger.info("7. JWT Validation")
        try:
            # This would normally be done with a real token
            # For demo purposes, we'll just show the validator is available
            logger.info("JWT validator is available and ready")
        except Exception as e:
            logger.error(f"JWT demo failed: {e}")
    
    logger.info("=== Phase 2 Features Demo Complete ===")

if __name__ == "__main__":
    # This would be called by the PyWatt orchestrator
    # For testing, you could run: python phase2_example.py
    logger.info("Phase 2 Example Module Starting...")
    
    # The @pywatt_module decorator handles all the initialization
    # When run by the orchestrator, this will:
    # 1. Read init data from stdin
    # 2. Initialize all Phase 2 features
    # 3. Create the app
    # 4. Announce endpoints
    # 5. Start IPC processing
    # 6. Return the app for serving
    
    # In a real deployment, the orchestrator would handle the execution
    # For local testing, you might want to create a test harness 