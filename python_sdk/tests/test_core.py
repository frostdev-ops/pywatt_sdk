"""Tests for core PyWatt SDK functionality."""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.error import (
    PyWattSDKError,
    HandshakeError,
    SecretError,
    Result,
)
from core.logging import (
    init_module,
    register_secret_for_redaction,
    redact_secrets,
    clear_secret_registry,
)
from core.state import AppState, AppConfig
from core.config import Config


class TestErrors:
    """Test error handling functionality."""
    
    def test_pywatt_sdk_error_creation(self):
        """Test creating PyWattSDKError instances."""
        error = PyWattSDKError("test error")
        assert str(error) == "test error"
        assert error.message == "test error"
        assert error.cause is None
    
    def test_pywatt_sdk_error_with_cause(self):
        """Test creating PyWattSDKError with cause."""
        cause = ValueError("original error")
        error = PyWattSDKError("wrapper error", cause)
        assert str(error) == "wrapper error: original error"
        assert error.cause is cause
    
    def test_handshake_error(self):
        """Test HandshakeError creation."""
        error = HandshakeError("handshake failed")
        assert "handshake failed: handshake failed" in str(error)
    
    def test_secret_error(self):
        """Test SecretError creation."""
        error = SecretError("secret not found")
        assert "secret client error: secret not found" in str(error)


class TestResult:
    """Test Result type functionality."""
    
    def test_result_ok(self):
        """Test creating successful Result."""
        result = Result.ok("success")
        assert result.is_ok()
        assert not result.is_err()
        assert result.unwrap() == "success"
    
    def test_result_err(self):
        """Test creating error Result."""
        error = PyWattSDKError("test error")
        result = Result.err(error)
        assert result.is_err()
        assert not result.is_ok()
        assert result.unwrap_err() is error
    
    def test_result_unwrap_error(self):
        """Test unwrapping error Result raises exception."""
        error = PyWattSDKError("test error")
        result = Result.err(error)
        with pytest.raises(PyWattSDKError):
            result.unwrap()
    
    def test_result_unwrap_or(self):
        """Test unwrap_or with default value."""
        error = PyWattSDKError("test error")
        result = Result.err(error)
        assert result.unwrap_or("default") == "default"
        
        success_result = Result.ok("success")
        assert success_result.unwrap_or("default") == "success"


class TestLogging:
    """Test logging functionality."""
    
    def setup_method(self):
        """Clear secret registry before each test."""
        clear_secret_registry()
    
    def test_secret_redaction(self):
        """Test secret redaction functionality."""
        secret = "super-secret-password"
        register_secret_for_redaction(secret)
        
        text = f"The password is {secret} and should be hidden"
        redacted = redact_secrets(text)
        
        assert secret not in redacted
        assert "[REDACTED]" in redacted
    
    def test_multiple_secret_redaction(self):
        """Test redacting multiple secrets."""
        secret1 = "password123"
        secret2 = "api-key-456"
        
        register_secret_for_redaction(secret1)
        register_secret_for_redaction(secret2)
        
        text = f"Password: {secret1}, API Key: {secret2}"
        redacted = redact_secrets(text)
        
        assert secret1 not in redacted
        assert secret2 not in redacted
        assert redacted.count("[REDACTED]") == 2
    
    def test_empty_secret_not_registered(self):
        """Test that empty secrets are not registered."""
        register_secret_for_redaction("")
        register_secret_for_redaction("   ")
        
        # Should not affect redaction
        text = "This text should not be redacted"
        redacted = redact_secrets(text)
        assert redacted == text


class TestAppState:
    """Test AppState functionality."""
    
    def test_app_state_creation(self):
        """Test creating AppState instance."""
        mock_client = Mock()
        user_state = {"key": "value"}
        
        state = AppState(
            module_id="test-module",
            orchestrator_api="http://localhost:9000",
            secret_client=mock_client,
            user_state=user_state
        )
        
        assert state.module_id == "test-module"
        assert state.orchestrator_api == "http://localhost:9000"
        assert state.secret_client is mock_client
        assert state.user_state is user_state
        assert state.custom() is user_state
    
    def test_app_state_with_config(self):
        """Test creating AppState with custom config."""
        mock_client = Mock()
        config = AppConfig(ipc_timeout_ms=5000)
        
        state = AppState(
            module_id="test-module",
            orchestrator_api="http://localhost:9000",
            secret_client=mock_client,
            user_state={},
            config=config
        )
        
        assert state.config.ipc_timeout_ms == 5000
    
    def test_available_channels_empty(self):
        """Test available_channels when no channels are set."""
        mock_client = Mock()
        state = AppState(
            module_id="test-module",
            orchestrator_api="http://localhost:9000",
            secret_client=mock_client,
            user_state={}
        )
        
        assert state.available_channels() == []
    
    def test_channel_health(self):
        """Test channel health checking."""
        mock_client = Mock()
        state = AppState(
            module_id="test-module",
            orchestrator_api="http://localhost:9000",
            secret_client=mock_client,
            user_state={}
        )
        
        # Should return empty dict when no channels
        health = asyncio.run(state.channel_health())
        assert health == {}


class TestAppConfig:
    """Test AppConfig functionality."""
    
    def test_app_config_defaults(self):
        """Test AppConfig default values."""
        config = AppConfig()
        
        assert config.message_format_primary.value == "json"
        assert config.message_format_secondary.value == "msgpack"
        assert config.ipc_timeout_ms == 30000
        assert config.ipc_only is False
        assert config.enable_advanced_features is True
    
    def test_app_config_custom_values(self):
        """Test AppConfig with custom values."""
        config = AppConfig(
            ipc_timeout_ms=5000,
            ipc_only=True,
            enable_advanced_features=True
        )
        
        assert config.ipc_timeout_ms == 5000
        assert config.ipc_only is True
        assert config.enable_advanced_features is True


class TestConfig:
    """Test Config functionality."""
    
    def test_config_defaults(self):
        """Test Config default values."""
        config = Config()
        
        assert config.log_level.value == "INFO"
        assert config.log_format == "json"
        assert config.ipc_timeout_seconds == 30
        assert config.max_retries == 3
        assert config.enable_metrics is False
        assert config.enable_health_check is True
    
    def test_config_validation(self):
        """Test Config validation."""
        # Valid orchestrator API
        config = Config(orchestrator_api="https://localhost:9000")
        assert config.orchestrator_api == "https://localhost:9000"
        
        # Invalid orchestrator API should raise validation error
        with pytest.raises(ValueError):
            Config(orchestrator_api="invalid-url")
    
    def test_config_from_dict(self):
        """Test creating Config from dictionary."""
        data = {
            "log_level": "DEBUG",
            "ipc_timeout_seconds": 60,
            "enable_metrics": True
        }
        
        config = Config.from_dict(data)
        assert config.log_level.value == "DEBUG"
        assert config.ipc_timeout_seconds == 60
        assert config.enable_metrics is True 