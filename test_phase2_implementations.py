#!/usr/bin/env python3
"""Test script for Phase 2 implementations.

This script tests the newly implemented Phase 2 components:
- HTTP-over-IPC communication
- HTTP-over-TCP communication  
- Port negotiation
- JWT authentication
"""

import asyncio
import json
import sys
import time
from typing import Dict, Any

# Add the SDK to the path
sys.path.insert(0, 'pywatt_sdk')

from pywatt_sdk.communication.http_ipc import (
    HttpIpcRouter, json_response, get_global_router, handle_http_request
)
from pywatt_sdk.communication.http_tcp import (
    HttpTcpClient, HttpTcpRouter, HttpTcpRequest, start_http_server
)
from pywatt_sdk.communication.port_negotiation import (
    PortNegotiationManager, generate_random_port, is_port_available
)
from pywatt_sdk.communication.ipc_types import IpcHttpRequest
from pywatt_sdk.security.jwt_auth import (
    JwtConfig, JwtValidator, create_jwt_token, validate_jwt_from_headers
)


async def test_http_ipc():
    """Test HTTP-over-IPC functionality."""
    print("Testing HTTP-over-IPC...")
    
    # Create a router
    router = get_global_router()
    
    @router.get("/test")
    async def test_handler(request: IpcHttpRequest):
        return json_response({"message": "Hello from IPC!", "path": request.uri})
    
    @router.post("/echo")
    async def echo_handler(request: IpcHttpRequest):
        if request.body:
            data = json.loads(request.body.decode())
            return json_response({"echo": data})
        return json_response({"error": "No body"})
    
    # Start the router
    await router.start()
    
    # Test GET request
    get_request = IpcHttpRequest(
        request_id="test-1",
        method="GET",
        uri="/test?param=value",
        headers={"Content-Type": "application/json"},
        body=None
    )
    
    await handle_http_request(get_request)
    
    # Test POST request
    post_data = {"test": "data", "number": 42}
    post_request = IpcHttpRequest(
        request_id="test-2",
        method="POST",
        uri="/echo",
        headers={"Content-Type": "application/json"},
        body=json.dumps(post_data).encode()
    )
    
    await handle_http_request(post_request)
    
    # Stop the router
    await router.stop()
    
    print("✓ HTTP-over-IPC tests passed")


async def test_http_tcp():
    """Test HTTP-over-TCP functionality."""
    print("Testing HTTP-over-TCP...")
    
    # Find an available port
    port = generate_random_port(8000, 8100)
    while not is_port_available(port):
        port = generate_random_port(8000, 8100)
    
    # Create a router
    router = HttpTcpRouter()
    
    @router.get("/hello")
    async def hello_handler(request: HttpTcpRequest):
        return {"message": "Hello from TCP!", "method": request.method}
    
    @router.post("/data")
    async def data_handler(request: HttpTcpRequest):
        if request.body:
            try:
                data = json.loads(request.body.decode())
                return {"received": data, "timestamp": time.time()}
            except json.JSONDecodeError:
                return {"error": "Invalid JSON"}, 400
        return {"error": "No data"}, 400
    
    # Start the server
    runner = await start_http_server(router, "127.0.0.1", port)
    
    try:
        # Give the server a moment to start
        await asyncio.sleep(0.1)
        
        # Test with HTTP client
        async with HttpTcpClient(f"http://127.0.0.1:{port}") as client:
            # Test GET request
            response = await client.get("/hello")
            assert response.status_code == 200
            data = json.loads(response.body.decode())
            assert data["message"] == "Hello from TCP!"
            
            # Test POST request
            post_data = {"test": "tcp", "value": 123}
            response = await client.post("/data", post_data)
            assert response.status_code == 200
            data = json.loads(response.body.decode())
            assert data["received"]["test"] == "tcp"
        
        print("✓ HTTP-over-TCP tests passed")
    
    finally:
        # Clean up
        await runner.cleanup()


def test_port_negotiation():
    """Test port negotiation functionality."""
    print("Testing port negotiation...")
    
    # Test port availability checking
    assert is_port_available(65432)  # Should be available
    
    # Test random port generation
    port1 = generate_random_port(10000, 11000)
    port2 = generate_random_port(10000, 11000)
    assert 10000 <= port1 <= 11000
    assert 10000 <= port2 <= 11000
    
    # Test port manager
    manager = PortNegotiationManager()
    
    # Test pre-allocated port
    test_port = 12345
    manager.set_pre_allocated_port(test_port)
    assert manager.get_allocated_port() == test_port
    
    # Test reset
    manager.reset_allocation()
    assert manager.get_allocated_port() is None
    
    print("✓ Port negotiation tests passed")


def test_jwt_auth():
    """Test JWT authentication functionality."""
    print("Testing JWT authentication...")
    
    # Create JWT config
    secret = "test-secret-key-for-jwt-testing"
    config = JwtConfig(secret_key=secret)
    
    # Test token creation and validation
    claims = {
        "sub": "user123",
        "name": "Test User",
        "role": "admin",
        "exp": int(time.time()) + 3600  # Expires in 1 hour
    }
    
    # Create token
    token = create_jwt_token(claims, config)
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Validate token
    validator = JwtValidator(config)
    decoded_claims = validator.validate_token(token)
    assert decoded_claims["sub"] == "user123"
    assert decoded_claims["name"] == "Test User"
    assert decoded_claims["role"] == "admin"
    
    # Test header extraction
    headers = {"Authorization": f"Bearer {token}"}
    extracted_token = validator.extract_token_from_header(headers["Authorization"])
    assert extracted_token == token
    
    # Test validation from headers
    validated_claims = validate_jwt_from_headers(headers, config)
    assert validated_claims["sub"] == "user123"
    
    # Test invalid token
    try:
        validator.validate_token("invalid.token.here")
        assert False, "Should have raised an error"
    except Exception:
        pass  # Expected
    
    # Test missing header
    try:
        validator.extract_token_from_header(None)
        assert False, "Should have raised an error"
    except Exception:
        pass  # Expected
    
    print("✓ JWT authentication tests passed")


async def run_all_tests():
    """Run all Phase 2 tests."""
    print("Running Phase 2 implementation tests...\n")
    
    try:
        # Test HTTP-over-IPC
        await test_http_ipc()
        
        # Test HTTP-over-TCP
        await test_http_tcp()
        
        # Test port negotiation
        test_port_negotiation()
        
        # Test JWT authentication
        test_jwt_auth()
        
        print("\n🎉 All Phase 2 tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1) 