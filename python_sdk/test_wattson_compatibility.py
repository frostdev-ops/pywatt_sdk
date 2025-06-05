#!/usr/bin/env python3
"""Test PyWatt Python SDK compatibility with Wattson orchestrator.

This test verifies that the Python SDK correctly implements the IPC protocol
expected by the Wattson orchestrator.
"""

import asyncio
import json
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, Any, List

# Add the SDK to the path
sys.path.insert(0, '.')

from communication.ipc_types import (
    InitBlob, AnnounceBlob, EndpointAnnounce,
    ModuleToOrchestrator, OrchestratorToModule,
    ListenAddress, TcpChannelConfig, IpcChannelConfig,
    SecurityLevel, GetSecretRequest, SecretValueResponse,
    RotatedNotification, RotationAckRequest
)
from communication.ipc import read_init, send_announce, process_ipc_messages
from module import pywatt_module, AnnouncedEndpoint
from core import AppState, init_module


def test_init_blob_parsing():
    """Test that InitBlob can parse the expected format from Wattson."""
    print("\n=== Testing InitBlob Parsing ===")
    
    # Test data matching Wattson's format
    init_data = {
        "orchestrator_api": "http://localhost:9900",
        "module_id": "test-module",
        "listen": "127.0.0.1:8080",
        "env": {"TEST_VAR": "test_value"},
        "tcp_channel": {
            "host": "127.0.0.1",
            "port": 9901,
            "tls_enabled": False,
            "required": False
        },
        "ipc_channel": {
            "socket_path": "/tmp/test.sock",
            "required": False
        },
        "auth_token": None,
        "security_level": "None",
        "debug_mode": True,
        "log_level": "debug"
    }
    
    # Parse the data
    init_blob = InitBlob(**init_data)
    
    # Verify all fields
    assert init_blob.orchestrator_api == "http://localhost:9900"
    assert init_blob.module_id == "test-module"
    assert str(init_blob.listen) == "127.0.0.1:8080"
    assert init_blob.env["TEST_VAR"] == "test_value"
    assert init_blob.tcp_channel.host == "127.0.0.1"
    assert init_blob.tcp_channel.port == 9901
    assert init_blob.ipc_channel.socket_path == "/tmp/test.sock"
    assert init_blob.auth_token is None
    assert init_blob.security_level == SecurityLevel.NONE
    assert init_blob.debug_mode == True
    assert init_blob.log_level == "debug"
    
    print("✓ InitBlob parsing successful")
    
    # Test JSON serialization round-trip
    json_str = init_blob.model_dump_json()
    parsed = InitBlob.model_validate_json(json_str)
    assert parsed.module_id == init_blob.module_id
    print("✓ JSON serialization round-trip successful")


def test_announce_blob_format():
    """Test that AnnounceBlob matches the expected format."""
    print("\n=== Testing AnnounceBlob Format ===")
    
    # Create announcement
    announce = AnnounceBlob(
        listen="127.0.0.1:8080",
        endpoints=[
            EndpointAnnounce(path="/health", methods=["GET"], auth=None),
            EndpointAnnounce(path="/api/data", methods=["GET", "POST"], auth="jwt")
        ]
    )
    
    # Verify JSON format
    json_data = json.loads(announce.model_dump_json())
    assert json_data["listen"] == "127.0.0.1:8080"
    assert len(json_data["endpoints"]) == 2
    assert json_data["endpoints"][0]["path"] == "/health"
    assert json_data["endpoints"][0]["methods"] == ["GET"]
    assert json_data["endpoints"][0]["auth"] is None
    assert json_data["endpoints"][1]["auth"] == "jwt"
    
    print("✓ AnnounceBlob format correct")


