"""HTTP-over-TCP utilities for PyWatt modules.

This module provides standardized utilities for handling HTTP requests and responses
over TCP connections. It simplifies the process of routing requests, formatting responses,
and handling errors in a consistent way across modules.
"""

import asyncio
import json
import uuid
from typing import Dict, Any, Optional, Callable, Awaitable, List, Union
from dataclasses import dataclass, field
from collections import defaultdict
import logging
from urllib.parse import urlparse, parse_qs

import aiohttp
from aiohttp import web

from ..core.error import NetworkError

logger = logging.getLogger(__name__)


@dataclass
class HttpTcpRequest:
    """HTTP request transported over TCP."""
    request_id: str
    method: str
    uri: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    
    @classmethod
    def new(cls, method: str, uri: str) -> 'HttpTcpRequest':
        """Create a new HTTP request."""
        return cls(
            request_id=str(uuid.uuid4()),
            method=method.upper(),
            uri=uri
        )
    
    def with_header(self, key: str, value: str) -> 'HttpTcpRequest':
        """Add a header to the request."""
        self.headers[key] = value
        return self
    
    def with_headers(self, headers: Dict[str, str]) -> 'HttpTcpRequest':
        """Add multiple headers to the request."""
        self.headers.update(headers)
        return self
    
    def with_body(self, body: Union[str, bytes, Dict[str, Any]]) -> 'HttpTcpRequest':
        """Set the request body."""
        if isinstance(body, str):
            self.body = body.encode()
        elif isinstance(body, dict):
            self.body = json.dumps(body).encode()
            self.headers["Content-Type"] = "application/json"
        else:
            self.body = body
        return self
    
    def with_request_id(self, request_id: str) -> 'HttpTcpRequest':
        """Set the request ID."""
        self.request_id = request_id
        return self
    
    def header(self, key: str) -> Optional[str]:
        """Get a specific header."""
        return self.headers.get(key)
    
    def query_params(self) -> Dict[str, List[str]]:
        """Parse query parameters from the URI."""
        parsed = urlparse(self.uri)
        return parse_qs(parsed.query)
    
    def query_param(self, key: str) -> Optional[str]:
        """Get a specific query parameter."""
        params = self.query_params()
        values = params.get(key, [])
        return values[0] if values else None


@dataclass
class HttpTcpResponse:
    """HTTP response transported over TCP."""
    request_id: str
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    
    @classmethod
    def new(cls, request_id: str, status_code: int) -> 'HttpTcpResponse':
        """Create a new HTTP response."""
        return cls(request_id=request_id, status_code=status_code)
    
    def with_header(self, key: str, value: str) -> 'HttpTcpResponse':
        """Add a header to the response."""
        self.headers[key] = value
        return self
    
    def with_headers(self, headers: Dict[str, str]) -> 'HttpTcpResponse':
        """Add multiple headers to the response."""
        self.headers.update(headers)
        return self
    
    def with_body(self, body: Union[str, bytes, Dict[str, Any]]) -> 'HttpTcpResponse':
        """Set the response body."""
        if isinstance(body, str):
            self.body = body.encode()
        elif isinstance(body, dict):
            self.body = json.dumps(body).encode()
            self.headers["Content-Type"] = "application/json"
        else:
            self.body = body
        return self
    
    def header(self, key: str) -> Optional[str]:
        """Get a specific header."""
        return self.headers.get(key)


class HttpTcpClient:
    """HTTP client for making requests over TCP."""
    
    def __init__(self, base_url: str = "", timeout: float = 30.0):
        """Initialize the HTTP TCP client."""
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def start(self):
        """Start the HTTP client session."""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
    
    async def close(self):
        """Close the HTTP client session."""
        if self._session:
            await self._session.close()
            self._session = None
    
    async def send_request(self, request: HttpTcpRequest) -> HttpTcpResponse:
        """Send an HTTP request and return the response."""
        if not self._session:
            await self.start()
        
        url = request.uri
        if not url.startswith('http'):
            url = f"{self.base_url}{url}"
        
        try:
            async with self._session.request(
                method=request.method,
                url=url,
                headers=request.headers,
                data=request.body
            ) as resp:
                body = await resp.read()
                headers = dict(resp.headers)
                
                return HttpTcpResponse(
                    request_id=request.request_id,
                    status_code=resp.status,
                    headers=headers,
                    body=body
                )
        
        except Exception as e:
            raise NetworkError(f"HTTP request failed: {e}")
    
    async def get(self, uri: str, headers: Dict[str, str] = None) -> HttpTcpResponse:
        """Make a GET request."""
        request = HttpTcpRequest.new("GET", uri)
        if headers:
            request.with_headers(headers)
        return await self.send_request(request)
    
    async def post(self, uri: str, data: Any = None, headers: Dict[str, str] = None) -> HttpTcpResponse:
        """Make a POST request."""
        request = HttpTcpRequest.new("POST", uri)
        if headers:
            request.with_headers(headers)
        if data:
            request.with_body(data)
        return await self.send_request(request)
    
    async def put(self, uri: str, data: Any = None, headers: Dict[str, str] = None) -> HttpTcpResponse:
        """Make a PUT request."""
        request = HttpTcpRequest.new("PUT", uri)
        if headers:
            request.with_headers(headers)
        if data:
            request.with_body(data)
        return await self.send_request(request)
    
    async def delete(self, uri: str, headers: Dict[str, str] = None) -> HttpTcpResponse:
        """Make a DELETE request."""
        request = HttpTcpRequest.new("DELETE", uri)
        if headers:
            request.with_headers(headers)
        return await self.send_request(request)


