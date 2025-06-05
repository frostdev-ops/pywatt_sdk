"""Core PyWatt SDK components.

This module provides the fundamental building blocks for PyWatt modules:
- Error handling and exceptions
- Application state management
- Configuration management
- Logging setup
- Module bootstrap functionality
"""

from .error import (
    PyWattSDKError,
    BootstrapError,
    HandshakeError,
    SecretError,
    AnnouncementError,
    ConfigError,
    NetworkError,
    Result,
)
from .logging import init_module, safe_log
from .state import AppState, AppConfig
from .config import Config

__all__ = [
    # Error handling
    "PyWattSDKError",
    "BootstrapError", 
    "HandshakeError",
    "SecretError",
    "AnnouncementError",
    "ConfigError",
    "NetworkError",
    "Result",
    # Logging
    "init_module",
    "safe_log",
    # State management
    "AppState",
    "AppConfig",
    # Configuration
    "Config",
] 