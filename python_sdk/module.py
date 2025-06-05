"""Module decorator and utilities for PyWatt SDK.

This module provides the @pywatt_module decorator that automates the module
initialization process, similar to the Rust SDK's #[pywatt_sdk::module] macro.

Updated to use the new bootstrap and lifecycle management functionality.
"""

import asyncio
import inspect
import logging
import sys
import os
from typing import Any, Callable, List, Optional, Dict, Union, Awaitable
from dataclasses import dataclass
from functools import wraps

# Core imports
from .core.error import BootstrapError, PyWattSDKError
from .core.logging import init_module
from .core.bootstrap import bootstrap_module
from .communication.ipc_types import EndpointAnnounce, InitBlob
from .services.server import serve_module_full, ServeOptions
from .security.typed_secret import TypedSecret

logger = logging.getLogger(__name__)


@dataclass
class AnnouncedEndpoint:
    """Information about an endpoint to announce to the orchestrator."""
    
    path: str
    methods: List[str]
    auth: Optional[str] = None
    
    def to_endpoint_info(self) -> EndpointAnnounce:
        """Convert to EndpointInfo for IPC."""
        return EndpointAnnounce(
            path=self.path,
            methods=self.methods,
            auth=self.auth
        )


def pywatt_module(
    secrets: Optional[List[str]] = None,
    rotate: bool = False,
    endpoints: Optional[List[AnnouncedEndpoint]] = None,
    health: str = "/health",
    metrics: bool = False,
    version: Optional[str] = None,
    state_builder: Optional[Callable] = None,
    config: Optional[Dict[str, Any]] = None,
    # Server options
    framework: str = "fastapi",
    bind_http: bool = True,
    specific_port: Optional[int] = None,
    listen_addr: Optional[str] = None,
    # Phase 2 enhancements (kept for backward compatibility)
    enable_tcp: bool = True,
    enable_ipc: bool = True,
    enable_service_discovery: bool = True,
    enable_module_registration: bool = True,
    enable_database: bool = False,
    enable_cache: bool = False,
    enable_jwt: bool = False,
    enable_internal_messaging: bool = True,
    tcp_config: Optional[Dict[str, Any]] = None,
    ipc_config: Optional[Dict[str, Any]] = None,
    database_config: Optional[Dict[str, Any]] = None,
    cache_config: Optional[Dict[str, Any]] = None,
    jwt_config: Optional[Dict[str, Any]] = None,
    service_capabilities: Optional[List[str]] = None,
):
    """Decorator to create a PyWatt module.
    
    This decorator automates the module initialization process using the
    new bootstrap and lifecycle management functionality.
    
    Args:
        secrets: List of secret keys to prefetch
        rotate: Whether to auto-subscribe to secret rotations
        endpoints: List of endpoints to announce
        health: Health check endpoint path
        metrics: Whether to enable metrics endpoint
        version: Version prefix for announcement paths
        state_builder: Function to build custom state
        config: Application configuration
        
        # Server options
        framework: Web framework to use ("fastapi" or "flask")
        bind_http: Whether to bind an HTTP server
        specific_port: Specific port to request from orchestrator
        listen_addr: Alternative listen address
        
        # Phase 2 enhancements (kept for backward compatibility)
        enable_tcp: Whether to enable TCP communication channel
        enable_ipc: Whether to enable IPC communication channel
        enable_service_discovery: Whether to enable service discovery
        enable_module_registration: Whether to enable module registration
        enable_database: Whether to enable database connection
        enable_cache: Whether to enable cache service
        enable_jwt: Whether to enable JWT authentication
        enable_internal_messaging: Whether to enable internal messaging
        tcp_config: TCP channel configuration
        ipc_config: IPC channel configuration
        database_config: Database configuration
        cache_config: Cache configuration
        jwt_config: JWT configuration
        service_capabilities: List of service capabilities to advertise
        
    Returns:
        Decorated function that becomes the module's main entry point
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Prepare endpoints for announcement
                announced_endpoints = []
                
                # Add user-specified endpoints
                if endpoints:
                    for endpoint in endpoints:
                        ep = endpoint.to_endpoint_info()
                        # Apply version prefix if specified
                        if version and not ep.path.startswith(health):
                            ep.path = f"/{version}{ep.path}"
                        announced_endpoints.append(ep)
                
                # Add health endpoint
                health_endpoint = EndpointAnnounce(
                    path=health,
                    methods=["GET"],
                    auth=None
                )
                announced_endpoints.append(health_endpoint)
                
                # Add metrics endpoint if enabled
                if metrics:
                    metrics_endpoint = EndpointAnnounce(
                        path="/metrics",
                        methods=["GET"],
                        auth=None
                    )
                    announced_endpoints.append(metrics_endpoint)
                
                # Create enhanced state builder that includes config
                def enhanced_state_builder(init_data: InitBlob, fetched_secrets: List[TypedSecret]) -> Any:
                    # Extract secret values for backward compatibility
                    secret_values = [s.expose_secret() for s in fetched_secrets] if fetched_secrets else []
                    
                    # Build user state
                    if state_builder:
                        if inspect.iscoroutinefunction(state_builder):
                            user_state = asyncio.run(state_builder(init_data, secret_values))
                        else:
                            user_state = state_builder(init_data, secret_values)
                    else:
                        user_state = {}
                    
                    # Add configuration to user state
                    if config:
                        if isinstance(user_state, dict):
                            user_state["config"] = config
                        else:
                            # If user state is not a dict, wrap it
                            user_state = {"user_state": user_state, "config": config}
                    
                    # Add Phase 2 configurations if specified
                    if isinstance(user_state, dict):
                        phase2_config = {}
                        if tcp_config:
                            phase2_config["tcp_config"] = tcp_config
                        if ipc_config:
                            phase2_config["ipc_config"] = ipc_config
                        if database_config:
                            phase2_config["database_config"] = database_config
                        if cache_config:
                            phase2_config["cache_config"] = cache_config
                        if jwt_config:
                            phase2_config["jwt_config"] = jwt_config
                        
                        phase2_config["enable_tcp"] = enable_tcp
                        phase2_config["enable_ipc"] = enable_ipc
                        phase2_config["enable_service_discovery"] = enable_service_discovery
                        phase2_config["enable_module_registration"] = enable_module_registration
                        phase2_config["enable_database"] = enable_database
                        phase2_config["enable_cache"] = enable_cache
                        phase2_config["enable_jwt"] = enable_jwt
                        phase2_config["enable_internal_messaging"] = enable_internal_messaging
                        phase2_config["service_capabilities"] = service_capabilities
                        
                        if phase2_config:
                            user_state["phase2_config"] = phase2_config
                    
                    return user_state
                
                # Create router builder that calls the decorated function
                def router_builder(app_state):
                    # Call the decorated function to get the application/router
                    if inspect.iscoroutinefunction(func):
                        return asyncio.run(func(app_state, *args, **kwargs))
                    else:
                        return func(app_state, *args, **kwargs)
                
                # Create serve options
                serve_options = ServeOptions(
                    bind_http=bind_http,
                    specific_port=specific_port,
                    listen_addr=listen_addr
                )
                
                # Use the new serve_module_full function
                await serve_module_full(
                    secret_keys=secrets or [],
                    endpoints=announced_endpoints,
                    state_builder=enhanced_state_builder,
                    router_builder=router_builder,
                    framework=framework,
                    options=serve_options
                )
                
            except Exception as e:
                logger.error(f"Failed to initialize PyWatt module: {e}")
                raise BootstrapError(f"module initialization failed: {e}")
        
        return wrapper
    return decorator


# Convenience function for simple modules
async def run_module(
    app_factory: Callable[[Any], Any],
    secrets: Optional[List[str]] = None,
    rotate: bool = False,
    endpoints: Optional[List[AnnouncedEndpoint]] = None,
    health: str = "/health",
    metrics: bool = False,
    version: Optional[str] = None,
    state_builder: Optional[Callable] = None,
    config: Optional[Dict[str, Any]] = None,
    framework: str = "fastapi",
    bind_http: bool = True,
    specific_port: Optional[int] = None,
    listen_addr: Optional[str] = None,
) -> None:
    """Run a PyWatt module with the given configuration.
    
    This is a convenience function for simple modules that don't need
    the decorator approach. It uses the new bootstrap and lifecycle
    management functionality.
    
    Args:
        app_factory: Function that creates the application given an AppState
        secrets: List of secret keys to prefetch
        rotate: Whether to auto-subscribe to secret rotations
        endpoints: List of endpoints to announce
        health: Health check endpoint path
        metrics: Whether to enable metrics endpoint
        version: Version prefix for announcement paths
        state_builder: Function to build custom state
        config: Application configuration
        framework: Web framework to use
        bind_http: Whether to bind an HTTP server
        specific_port: Specific port to request
        listen_addr: Alternative listen address
    """
    @pywatt_module(
        secrets=secrets,
        rotate=rotate,
        endpoints=endpoints,
        health=health,
        metrics=metrics,
        version=version,
        state_builder=state_builder,
        config=config,
        framework=framework,
        bind_http=bind_http,
        specific_port=specific_port,
        listen_addr=listen_addr,
    )
    async def module_main(app_state):
        return app_factory(app_state)
    
    await module_main()


# Helper functions for framework detection
def create_fastapi_endpoints(app: Any, endpoints: List[AnnouncedEndpoint]) -> List[AnnouncedEndpoint]:
    """Create FastAPI endpoints from the app.
    
    This function inspects a FastAPI app and creates AnnouncedEndpoint
    objects for all registered routes.
    """
    discovered = []
    try:
        # Import here to avoid dependency if not using FastAPI
        import fastapi
        from fastapi import FastAPI
        from fastapi.routing import APIRoute
        
        if isinstance(app, FastAPI):
            for route in app.routes:
                if isinstance(route, APIRoute):
                    discovered.append(AnnouncedEndpoint(
                        path=route.path,
                        methods=list(route.methods),
                        auth=None  # Would need to inspect dependencies
                    ))
    except ImportError:
        pass
    
    return discovered


def create_flask_endpoints(app: Any, endpoints: List[AnnouncedEndpoint]) -> List[AnnouncedEndpoint]:
    """Create Flask endpoints from the app.
    
    This function inspects a Flask app and creates AnnouncedEndpoint
    objects for all registered routes.
    """
    discovered = []
    try:
        # Import here to avoid dependency if not using Flask
        from flask import Flask
        
        if hasattr(app, 'url_map'):  # Flask app
            for rule in app.url_map.iter_rules():
                if rule.endpoint != 'static':
                    discovered.append(AnnouncedEndpoint(
                        path=rule.rule,
                        methods=list(rule.methods - {'HEAD', 'OPTIONS'}),
                        auth=None
                    ))
    except ImportError:
        pass
    
    return discovered


__all__ = [
    "pywatt_module",
    "AnnouncedEndpoint",
    "run_module",
    "create_fastapi_endpoints",
    "create_flask_endpoints",
] 