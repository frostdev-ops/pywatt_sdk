"""Unified error handling for the PyWatt SDK.

This module provides a comprehensive error system that mirrors the Rust SDK's
error handling approach, with proper error chaining and context preservation.
"""

from typing import Any, Optional, TypeVar, Union, Generic
import traceback


T = TypeVar("T")


class PyWattSDKError(Exception):
    """Base exception for all PyWatt SDK errors.
    
    This is the unified error type that encompasses all possible error cases
    in the SDK, providing meaningful error messages and proper error chaining.
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause

    def __str__(self) -> str:
        if self.cause:
            return f"{self.message}: {self.cause}"
        return self.message

    def __repr__(self) -> str:
        if self.cause:
            return f"{self.__class__.__name__}('{self.message}', cause={self.cause!r})"
        return f"{self.__class__.__name__}('{self.message}')"


class BootstrapError(PyWattSDKError):
    """Error that occurs during module bootstrap initialization."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"bootstrap failed: {message}", cause)


class HandshakeError(PyWattSDKError):
    """Error that occurs during the initial handshake with the orchestrator."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"handshake failed: {message}", cause)


class SecretError(PyWattSDKError):
    """Error that occurs during secret management operations."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"secret client error: {message}", cause)


class AnnouncementError(PyWattSDKError):
    """Error that occurs during module announcement to the orchestrator."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"announcement error: {message}", cause)


class ConfigError(PyWattSDKError):
    """Error that occurs due to configuration issues."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"configuration error: {message}", cause)

    @classmethod
    def missing_env_var(cls, var_name: str) -> "ConfigError":
        """Create a ConfigError for a missing environment variable."""
        return cls(f"missing environment variable: {var_name}")

    @classmethod
    def invalid_config(cls, message: str) -> "ConfigError":
        """Create a ConfigError for invalid configuration."""
        return cls(f"invalid configuration: {message}")


class NetworkError(PyWattSDKError):
    """Error that occurs during network operations."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"network error: {message}", cause)


class MetricsError(PyWattSDKError):
    """Error that occurs during metrics operations."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"metrics error: {message}", cause)


class DatabaseError(PyWattSDKError):
    """Error that occurs during database operations."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"database error: {message}", cause)


class CacheError(PyWattSDKError):
    """Error that occurs during cache operations."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"cache error: {message}", cause)


class HttpError(PyWattSDKError):
    """Error that occurs during HTTP operations."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"HTTP error: {message}", cause)


class ServerError(PyWattSDKError):
    """Error that occurs during server operations."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"server error: {message}", cause)


class RegistrationError(PyWattSDKError):
    """Error that occurs during module registration."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"registration error: {message}", cause)


class AuthenticationError(PyWattSDKError):
    """Error that occurs during authentication operations."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"authentication error: {message}", cause)


class Result(Generic[T]):
    """A Result type similar to Rust's Result<T, E>.
    
    This provides a more explicit way to handle operations that can fail,
    making error handling more visible in the code.
    """

    def __init__(self, value: Optional[T] = None, error: Optional[PyWattSDKError] = None) -> None:
        if value is not None and error is not None:
            raise ValueError("Result cannot have both value and error")
        if value is None and error is None:
            raise ValueError("Result must have either value or error")
        
        self._value = value
        self._error = error

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        """Create a successful Result."""
        return cls(value=value)

    @classmethod
    def err(cls, error: PyWattSDKError) -> "Result[T]":
        """Create an error Result."""
        return cls(error=error)

    def is_ok(self) -> bool:
        """Check if the Result is successful."""
        return self._error is None

    def is_err(self) -> bool:
        """Check if the Result is an error."""
        return self._error is not None

    def unwrap(self) -> T:
        """Get the value, raising an exception if it's an error."""
        if self._error is not None:
            raise self._error
        assert self._value is not None
        return self._value

    def unwrap_or(self, default: T) -> T:
        """Get the value or return a default if it's an error."""
        if self._error is not None:
            return default
        assert self._value is not None
        return self._value

    def unwrap_err(self) -> PyWattSDKError:
        """Get the error, raising an exception if it's successful."""
        if self._error is None:
            raise ValueError("Called unwrap_err on a successful Result")
        return self._error

    def map(self, func) -> "Result":
        """Apply a function to the value if successful."""
        if self._error is not None:
            return Result.err(self._error)
        assert self._value is not None
        try:
            new_value = func(self._value)
            return Result.ok(new_value)
        except Exception as e:
            if isinstance(e, PyWattSDKError):
                return Result.err(e)
            return Result.err(PyWattSDKError(str(e), cause=e))

    def and_then(self, func) -> "Result":
        """Chain operations that return Results."""
        if self._error is not None:
            return Result.err(self._error)
        assert self._value is not None
        try:
            return func(self._value)
        except Exception as e:
            if isinstance(e, PyWattSDKError):
                return Result.err(e)
            return Result.err(PyWattSDKError(str(e), cause=e))

    def __repr__(self) -> str:
        if self._error is not None:
            return f"Result.err({self._error!r})"
        return f"Result.ok({self._value!r})"


def wrap_exception(func):
    """Decorator to wrap exceptions in PyWattSDKError."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PyWattSDKError:
            raise  # Re-raise PyWattSDKError as-is
        except Exception as e:
            # Convert other exceptions to PyWattSDKError
            raise PyWattSDKError(str(e), cause=e)
    return wrapper


def wrap_async_exception(func):
    """Decorator to wrap exceptions in async functions."""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except PyWattSDKError:
            raise  # Re-raise PyWattSDKError as-is
        except Exception as e:
            # Convert other exceptions to PyWattSDKError
            raise PyWattSDKError(str(e), cause=e)
    return wrapper


def format_error_chain(error: Exception) -> str:
    """Format an error with its full chain of causes."""
    lines = []
    current = error
    
    while current is not None:
        lines.append(f"  {type(current).__name__}: {current}")
        
        # Get the cause
        if hasattr(current, 'cause') and current.cause is not None:
            current = current.cause
        elif hasattr(current, '__cause__') and current.__cause__ is not None:
            current = current.__cause__
        else:
            current = None
    
    return "\n".join(lines)


def get_error_context() -> str:
    """Get the current error context (stack trace)."""
    return traceback.format_exc() 