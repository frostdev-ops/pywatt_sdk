"""Module decorator and utilities for PyWatt SDK.

This module provides the @pywatt_module decorator that automates the module
initialization process, similar to the Rust SDK's #[pywatt_sdk::module] macro.
It also provides enhanced functionality including context managers, automatic
reconnection, and comprehensive error handling.
"""

import asyncio
import inspect
import logging
import sys
import os
from typing import Any, Callable, List, Optional, Dict, Union, Awaitable, TypeVar, Generic
from dataclasses import dataclass
from functools import wraps

# Core imports
from .core.error import (
    BootstrapError, 
    PyWattSDKError, 
    ModuleError,
    Result
)
from .core.logging import init_module
from .core.bootstrap import bootstrap_module
from .core.module import Module
from .communication.ipc_types import EndpointAnnounce, InitBlob
from .services.server import serve_module_full, ServeOptions
from .security.typed_secret import TypedSecret

logger = logging.getLogger(__name__)

T = TypeVar('T')


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
    framework: str = "fastapi",
    bind_http: bool = True,
    specific_port: Optional[int] = None,
    listen_addr: Optional[str] = None,
):
    """Decorator that transforms a function into a PyWatt module.
    
    This decorator automates the process of creating a PyWatt module, handling
    initialization, configuration, and cleanup. It is similar to the Rust SDK's
    #[pywatt_sdk::module] macro.
    
    The decorated function should accept an AppState parameter and return
    an application object (e.g., a FastAPI app).
    
    Args:
        secrets: List of secret keys to prefetch
        rotate: Whether to auto-subscribe to secret rotations
        endpoints: List of endpoints to announce
        health: Path for health endpoint
        metrics: Whether to enable metrics endpoint
        version: Version prefix for announcement paths
        state_builder: Function to build custom state
        config: Application configuration
        framework: Web framework to use (fastapi or flask)
        bind_http: Whether to bind an HTTP server
        specific_port: Specific port to request
        listen_addr: Alternative listen address
        
    Returns:
        Decorator function
        
    Examples:
        ```python
        @pywatt_module(
            secrets=["API_KEY", "DATABASE_URL"],
            rotate=True,
            metrics=True
        )
        async def module_main(app_state):
            app = FastAPI()
            
            @app.get("/api/data")
            async def get_data():
                api_key = app_state.secrets.get("API_KEY")
                return {"data": "example"}
                
            return app
        ```
    """
    def decorator(func: Callable) -> Callable:
        # Ensure target is an async function
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("pywatt_module decorator must be applied to an async function")
            
        @wraps(func)
        async def wrapper() -> None:
            # Initialize logging
            init_module()
            
            try:
                # Bootstrap the module
                bootstrap_result = await bootstrap_module(
                    secrets=secrets,
                    rotate=rotate
                )
                
                if bootstrap_result.is_err():
                    raise bootstrap_result.unwrap_err()
                    
                init, secret_client, app_state = bootstrap_result.unwrap()
                
                # Create the application using the decorated function
                app = await func(app_state)
                
                # Auto-detect and announce endpoints based on framework
                effective_endpoints = endpoints or []
                
                if not effective_endpoints and framework:
                    if framework.lower() == "fastapi":
                        if app is not None:
                            create_fastapi_endpoints(app, effective_endpoints)
                    elif framework.lower() == "flask":
                        if app is not None:
                            create_flask_endpoints(app, effective_endpoints)
                
                # Add health endpoint if not already present
                if health and all(endpoint.path != health for endpoint in effective_endpoints):
                    effective_endpoints.append(
                        AnnouncedEndpoint(path=health, methods=["GET"])
                    )
                
                # Add metrics endpoint if enabled
                if metrics:
                    metrics_path = "/metrics"
                    if all(endpoint.path != metrics_path for endpoint in effective_endpoints):
                        effective_endpoints.append(
                            AnnouncedEndpoint(path=metrics_path, methods=["GET"])
                        )
                
                # Convert to EndpointInfo objects
                endpoint_infos = [endpoint.to_endpoint_info() for endpoint in effective_endpoints]
                
                # Serve the application
                serve_options = ServeOptions(
                    bind_http=bind_http,
                    specific_port=specific_port,
                    listen_addr=listen_addr
                )
                
                await serve_module_full(
                    app=app,
                    init=init,
                    endpoints=endpoint_infos,
                    app_state=app_state,
                    options=serve_options,
                    framework=framework
                )
                
            except Exception as e:
                # Format and log the error
                if isinstance(e, PyWattSDKError):
                    logger.error(f"Module error: {e}")
                else:
                    logger.exception("Unhandled exception in module")
                sys.exit(1)
        
        # Set up the module entry point
        if inspect.iscoroutinefunction(func):
            wrapper.__module_func__ = func
            wrapper.__is_pywatt_module__ = True
            
            # Run the wrapper if this is the main module
            if func.__module__ == "__main__":
                asyncio.run(wrapper())
                
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
        
    Examples:
        ```python
        import asyncio
        from pywatt_sdk import run_module
        from fastapi import FastAPI
        
        def create_app(app_state):
            app = FastAPI()
            
            @app.get("/api/data")
            async def get_data():
                return {"data": "example"}
                
            return app
        
        if __name__ == "__main__":
            asyncio.run(run_module(
                app_factory=create_app,
                secrets=["API_KEY"],
                metrics=True
            ))
        ```
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
    async def module_main(app_state: Any) -> Any:
        return app_factory(app_state)