@dataclass
class Route:
    """HTTP route definition."""
    path: str
    method: str
    handler: Callable
    middleware: List[Callable] = field(default_factory=list)


class HttpTcpRouter:
    """Router for handling HTTP requests over TCP."""
    
    def __init__(self):
        """Initialize the HTTP TCP router."""
        self.routes: List[Route] = []
        self.middleware: List[Callable] = []
        self.error_handlers: Dict[int, Callable] = {}
        self.app: Optional[web.Application] = None
    
    def route(self, path: str, methods: List[str] = None):
        """Decorator for registering route handlers."""
        if methods is None:
            methods = ["GET"]
        
        def decorator(handler: Callable):
            for method in methods:
                route = Route(path=path, method=method.upper(), handler=handler)
                self.routes.append(route)
            return handler
        
        return decorator
    
    def get(self, path: str):
        """Decorator for GET routes."""
        return self.route(path, ["GET"])
    
    def post(self, path: str):
        """Decorator for POST routes."""
        return self.route(path, ["POST"])
    
    def put(self, path: str):
        """Decorator for PUT routes."""
        return self.route(path, ["PUT"])
    
    def delete(self, path: str):
        """Decorator for DELETE routes."""
        return self.route(path, ["DELETE"])
    
    def middleware(self, func: Callable):
        """Register middleware function."""
        self.middleware.append(func)
        return func
    
    def error_handler(self, status_code: int):
        """Decorator for error handlers."""
        def decorator(handler: Callable):
            self.error_handlers[status_code] = handler
            return handler
        return decorator
    
    def build_app(self) -> web.Application:
        """Build the aiohttp application."""
        app = web.Application()
        
        # Add routes
        for route in self.routes:
            app.router.add_route(
                route.method,
                route.path,
                self._wrap_handler(route.handler)
            )
        
        # Add middleware
        for middleware in self.middleware:
            app.middlewares.append(self._wrap_middleware(middleware))
        
        self.app = app
        return app
    
    def _wrap_handler(self, handler: Callable):
        """Wrap a handler for aiohttp compatibility."""
        async def wrapped(request: web.Request) -> web.Response:
            try:
                # Convert aiohttp request to HttpTcpRequest
                body = await request.read()
                tcp_request = HttpTcpRequest(
                    request_id=str(uuid.uuid4()),
                    method=request.method,
                    uri=str(request.url),
                    headers=dict(request.headers),
                    body=body if body else None
                )
                
                # Call handler
                result = await handler(tcp_request)
                
                # Convert result to aiohttp response
                if isinstance(result, HttpTcpResponse):
                    return web.Response(
                        status=result.status_code,
                        headers=result.headers,
                        body=result.body
                    )
                elif isinstance(result, dict):
                    return web.json_response(result)
                elif isinstance(result, str):
                    return web.Response(text=result)
                else:
                    return web.Response(text=str(result))
            
            except Exception as e:
                logger.error(f"Error in HTTP TCP handler: {e}")
                return web.Response(status=500, text=f"Internal server error: {e}")
        
        return wrapped
    
    def _wrap_middleware(self, middleware: Callable):
        """Wrap middleware for aiohttp compatibility."""
        async def wrapped(request: web.Request, handler):
            try:
                # Apply middleware
                await middleware(request)
                return await handler(request)
            except Exception as e:
                logger.warning(f"Middleware error: {e}")
                return await handler(request)
        
        return wrapped


async def start_http_server(
    router: HttpTcpRouter,
    host: str = "0.0.0.0",
    port: int = 8080
) -> web.AppRunner:
    """Start an HTTP server with the given router."""
    app = router.build_app()
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    logger.info(f"HTTP TCP server started on {host}:{port}")
    return runner


async def serve(
    router: HttpTcpRouter,
    host: str = "0.0.0.0",
    port: int = 8080
) -> None:
    """Serve HTTP requests using the router."""
    runner = await start_http_server(router, host, port)
    
    try:
        # Keep the server running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down HTTP TCP server")
    finally:
        await runner.cleanup()


# Helper functions for creating responses

def json_response(data: Any, status_code: int = 200) -> HttpTcpResponse:
    """Create a JSON response."""
    response = HttpTcpResponse.new("", status_code)
    response.with_body(data)
    return response


def text_response(text: str, status_code: int = 200) -> HttpTcpResponse:
    """Create a text response."""
    response = HttpTcpResponse.new("", status_code)
    response.with_header("Content-Type", "text/plain")
    response.with_body(text)
    return response


def error_response(status_code: int, message: str) -> HttpTcpResponse:
    """Create an error response."""
    return json_response({"error": message}, status_code)


def not_found(message: str = "Not found") -> HttpTcpResponse:
    """Create a 404 not found response."""
    return error_response(404, message)


def bad_request(message: str = "Bad request") -> HttpTcpResponse:
    """Create a 400 bad request response."""
    return error_response(400, message)


def internal_error(message: str = "Internal server error") -> HttpTcpResponse:
    """Create a 500 internal server error response."""
    return error_response(500, message) 