def test_ipc_message_types():
    """Test all IPC message types."""
    print("\n=== Testing IPC Message Types ===")
    
    # Test ModuleToOrchestrator messages
    messages = []
    
    # GetSecret
    msg = ModuleToOrchestrator.get_secret_msg(GetSecretRequest(name="API_KEY"))
    assert msg.op == "get_secret"
    assert msg.get_secret.name == "API_KEY"
    messages.append(("GetSecret", msg))
    
    # Announce
    announce = AnnounceBlob(listen="127.0.0.1:8080", endpoints=[])
    msg = ModuleToOrchestrator.announce_msg(announce)
    assert msg.op == "announce"
    messages.append(("Announce", msg))
    
    # HeartbeatAck
    msg = ModuleToOrchestrator.heartbeat_ack_msg()
    assert msg.op == "heartbeat_ack"
    messages.append(("HeartbeatAck", msg))
    
    # RotationAck
    ack = RotationAckRequest(rotation_id="rot123", status="success")
    msg = ModuleToOrchestrator.rotation_ack_msg(ack)
    assert msg.op == "rotation_ack"
    messages.append(("RotationAck", msg))
    
    # Verify JSON serialization
    for name, msg in messages:
        json_str = msg.model_dump_json()
        parsed = ModuleToOrchestrator.model_validate_json(json_str)
        assert parsed.op == msg.op
        print(f"✓ {name} message format correct")
    
    # Test OrchestratorToModule messages
    orch_messages = []
    
    # Secret
    secret = SecretValueResponse(name="API_KEY", value="secret123", rotation_id=None)
    msg = OrchestratorToModule.secret_msg(secret)
    assert msg.op == "secret"
    orch_messages.append(("Secret", msg))
    
    # Rotated
    rotated = RotatedNotification(keys=["API_KEY", "DB_URL"], rotation_id="rot123")
    msg = OrchestratorToModule.rotated_msg(rotated)
    assert msg.op == "rotated"
    orch_messages.append(("Rotated", msg))
    
    # Shutdown
    msg = OrchestratorToModule.shutdown_msg()
    assert msg.op == "shutdown"
    orch_messages.append(("Shutdown", msg))
    
    # Heartbeat
    msg = OrchestratorToModule.heartbeat_msg()
    assert msg.op == "heartbeat"
    orch_messages.append(("Heartbeat", msg))
    
    # Verify JSON serialization
    for name, msg in orch_messages:
        json_str = msg.model_dump_json()
        parsed = OrchestratorToModule.model_validate_json(json_str)
        assert parsed.op == msg.op
        print(f"✓ {name} message format correct")


async def test_ipc_handshake():
    """Test the IPC handshake process."""
    print("\n=== Testing IPC Handshake ===")
    
    # Simulate stdin with init data
    init_json = json.dumps({
        "orchestrator_api": "http://localhost:9900",
        "module_id": "test-module",
        "listen": "127.0.0.1:8080",
        "env": {},
        "tcp_channel": None,
        "ipc_channel": None,
        "auth_token": None,
        "security_level": "None",
        "debug_mode": False,
        "log_level": "info"
    })
    
    # Mock stdin
    original_stdin = sys.stdin
    sys.stdin = io.StringIO(init_json + "\n")
    
    try:
        # Read init
        init_data = await read_init()
        assert init_data.module_id == "test-module"
        assert init_data.orchestrator_api == "http://localhost:9900"
        print("✓ Handshake read successful")
    finally:
        sys.stdin = original_stdin
    
    # Test announcement
    captured_output = io.StringIO()
    with redirect_stdout(captured_output):
        announce = AnnounceBlob(
            listen="127.0.0.1:8080",
            endpoints=[EndpointAnnounce(path="/health", methods=["GET"], auth=None)]
        )
        send_announce(announce)
    
    output = captured_output.getvalue()
    assert output.strip()  # Should have output
    announce_data = json.loads(output.strip())
    assert announce_data["listen"] == "127.0.0.1:8080"
    assert len(announce_data["endpoints"]) == 1
    print("✓ Announcement send successful")


