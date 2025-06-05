"""
PyWatt SDK Security Module

This module provides security-related functionality including:
- JWT authentication middleware for FastAPI, Flask, and Starlette
- Secret management and rotation
- Authentication utilities
"""

from .jwt_auth import (
    JwtConfig,
    JwtAuthError,
    JwtValidator,
    FastAPIJwtMiddleware,
    FlaskJwtManager,
    StarletteJwtMiddleware,
    validate_jwt_from_headers,
    create_jwt_token,
    create_default_jwt_config,
    get_jwt_secret_from_env,
    is_running_as_module,
)

from .secret_client import (
    SecretClient,
    RequestMode,
    get_module_secret_client,
    get_secret,
    get_secrets,
    subscribe_secret_rotations,
    get_global_secret_client,
)

from .secrets import (
    SecretProvider,
    OrchestratorSecretProvider,
    SecretNotFoundError,
    SecretError,
    SecretRotationError,
    redact_secrets,
)

try:
    from core.logging import register_secret_for_redaction
except ImportError:
    def register_secret_for_redaction(secret):
        pass

from .typed_secret import (
    Secret, SecretString, SecretInt, SecretFloat, SecretBool,
    get_typed_secret, get_string_secret, get_int_secret, 
    get_float_secret, get_bool_secret, TypedSecretError
)

__all__ = [
    # JWT Authentication
    "JwtConfig",
    "JwtAuthError",
    "JwtValidator",
    "FastAPIJwtMiddleware",
    "FlaskJwtManager", 
    "StarletteJwtMiddleware",
    "validate_jwt_from_headers",
    "create_jwt_token",
    "create_default_jwt_config",
    "get_jwt_secret_from_env",
    "is_running_as_module",
    
    # Secret Management
    "SecretClient",
    "RequestMode",
    "get_module_secret_client",
    "get_secret",
    "get_secrets",
    "subscribe_secret_rotations",
    "get_global_secret_client",
    "SecretProvider",
    "OrchestratorSecretProvider",
    "SecretNotFoundError",
    "SecretError",
    "SecretRotationError",
    "redact_secrets",
    "register_secret_for_redaction",
    "Secret",
    "SecretString",
    "SecretInt",
    "SecretFloat",
    "SecretBool",
    "get_typed_secret",
    "get_string_secret",
    "get_int_secret",
    "get_float_secret",
    "get_bool_secret",
    "TypedSecretError",
] 