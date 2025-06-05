# Services Layer for PyWatt Python SDK
# This module provides high-level services like registration, service discovery, and server utilities

from .registration import (
    ModuleInfo, Endpoint, Capabilities, HealthStatus, RegisteredModule,
    RegistrationError, register_module, unregister_module, heartbeat,
    advertise_capabilities, start_heartbeat_loop
)
from .service_discovery import (
    ServiceDiscoveryClient, ServiceProviderInfo, ServiceType,
    ServiceDiscoveryError, ServiceProvider
)
from .router_discovery import (
    discover_fastapi_routes,
    discover_flask_routes,
    discover_starlette_routes,
    RouteInfo
)
from .server import (
    ServeOptions, ServerManager, FastAPIServerManager, FlaskServerManager,
    get_server_manager, set_pre_allocated_port, get_pre_allocated_port,
    negotiate_port, serve_module, serve_with_options, serve_module_full,
    serve_module_with_lifecycle
)

# Import model_manager components
from . import model_manager

__all__ = [
    # Registration
    'ModuleInfo',
    'Endpoint', 
    'Capabilities',
    'HealthStatus',
    'RegisteredModule',
    'RegistrationError',
    'register_module',
    'unregister_module',
    'heartbeat',
    'advertise_capabilities',
    'start_heartbeat_loop',
    
    # Service Discovery
    'ServiceDiscoveryClient',
    'ServiceProviderInfo',
    'ServiceType',
    'ServiceDiscoveryError',
    'ServiceProvider',
    
    # Router Discovery
    'discover_fastapi_routes',
    'discover_flask_routes',
    'discover_starlette_routes',
    'RouteInfo',
    
    # Server
    'ServeOptions',
    'ServerManager',
    'FastAPIServerManager',
    'FlaskServerManager',
    'get_server_manager',
    'set_pre_allocated_port',
    'get_pre_allocated_port',
    'negotiate_port',
    'serve_module',
    'serve_with_options',
    'serve_module_full',
    'serve_module_with_lifecycle',
    
    # Model Manager
    'model_manager',
] 