"""HTTP over IPC utilities for PyWatt modules.

This module provides standardized utilities for handling HTTP requests and responses
over the PyWatt IPC mechanism. It simplifies the process of routing requests,
formatting responses, and handling errors in a consistent way across modules.
"""

import asyncio
import json
import time
import uuid
from typing import Dict, Any, Optional, Callable, Awaitable, List
from dataclasses import dataclass, field
from collections import defaultdict
import logging

from ..communication.ipc_types import IpcHttpRequest, IpcHttpResponse
from ..core.error import NetworkError

logger = logging.getLogger(__name__)


@dataclass
class HttpIpcMetrics:
    """Metrics for HTTP-IPC performance monitoring."""
    requests_received: int = 0
    responses_sent: int = 0
    errors_encountered: int = 0
    total_response_time_ms: float = 0.0
    
    @property
    def avg_response_time_ms(self) -> float:
        """Calculate average response time."""
        if self.responses_sent == 0:
            return 0.0
        return self.total_response_time_ms / self.responses_sent


@dataclass
class ApiResponse:
    """Standardized API response structure."""
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    
    def to_ipc_response(self, request_id: str) -> IpcHttpResponse:
        """Convert to IPC HTTP response."""
        return IpcHttpResponse(
            request_id=request_id,
            status_code=self.status_code,
            headers=self.headers,
            body=self.body
        )


# Global channels for HTTP request/response handling
_http_request_queue: asyncio.Queue[IpcHttpRequest] = asyncio.Queue(maxsize=256)
_http_response_handlers: Dict[str, asyncio.Future[IpcHttpResponse]] = {}
_http_ipc_metrics = HttpIpcMetrics()


class HttpIpcRouter:
    """Router for handling HTTP requests over IPC."""
    
    def __init__(self):
        """Initialize the HTTP IPC router."""
        self.routes: Dict[str, Dict[str, Callable]] = defaultdict(dict)
        self.middleware: List[Callable] = []
        self.error_handlers: Dict[int, Callable] = {}
        self.running = False
        self._request_task: Optional[asyncio.Task] = None
    
    def route(self, path: str, methods: List[str] = None):
        """Decorator for registering route handlers."""
        if methods is None:
            methods = ["GET"]
        
        def decorator(handler: Callable):
            for method in methods:
                self.routes[path][method.upper()] = handler
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
    
    async def start(self):
        """Start the HTTP IPC router."""
        if self.running:
            return
        
        self.running = True
        self._request_task = asyncio.create_task(self._process_requests())
        logger.info("HTTP IPC router started")
    
    async def stop(self):
        """Stop the HTTP IPC router."""
        if not self.running:
            return
        
        self.running = False
        if self._request_task:
            self._request_task.cancel()
            try:
                await self._request_task
            except asyncio.CancelledError:
                pass
        
        logger.info("HTTP IPC router stopped")
    
    async def _process_requests(self):
        """Process incoming HTTP requests."""
        while self.running:
            try:
                request = await _http_request_queue.get()
                asyncio.create_task(self._handle_request(request))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing HTTP IPC request: {e}")
    
    async def _handle_request(self, request: IpcHttpRequest):
        """Handle a single HTTP request."""
        start_time = time.time()
        _http_ipc_metrics.requests_received += 1
        
        try:
            # Apply middleware
            for middleware in self.middleware:
                try:
                    await middleware(request)
                except Exception as e:
                    logger.warning(f"Middleware error: {e}")
            
            # Find route handler
            handler = self._find_handler(request.uri, request.method)
            
            if handler:
                # Execute handler
                response = await handler(request)
                if not isinstance(response, ApiResponse):
                    # Convert simple responses
                    if isinstance(response, dict):
                        response = json_response(response)
                    elif isinstance(response, str):
                        response = ApiResponse(200, body=response.encode())
                    else:
                        response = ApiResponse(200, body=str(response).encode())
            else:
                # No handler found
                response = not_found(f"No handler for {request.method} {request.uri}")
            
        except Exception as e:
            logger.error(f"Error handling HTTP IPC request: {e}")
            response = error_response(500, f"Internal server error: {e}")
            _http_ipc_metrics.errors_encountered += 1
        
        # Send response
        ipc_response = response.to_ipc_response(request.request_id)
        await send_http_response(ipc_response)
        
        # Update metrics
        response_time = (time.time() - start_time) * 1000
        _http_ipc_metrics.responses_sent += 1
        _http_ipc_metrics.total_response_time_ms += response_time
        
        logger.debug(f"Handled {request.method} {request.uri} -> {response.status_code} ({response_time:.1f}ms)")
    
    def _find_handler(self, uri: str, method: str) -> Optional[Callable]:
        """Find the appropriate handler for a request."""
        # Simple exact match for now
        # In a full implementation, this would support path parameters
        path = uri.split('?')[0]  # Remove query parameters
        
        if path in self.routes and method.upper() in self.routes[path]:
            return self.routes[path][method.upper()]
        
        return None


