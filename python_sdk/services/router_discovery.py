"""
Router discovery module for PyWatt Python SDK.

This module provides functionality to automatically discover and extract endpoints
from popular Python web frameworks (FastAPI, Flask, Starlette) and convert them
to AnnouncedEndpoint format for orchestrator registration.
"""

import inspect
import logging
from typing import List, Dict, Set, Optional, Any, Union
from dataclasses import dataclass

from ..communication.ipc_types import EndpointAnnounce

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredEndpoint:
    """Represents a discovered endpoint from a web framework."""
    path: str
    methods: List[str]
    auth: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None


def normalize_method(method: str) -> str:
    """Normalize HTTP method names to uppercase standard format."""
    return method.upper()


def has_path_parameters(path: str) -> bool:
    """Check if a path contains parameter placeholders."""
    return ':' in path or '{' in path or '<' in path or '*' in path


def extract_base_path(path: str) -> str:
    """Extract base path without parameters for grouping."""
    # Handle different parameter formats
    for param_char in [':', '{', '<', '*']:
        if param_char in path:
            pos = path.find(param_char)
            return path[:pos]
    return path


def deduplicate_endpoints(endpoints: List[DiscoveredEndpoint]) -> List[DiscoveredEndpoint]:
    """Deduplicate endpoints by path and merge methods."""
    endpoint_map: Dict[str, DiscoveredEndpoint] = {}
    
    for endpoint in endpoints:
        if endpoint.path in endpoint_map:
            # Merge methods
            existing = endpoint_map[endpoint.path]
            existing.methods.extend(endpoint.methods)
            existing.methods = sorted(list(set(existing.methods)))
        else:
            endpoint_map[endpoint.path] = DiscoveredEndpoint(
                path=endpoint.path,
                methods=sorted(list(set(endpoint.methods))),
                auth=endpoint.auth,
                metadata=endpoint.metadata
            )
    
    return sorted(endpoint_map.values(), key=lambda x: x.path)


def discover_fastapi_endpoints(app) -> List[DiscoveredEndpoint]:
    """Discover endpoints from a FastAPI application."""
    try:
        from fastapi import FastAPI
        from fastapi.routing import APIRoute, APIRouter
    except ImportError:
        logger.warning("FastAPI not available for endpoint discovery")
        return []
    
    if not isinstance(app, FastAPI):
        logger.warning("App is not a FastAPI instance")
        return []
    
    endpoints = []
    
    def extract_routes(router, prefix: str = ""):
        """Recursively extract routes from FastAPI router."""
        for route in router.routes:
            if isinstance(route, APIRoute):
                # Get the full path
                path = prefix + route.path
                
                # Convert FastAPI path parameters to standard format
                # FastAPI uses {param} format, convert to :param
                if '{' in path and '}' in path:
                    import re
                    path = re.sub(r'\{([^}]+)\}', r':\1', path)
                
                # Get methods
                methods = [normalize_method(method) for method in route.methods]
                methods = [m for m in methods if m != "HEAD"]  # Filter out HEAD
                
                # Determine auth requirements (basic heuristic)
                auth = None
                if hasattr(route, 'dependencies') and route.dependencies:
                    # Check if any dependency looks like auth
                    for dep in route.dependencies:
                        if hasattr(dep, 'dependency'):
                            dep_name = getattr(dep.dependency, '__name__', str(dep.dependency))
                            if any(auth_term in dep_name.lower() for auth_term in ['auth', 'jwt', 'token', 'security']):
                                auth = "jwt"
                                break
                
                endpoints.append(DiscoveredEndpoint(
                    path=path,
                    methods=methods,
                    auth=auth
                ))
            
            elif hasattr(route, 'routes'):  # Sub-router
                sub_prefix = prefix + getattr(route, 'prefix', '')
                extract_routes(route, sub_prefix)
    
    extract_routes(app.router)
    return deduplicate_endpoints(endpoints)


