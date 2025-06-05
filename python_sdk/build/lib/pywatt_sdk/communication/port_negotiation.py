"""
Port negotiation implementation for PyWatt modules.

This module provides port negotiation with the orchestrator via IPC.
"""

import asyncio
import json
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any
import logging

from ..communication.ipc_types import IpcPortNegotiation, IpcPortNegotiationResponse, ModuleToOrchestrator
from ..core.error import NetworkError

logger = logging.getLogger(__name__)

# Constants
NEGOTIATION_PORT = 9998
MAX_PORT = 65535
MIN_DYNAMIC_PORT = 49152
DEFAULT_PORT_NEGOTIATION_TIMEOUT_SECS = 3
INITIAL_PORT_NEGOTIATION_TIMEOUT_SECS = 3
MAX_PORT_NEGOTIATION_TIMEOUT_SECS = 10
MAX_PORT_NEGOTIATION_RETRIES = 3
DEFAULT_PORT_RANGE_START = 8000
DEFAULT_PORT_RANGE_END = 9000
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_RESET_SECS = 60
FALLBACK_PORT_RANGE_START = 10000
FALLBACK_PORT_RANGE_END = 11000


class CircuitBreakerStatus(Enum):
    """Circuit breaker status."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Using fallback mechanisms
    HALF_OPEN = "half_open"  # Testing if normal operation can resume


@dataclass
class CircuitBreakerState:
    """Circuit breaker state."""
    status: CircuitBreakerStatus = CircuitBreakerStatus.CLOSED
    consecutive_failures: int = 0
    last_failure_time: Optional[float] = None
    
    def should_attempt_request(self) -> bool:
        """Check if we should attempt a request."""
        if self.status == CircuitBreakerStatus.CLOSED:
            return True
        elif self.status == CircuitBreakerStatus.OPEN:
            # Check if enough time has passed to try again
            if (self.last_failure_time and 
                time.time() - self.last_failure_time > CIRCUIT_BREAKER_RESET_SECS):
                self.status = CircuitBreakerStatus.HALF_OPEN
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def record_success(self):
        """Record a successful operation."""
        self.status = CircuitBreakerStatus.CLOSED
        self.consecutive_failures = 0
        self.last_failure_time = None
    
    def record_failure(self):
        """Record a failed operation."""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        
        if self.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            self.status = CircuitBreakerStatus.OPEN


@dataclass
class PortNegotiationState:
    """Port negotiation state."""
    allocated_port: Optional[int] = None
    pending_requests: Dict[str, asyncio.Future] = field(default_factory=dict)
    circuit_breaker: CircuitBreakerState = field(default_factory=CircuitBreakerState)


class PortNegotiationManager:
    """Manager for port negotiation with the orchestrator."""
    
    def __init__(self):
        """Initialize the port negotiation manager."""
        self.state = PortNegotiationState()
        self._stdout_lock = asyncio.Lock()
    
    async def negotiate_port(
        self,
        preferred_port: Optional[int] = None,
        timeout: float = DEFAULT_PORT_NEGOTIATION_TIMEOUT_SECS
    ) -> int:
        """Negotiate a port with the orchestrator."""
        # Check if we already have an allocated port
        if self.state.allocated_port:
            return self.state.allocated_port
        
        # Check circuit breaker
        if not self.state.circuit_breaker.should_attempt_request():
            logger.warning("Circuit breaker is open, using fallback port allocation")
            return self._generate_fallback_port()
        
        # Try negotiation with retries
        for attempt in range(MAX_PORT_NEGOTIATION_RETRIES):
            try:
                port = await self._attempt_negotiation(preferred_port, timeout)
                self.state.circuit_breaker.record_success()
                self.state.allocated_port = port
                return port
            
            except Exception as e:
                logger.warning(f"Port negotiation attempt {attempt + 1} failed: {e}")
                if attempt == MAX_PORT_NEGOTIATION_RETRIES - 1:
                    self.state.circuit_breaker.record_failure()
                    logger.error("All port negotiation attempts failed, using fallback")
                    return self._generate_fallback_port()
                
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)
        
        # Should not reach here, but fallback just in case
        return self._generate_fallback_port()
    
    async def _attempt_negotiation(
        self,
        preferred_port: Optional[int],
        timeout: float
    ) -> int:
        """Attempt a single port negotiation."""
        request_id = str(uuid.uuid4())
        
        # Create negotiation request
        negotiation_request = IpcPortNegotiation(
            request_id=request_id,
            preferred_port=preferred_port,
            port_range_start=DEFAULT_PORT_RANGE_START,
            port_range_end=DEFAULT_PORT_RANGE_END
        )
        
        # Create future for response
        response_future: asyncio.Future[IpcPortNegotiationResponse] = asyncio.Future()
        self.state.pending_requests[request_id] = response_future
        
        try:
            # Send request to orchestrator
            await self._send_negotiation_request(negotiation_request)
            
            # Wait for response
            response = await asyncio.wait_for(response_future, timeout=timeout)
            
            if response.success and response.allocated_port:
                logger.info(f"Successfully negotiated port: {response.allocated_port}")
                return response.allocated_port
            else:
                error_msg = response.error_message or "Unknown error"
                raise NetworkError(f"Port negotiation failed: {error_msg}")
        
        except asyncio.TimeoutError:
            raise NetworkError("Port negotiation timed out")
        
        finally:
            # Clean up pending request
            self.state.pending_requests.pop(request_id, None)
    
    async def _send_negotiation_request(self, request: IpcPortNegotiation):
        """Send a port negotiation request to the orchestrator."""
        message = ModuleToOrchestrator(
            op="port_negotiation",
            port_negotiation=request
        )
        
        async with self._stdout_lock:
            json_str = json.dumps(message.model_dump(exclude_none=True))
            sys.stdout.write(json_str + "\n")
            sys.stdout.flush()
        
        logger.debug(f"Sent port negotiation request: {request.request_id}")
    
    def handle_negotiation_response(self, response: IpcPortNegotiationResponse):
        """Handle a port negotiation response from the orchestrator."""
        request_id = response.request_id
        
        if request_id in self.state.pending_requests:
            future = self.state.pending_requests[request_id]
            if not future.done():
                future.set_result(response)
            logger.debug(f"Handled port negotiation response: {request_id}")
        else:
            logger.warning(f"Received unexpected port negotiation response: {request_id}")
    
    def _generate_fallback_port(self) -> int:
        """Generate a fallback port when orchestrator communication fails."""
        # Use a random port in the fallback range
        port = random.randint(FALLBACK_PORT_RANGE_START, FALLBACK_PORT_RANGE_END)
        
        # Try to ensure it's not in use (basic check)
        import socket
        for _ in range(10):  # Try up to 10 times
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('127.0.0.1', port))
                    break  # Port is available
            except OSError:
                port = random.randint(FALLBACK_PORT_RANGE_START, FALLBACK_PORT_RANGE_END)
        
        logger.info(f"Using fallback port: {port}")
        self.state.allocated_port = port
        return port
    
    def get_allocated_port(self) -> Optional[int]:
        """Get the currently allocated port."""
        return self.state.allocated_port
    
    def set_pre_allocated_port(self, port: int):
        """Set a pre-allocated port (for testing or manual configuration)."""
        self.state.allocated_port = port
        logger.info(f"Set pre-allocated port: {port}")
    
    def reset_allocation(self):
        """Reset the port allocation state."""
        self.state.allocated_port = None
        self.state.pending_requests.clear()
        logger.debug("Reset port allocation state")


# Global port negotiation manager instance
_port_manager: Optional[PortNegotiationManager] = None


def get_port_manager() -> PortNegotiationManager:
    """Get the global port negotiation manager."""
    global _port_manager
    if _port_manager is None:
        _port_manager = PortNegotiationManager()
    return _port_manager


async def negotiate_port(
    preferred_port: Optional[int] = None,
    timeout: float = DEFAULT_PORT_NEGOTIATION_TIMEOUT_SECS
) -> int:
    """Negotiate a port with the orchestrator."""
    manager = get_port_manager()
    return await manager.negotiate_port(preferred_port, timeout)


def handle_port_negotiation_response(response: IpcPortNegotiationResponse):
    """Handle a port negotiation response from the orchestrator."""
    manager = get_port_manager()
    manager.handle_negotiation_response(response)


def get_allocated_port() -> Optional[int]:
    """Get the currently allocated port."""
    manager = get_port_manager()
    return manager.get_allocated_port()


def set_pre_allocated_port(port: int):
    """Set a pre-allocated port (for testing or manual configuration)."""
    manager = get_port_manager()
    manager.set_pre_allocated_port(port)


def reset_port_allocation():
    """Reset the port allocation state."""
    manager = get_port_manager()
    manager.reset_allocation()


def generate_random_port(start: int = DEFAULT_PORT_RANGE_START, end: int = DEFAULT_PORT_RANGE_END) -> int:
    """Generate a random port in the specified range."""
    return random.randint(start, end)


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is available for binding."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            return True
    except OSError:
        return False


def find_available_port(
    start: int = DEFAULT_PORT_RANGE_START,
    end: int = DEFAULT_PORT_RANGE_END,
    host: str = "127.0.0.1"
) -> Optional[int]:
    """Find an available port in the specified range."""
    for port in range(start, end + 1):
        if is_port_available(port, host):
            return port
    return None


# Port negotiation functionality is fully implemented with:
# - IPC message sending/receiving
# - Timeout and retry logic with exponential backoff
# - Circuit breaker pattern for resilience
# - Fallback port allocation when orchestrator is unavailable 