class ModuleApp:
    """A PyWatt module application.
    
    This class provides a convenient way to create a PyWatt module
    with context manager support, automatic reconnection, and
    comprehensive error handling.
    
    Examples:
        ```python
        from pywatt_sdk import ModuleApp
        from fastapi import FastAPI
        
        def create_app(app_state):
            app = FastAPI()
            
            @app.get("/api/data")
            async def get_data():
                return {"data": "example"}
                
            return app
        
        if __name__ == "__main__":
            app = ModuleApp(
                name="example-module",
                app_factory=create_app,
                secrets=["API_KEY"],
                metrics=True
            )
            app.run()
        ```
        
        With context manager:
        
        ```python
        async with ModuleApp(
            name="example-module",
            app_factory=create_app
        ) as app:
            # Module is running
            await app.some_task()
        # Module is automatically shut down
        ```
    """
    
    def __init__(
        self,
        name: str,
        app_factory: Callable,
        version: str = "0.1.0",
        secrets: Optional[List[str]] = None,
        rotate: bool = False,
        endpoints: Optional[List[AnnouncedEndpoint]] = None,
        health: str = "/health",
        metrics: bool = False,
        config: Optional[Dict[str, Any]] = None,
        framework: str = "fastapi",
        bind_http: bool = True,
        specific_port: Optional[int] = None,
        listen_addr: Optional[str] = None,
    ) -> None:
        """Initialize a PyWatt module application.
        
        Args:
            name: Name of the module
            app_factory: Function that creates the application given an AppState
            version: Version of the module
            secrets: List of secret keys to prefetch
            rotate: Whether to auto-subscribe to secret rotations
            endpoints: List of endpoints to announce
            health: Health check endpoint path
            metrics: Whether to enable metrics endpoint
            config: Application configuration
            framework: Web framework to use
            bind_http: Whether to bind an HTTP server
            specific_port: Specific port to request
            listen_addr: Alternative listen address
        """
        self.name = name
        self.version = version
        self.app_factory = app_factory
        self.secrets = secrets or []
        self.rotate = rotate
        self.endpoints = endpoints or []
        self.health = health
        self.metrics = metrics
        self.config = config or {}
        self.framework = framework
        self.bind_http = bind_http
        self.specific_port = specific_port
        self.listen_addr = listen_addr
        self.module = Module(name=name, version=version, config=config)
        self._app = None
        self._app_state = None
    
    async def __aenter__(self) -> "ModuleApp":
        """Async context manager entry.
        
        Starts the module when entering the context.
        
        Returns:
            The ModuleApp instance
        """
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit.
        
        Shuts down the module when exiting the context.
        
        Args:
            exc_type: Exception type, if an exception was raised
            exc_val: Exception value, if an exception was raised
            exc_tb: Exception traceback, if an exception was raised
        """
        await self.shutdown()
    
    async def start(self) -> Result[None]:
        """Start the module.
        
        Returns:
            A Result indicating success or failure
        """
        try:
            # Start the module
            module_result = await self.module.start()
            if module_result.is_err():
                return module_result
            
            # Set up app and state (simplified for this example)
            self._app_state = {"module": self.module, "secrets": {}}
            self._app = self.app_factory(self._app_state)
            
            return Result.ok(None)
        except Exception as e:
            logger.error(f"Failed to start module app: {e}")
            if isinstance(e, PyWattSDKError):
                return Result.err(e)
            return Result.err(ModuleError(f"Failed to start module app: {e}", cause=e))
    
    async def shutdown(self) -> Result[None]:
        """Shut down the module.
        
        Returns:
            A Result indicating success or failure
        """
        return await self.module.shutdown()
    
    def run(self) -> None:
        """Run the module synchronously.
        
        This is a convenience method for running the module in a 
        synchronous context.
        """
        async def _async_run() -> None:
            await self.start()
            try:
                # Run until interrupted
                await self.module.run()
            finally:
                await self.shutdown()
        
        # Run the async function synchronously
        asyncio.run(_async_run())


# Helper functions for framework detection
def create_fastapi_endpoints(app: Any, endpoints: List[AnnouncedEndpoint]) -> None:
    """Create FastAPI endpoints from the app.
    
    This function inspects a FastAPI app and creates AnnouncedEndpoint
    objects for all registered routes.
    
    Args:
        app: FastAPI application
        endpoints: List to add endpoints to
    """
    try:
        # Check if app has routes
        if not hasattr(app, "routes"):
            return
            
        for route in app.routes:
            # Skip endpoints without paths
            if not hasattr(route, "path"):
                continue
                
            path = route.path
            
            # Get methods
            methods = []
            if hasattr(route, "methods"):
                methods = list(route.methods)
            else:
                # Default to GET
                methods = ["GET"]
            
            # Add endpoint if not already present
            if not any(e.path == path for e in endpoints):
                endpoints.append(AnnouncedEndpoint(
                    path=path,
                    methods=methods
                ))
    except Exception as e:
        logger.warning(f"Error creating FastAPI endpoints: {e}")

    
def create_flask_endpoints(app: Any, endpoints: List[AnnouncedEndpoint]) -> None:
    """Create Flask endpoints from the app.
    
    This function inspects a Flask app and creates AnnouncedEndpoint
    objects for all registered routes.
    
    Args:
        app: Flask application
        endpoints: List to add endpoints to
    """
    try:
        # Check if app has url_map
        if not hasattr(app, "url_map"):
            return
            
        for rule in app.url_map.iter_rules():
            path = rule.rule
            methods = list(rule.methods - {"HEAD", "OPTIONS"})
            
            # Add endpoint if not already present
            if not any(e.path == path for e in endpoints):
                endpoints.append(AnnouncedEndpoint(
                    path=path,
                    methods=methods
                ))
    except Exception as e:
        logger.warning(f"Error creating Flask endpoints: {e}")


__all__ = [
    "pywatt_module",
    "AnnouncedEndpoint",
    "run_module",
    "ModuleApp",
    "Module",
]