def discover_flask_endpoints(app) -> List[DiscoveredEndpoint]:
    """Discover endpoints from a Flask application."""
    try:
        from flask import Flask
    except ImportError:
        logger.warning("Flask not available for endpoint discovery")
        return []
    
    if not isinstance(app, Flask):
        logger.warning("App is not a Flask instance")
        return []
    
    endpoints = []
    
    for rule in app.url_map.iter_rules():
        # Get the path
        path = rule.rule
        
        # Convert Flask path parameters to standard format
        # Flask uses <param> format, convert to :param
        if '<' in path and '>' in path:
            import re
            path = re.sub(r'<[^:>]*:?([^>]+)>', r':\1', path)
        
        # Get methods (exclude OPTIONS and HEAD)
        methods = [normalize_method(method) for method in rule.methods]
        methods = [m for m in methods if m not in ["OPTIONS", "HEAD"]]
        
        if not methods:
            continue
        
        # Determine auth requirements (basic heuristic)
        auth = None
        endpoint_func = app.view_functions.get(rule.endpoint)
        if endpoint_func:
            # Check if function has auth decorators
            func_name = getattr(endpoint_func, '__name__', '')
            if any(auth_term in func_name.lower() for auth_term in ['auth', 'jwt', 'token', 'protected']):
                auth = "jwt"
            
            # Check for common auth decorators in the function's attributes
            if hasattr(endpoint_func, '__wrapped__'):
                # Function is decorated, might be auth-related
                auth = "jwt"
        
        endpoints.append(DiscoveredEndpoint(
            path=path,
            methods=methods,
            auth=auth
        ))
    
    return deduplicate_endpoints(endpoints)


def discover_starlette_endpoints(app) -> List[DiscoveredEndpoint]:
    """Discover endpoints from a Starlette application."""
    try:
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
    except ImportError:
        logger.warning("Starlette not available for endpoint discovery")
        return []
    
    if not isinstance(app, Starlette):
        logger.warning("App is not a Starlette instance")
        return []
    
    endpoints = []
    
    def extract_routes(routes, prefix: str = ""):
        """Recursively extract routes from Starlette router."""
        for route in routes:
            if isinstance(route, Route):
                # Get the full path
                path = prefix + route.path
                
                # Convert Starlette path parameters to standard format
                # Starlette uses {param} format, convert to :param
                if '{' in path and '}' in path:
                    import re
                    path = re.sub(r'\{([^}]+)\}', r':\1', path)
                
                # Get methods
                methods = [normalize_method(method) for method in route.methods]
                methods = [m for m in methods if m != "HEAD"]  # Filter out HEAD
                
                # Basic auth detection (limited for Starlette)
                auth = None
                if hasattr(route, 'endpoint'):
                    endpoint_name = getattr(route.endpoint, '__name__', str(route.endpoint))
                    if any(auth_term in endpoint_name.lower() for auth_term in ['auth', 'jwt', 'token', 'protected']):
                        auth = "jwt"
                
                endpoints.append(DiscoveredEndpoint(
                    path=path,
                    methods=methods,
                    auth=auth
                ))
            
            elif isinstance(route, Mount):
                # Mounted sub-application
                sub_prefix = prefix + route.path.rstrip('/')
                if hasattr(route.app, 'routes'):
                    extract_routes(route.app.routes, sub_prefix)
    
    extract_routes(app.routes)
    return deduplicate_endpoints(endpoints)


def discover_endpoints_from_app(app: Any) -> List[DiscoveredEndpoint]:
    """Discover endpoints from any supported web framework application.
    
    Args:
        app: Web application instance (FastAPI, Flask, or Starlette)
        
    Returns:
        List of discovered endpoints
    """
    # Try FastAPI first
    try:
        from fastapi import FastAPI
        if isinstance(app, FastAPI):
            logger.debug("Discovering endpoints from FastAPI application")
            return discover_fastapi_endpoints(app)
    except ImportError:
        pass
    
    # Try Flask
    try:
        from flask import Flask
        if isinstance(app, Flask):
            logger.debug("Discovering endpoints from Flask application")
            return discover_flask_endpoints(app)
    except ImportError:
        pass
    
    # Try Starlette
    try:
        from starlette.applications import Starlette
        if isinstance(app, Starlette):
            logger.debug("Discovering endpoints from Starlette application")
            return discover_starlette_endpoints(app)
    except ImportError:
        pass
    
    logger.warning(f"Unsupported application type: {type(app)}")
    return []


def announce_from_router(app: Any) -> List[EndpointAnnounce]:
    """Discover endpoints from a web framework application and convert to announcement format.
    
    This is the main function for endpoint discovery, similar to the Rust SDK's
    announce_from_router function.
    
    Args:
        app: Web application instance (FastAPI, Flask, or Starlette)
        
    Returns:
        List of EndpointAnnounce objects ready for orchestrator announcement
        
    Example:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> app.get("/users/{user_id}")(lambda user_id: {"user_id": user_id})
        >>> endpoints = announce_from_router(app)
        >>> print(endpoints[0].path)  # "/users/:user_id"
    """
    discovered = discover_endpoints_from_app(app)
    
    # Convert to EndpointAnnounce format
    announced = []
    for endpoint in discovered:
        announced.append(EndpointAnnounce(
            path=endpoint.path,
            methods=endpoint.methods,
            auth=endpoint.auth
        ))
    
    logger.info(f"Discovered {len(announced)} endpoints from application")
    return announced