# Global router instance
_global_router: Optional[HttpIpcRouter] = None


def get_global_router() -> HttpIpcRouter:
    """Get the global HTTP IPC router."""
    global _global_router
    if _global_router is None:
        _global_router = HttpIpcRouter()
    return _global_router


async def subscribe_http_requests() -> asyncio.Queue[IpcHttpRequest]:
    """Subscribe to HTTP requests over IPC."""
    return _http_request_queue


async def send_http_response(response: IpcHttpResponse) -> None:
    """Send an HTTP response over IPC."""
    # In a real implementation, this would send via the IPC channel
    # For now, we'll use a simple mechanism
    if response.request_id in _http_response_handlers:
        future = _http_response_handlers.pop(response.request_id)
        if not future.done():
            future.set_result(response)


async def handle_http_request(request: IpcHttpRequest) -> None:
    """Handle an incoming HTTP request."""
    await _http_request_queue.put(request)


async def send_http_request(request: IpcHttpRequest, timeout: float = 30.0) -> IpcHttpResponse:
    """Send an HTTP request and wait for response."""
    # Create future for response
    future: asyncio.Future[IpcHttpResponse] = asyncio.Future()
    _http_response_handlers[request.request_id] = future
    
    try:
        # Send request (in real implementation, this would go via IPC)
        await handle_http_request(request)
        
        # Wait for response
        response = await asyncio.wait_for(future, timeout=timeout)
        return response
        
    except asyncio.TimeoutError:
        _http_response_handlers.pop(request.request_id, None)
        raise NetworkError(f"HTTP request {request.request_id} timed out")
    except Exception as e:
        _http_response_handlers.pop(request.request_id, None)
        raise NetworkError(f"HTTP request failed: {e}")


# Helper functions for creating responses

def json_response(data: Any, status_code: int = 200) -> ApiResponse:
    """Create a JSON response."""
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode()
    return ApiResponse(status_code, headers, body)


def success(data: Any = None) -> ApiResponse:
    """Create a success response."""
    response_data = {"success": True}
    if data is not None:
        response_data["data"] = data
    return json_response(response_data)


def error_response(status_code: int, message: str, details: Any = None) -> ApiResponse:
    """Create an error response."""
    response_data = {"error": message}
    if details is not None:
        response_data["details"] = details
    return json_response(response_data, status_code)


def not_found(message: str = "Not found") -> ApiResponse:
    """Create a 404 not found response."""
    return error_response(404, message)


def bad_request(message: str = "Bad request") -> ApiResponse:
    """Create a 400 bad request response."""
    return error_response(400, message)


def internal_error(message: str = "Internal server error") -> ApiResponse:
    """Create a 500 internal server error response."""
    return error_response(500, message)


def parse_json_body(request: IpcHttpRequest) -> Any:
    """Parse JSON body from request."""
    if not request.body:
        raise ValueError("No body in request")
    
    try:
        return json.loads(request.body.decode())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in request body: {e}")


def get_query_params(request: IpcHttpRequest) -> Dict[str, str]:
    """Extract query parameters from request URI."""
    params = {}
    
    if '?' in request.uri:
        query_string = request.uri.split('?', 1)[1]
        for pair in query_string.split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                params[key] = value
    
    return params


def get_metrics() -> HttpIpcMetrics:
    """Get HTTP IPC metrics."""
    return _http_ipc_metrics


def reset_metrics() -> None:
    """Reset HTTP IPC metrics."""
    global _http_ipc_metrics
    _http_ipc_metrics = HttpIpcMetrics() 