def test_logging_to_stderr():
    """Test that all logs go to stderr, not stdout."""
    print("\n=== Testing Logging to stderr ===")
    
    # Capture stdout and stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
        # Initialize logging inside the redirect context
        init_module()
        
        from core.logging import info, error, debug
        info("Test info message")
        error("Test error message")
        debug("Test debug message")
    
    # Check that nothing went to stdout
    stdout_content = stdout_capture.getvalue()
    assert stdout_content == "", f"Unexpected stdout content: {stdout_content}"
    
    # Check that logs went to stderr as JSON
    stderr_content = stderr_capture.getvalue()
    
    # Look for JSON objects in the content
    # Split by newlines first, then try to parse each line
    lines = stderr_content.strip().split('\n')
    
    found_info = False
    found_error = False
    found_init = False
    
    for line in lines:
        if line.strip():
            try:
                log_entry = json.loads(line)
                message = log_entry.get("message", "")
                if "Test info message" in message:
                    found_info = True
                elif "Test error message" in message:
                    found_error = True
                elif "PyWatt SDK logging initialized" in message:
                    found_init = True
            except json.JSONDecodeError:
                # If the line isn't valid JSON, skip it
                pass
    
    assert found_init, "Logging initialization message not found"
    assert found_info, "Info message not found in stderr logs"
    assert found_error, "Error message not found in stderr logs"
    
    print("✓ Logging correctly goes to stderr only")


async def test_module_decorator():
    """Test the @pywatt_module decorator."""
    print("\n=== Testing @pywatt_module Decorator ===")
    
    # Create a test module
    @pywatt_module(
        secrets=["API_KEY", "DATABASE_URL"],
        rotate=True,
        endpoints=[
            AnnouncedEndpoint(path="/api/data", methods=["GET", "POST"], auth="jwt"),
        ],
        health="/health",
        metrics=True,
    )
    async def test_module(app_state: AppState) -> Dict[str, Any]:
        return {
            "type": "test",
            "state": app_state,
        }
    
    # The decorator should handle initialization
    # In a real scenario, this would read from stdin and write to stdout
    print("✓ @pywatt_module decorator defined successfully")


def test_listen_address_formats():
    """Test different ListenAddress formats."""
    print("\n=== Testing ListenAddress Formats ===")
    
    # TCP address
    tcp_addr = ListenAddress.tcp("127.0.0.1", 8080)
    assert str(tcp_addr) == "127.0.0.1:8080"
    assert tcp_addr.is_tcp()
    assert not tcp_addr.is_unix()
    
    # Unix socket address
    unix_addr = ListenAddress.unix("/tmp/test.sock")
    assert str(unix_addr) == "/tmp/test.sock"
    assert unix_addr.is_unix()
    assert not unix_addr.is_tcp()
    
    # Parse from string (TCP)
    parsed_tcp = ListenAddress(root="192.168.1.1:9000")
    assert str(parsed_tcp) == "192.168.1.1:9000"
    assert parsed_tcp.is_tcp()
    
    # Parse from dict (Unix)
    parsed_unix = ListenAddress(root={"Unix": "/var/run/test.sock"})
    assert str(parsed_unix) == "/var/run/test.sock"
    assert parsed_unix.is_unix()
    
    print("✓ ListenAddress formats work correctly")


async def test_example_module_pattern():
    """Test the example module pattern from requirements."""
    print("\n=== Testing Example Module Pattern ===")
    
    # This tests that the pattern shown in requirements would work
    from aiohttp import web
    
    @pywatt_module(
        secrets=["DATABASE_URL", "API_KEY"],
        rotate=True,
        endpoints=[
            AnnouncedEndpoint(path="/api/data", methods=["GET", "POST"]),
        ],
        health="/health",
    )
    async def create_app(app_state: AppState) -> web.Application:
        app = web.Application()
        app["app_state"] = app_state
        
        # Define routes would go here
        return app
    
    print("✓ Example module pattern is valid")


def main():
    """Run all compatibility tests."""
    print("PyWatt Python SDK - Wattson Compatibility Tests")
    print("=" * 50)
    
    # Synchronous tests
    test_init_blob_parsing()
    test_announce_blob_format()
    test_ipc_message_types()
    test_logging_to_stderr()
    test_listen_address_formats()
    
    # Asynchronous tests
    asyncio.run(test_ipc_handshake())
    asyncio.run(test_module_decorator())
    asyncio.run(test_example_module_pattern())
    
    print("\n" + "=" * 50)
    print("All compatibility tests passed! ✓")
    print("\nThe Python SDK is compatible with Wattson's requirements.")


if __name__ == "__main__":
    main() 