def discover_endpoints(app: Any) -> List[EndpointAnnounce]:
    """Alternative discovery function with enhanced capabilities.
    
    This function provides the same functionality as announce_from_router
    but with additional common endpoints added.
    
    Args:
        app: Web application instance
        
    Returns:
        List of EndpointAnnounce objects
    """
    endpoints = announce_from_router(app)
    
    # Add common endpoints that might not be automatically discovered
    common_endpoints = [
        EndpointAnnounce(
            path="/health",
            methods=["GET"],
            auth=None
        ),
        EndpointAnnounce(
            path="/metrics",
            methods=["GET"],
            auth=None
        ),
        EndpointAnnounce(
            path="/info",
            methods=["GET"],
            auth=None
        ),
    ]
    
    # Only add common endpoints if they don't already exist
    existing_paths = {ep.path for ep in endpoints}
    for common_ep in common_endpoints:
        if common_ep.path not in existing_paths:
            endpoints.append(common_ep)
    
    # Sort for consistent ordering
    endpoints.sort(key=lambda x: x.path)
    
    logger.info(f"Enhanced discovery found {len(endpoints)} total endpoints")
    return endpoints


def discover_endpoints_advanced(app: Any) -> List[EndpointAnnounce]:
    """Advanced endpoint discovery with pattern matching and heuristics.
    
    This function provides the most comprehensive discovery by analyzing
    the application structure and making intelligent assumptions about
    common patterns.
    
    Args:
        app: Web application instance
        
    Returns:
        List of EndpointAnnounce objects
    """
    endpoints = discover_endpoints(app)
    
    # Analyze patterns and add missing common API endpoints
    has_api_prefix = any(ep.path.startswith('/api/') for ep in endpoints)
    
    if has_api_prefix:
        # Add common API endpoints
        api_endpoints = [
            EndpointAnnounce(
                path="/api/status",
                methods=["GET"],
                auth=None
            ),
            EndpointAnnounce(
                path="/api/version",
                methods=["GET"],
                auth=None
            ),
        ]
        
        existing_paths = {ep.path for ep in endpoints}
        for api_ep in api_endpoints:
            if api_ep.path not in existing_paths:
                endpoints.append(api_ep)
    
    # Enhance auth detection based on patterns
    for endpoint in endpoints:
        if endpoint.auth is None:
            # Apply heuristics for auth requirements
            if (endpoint.path.startswith('/api/') and 
                endpoint.path not in ['/api/status', '/api/version', '/api/health', '/api/info']):
                endpoint.auth = "jwt"
            elif any(protected in endpoint.path.lower() for protected in ['admin', 'private', 'secure']):
                endpoint.auth = "jwt"
    
    # Sort for consistent ordering
    endpoints.sort(key=lambda x: x.path)
    
    logger.info(f"Advanced discovery found {len(endpoints)} total endpoints with enhanced auth detection")
    return endpoints


# Convenience functions for specific frameworks

def announce_fastapi_endpoints(app) -> List[EndpointAnnounce]:
    """Convenience function specifically for FastAPI applications."""
    discovered = discover_fastapi_endpoints(app)
    return [EndpointAnnounce(path=ep.path, methods=ep.methods, auth=ep.auth) for ep in discovered]


def announce_flask_endpoints(app) -> List[EndpointAnnounce]:
    """Convenience function specifically for Flask applications."""
    discovered = discover_flask_endpoints(app)
    return [EndpointAnnounce(path=ep.path, methods=ep.methods, auth=ep.auth) for ep in discovered]


def announce_starlette_endpoints(app) -> List[EndpointAnnounce]:
    """Convenience function specifically for Starlette applications."""
    discovered = discover_starlette_endpoints(app)
    return [EndpointAnnounce(path=ep.path, methods=ep.methods, auth=ep.auth) for ep in discovered]


# Legacy aliases for backward compatibility
discover_fastapi_routes = discover_fastapi_endpoints
discover_flask_routes = discover_flask_endpoints
discover_starlette_routes = discover_starlette_endpoints
RouteInfo = DiscoveredEndpoint 