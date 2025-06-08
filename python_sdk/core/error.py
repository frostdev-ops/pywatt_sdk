"""Unified error handling for the PyWatt SDK.

This module provides a comprehensive error system that mirrors the Rust SDK's
error handling approach, with proper error chaining and context preservation.
It defines specialized error types for different categories of failures, making
error handling more granular and informative.
"""

from typing import Any, Optional, TypeVar, Union, Generic, Callable, TypeVar, Awaitable
import traceback
import asyncio


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
    """Error that occurs during secret management operations.
    
    This error is raised when secret retrieval, storage, or rotation
    operations fail.
    
    Examples:
        ```python
        try:
            # Get a secret
            secret = await secret_client.get("API_KEY")
        except Exception as e:
            raise SecretError("Failed to retrieve secret", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"secret client error: {message}", cause)


class AnnouncementError(PyWattSDKError):
    """Error that occurs during module announcement to the orchestrator.
    
    This error is raised when a module fails to announce its endpoints
    or capabilities to the orchestrator.
    
    Examples:
        ```python
        try:
            # Announce endpoints
            await module.announce_endpoints()
        except Exception as e:
            raise AnnouncementError("Failed to announce endpoints", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"announcement error: {message}", cause)


class ConfigError(PyWattSDKError):
    """Error that occurs due to configuration issues.
    
    This error is raised when configuration validation fails, a required
    configuration value is missing, or configuration loading fails.
    
    Examples:
        ```python
        try:
            # Load configuration
            config = Config.from_file("config.yaml")
        except Exception as e:
            raise ConfigError("Failed to load configuration", cause=e)
        ```
    """

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
    """Error that occurs during network operations.
    
    This error is raised when a network operation fails, such as
    when a connection is refused, times out, or encounters other
    network-related issues.
    
    Examples:
        ```python
        try:
            # Make a network request
            response = await client.get(url)
        except Exception as e:
            raise NetworkError("Failed to reach service", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"network error: {message}", cause)


class ConnectionError(NetworkError):
    """Error that occurs when connecting to a service.
    
    This error is raised when establishing a connection to a service fails,
    such as when the service is unavailable or the connection is refused.
    
    Examples:
        ```python
        try:
            connection = await connect_to_service(url)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {url}", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(message, cause)


class ServiceDiscoveryError(NetworkError):
    """Error that occurs during service discovery.
    
    This error is raised when service discovery operations fail, such as
    when registering a service provider or discovering a service.
    
    Examples:
        ```python
        try:
            service = await discover_service("database")
        except Exception as e:
            raise ServiceDiscoveryError("Failed to discover database service", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"service discovery error: {message}", cause)


class MetricsError(PyWattSDKError):
    """Error that occurs during metrics operations.
    
    This error is raised when metrics collection, reporting, or
    configuration fails.
    
    Examples:
        ```python
        try:
            # Report a metric
            await metrics.increment("requests_total")
        except Exception as e:
            raise MetricsError("Failed to report metric", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"metrics error: {message}", cause)


class DatabaseError(PyWattSDKError):
    """Error that occurs during database operations.
    
    This error is raised when database queries, connections, or
    transactions fail.
    
    Examples:
        ```python
        try:
            # Execute a database query
            result = await db.execute("SELECT * FROM users")
        except Exception as e:
            raise DatabaseError("Failed to execute query", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"database error: {message}", cause)


class CacheError(PyWattSDKError):
    """Error that occurs during cache operations.
    
    This error is raised when cache operations such as get, set, or delete fail.
    
    Examples:
        ```python
        try:
            # Set a cache value
            await cache.set("key", "value")
        except Exception as e:
            raise CacheError("Failed to set cache value", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"cache error: {message}", cause)


class HttpError(NetworkError):
    """Error that occurs during HTTP operations.
    
    This error is raised when HTTP requests fail, such as when a server
    returns an error status code or when a request times out.
    
    Examples:
        ```python
        try:
            # Make an HTTP request
            response = await client.get("https://example.com/api")
            response.raise_for_status()
        except Exception as e:
            raise HttpError("Failed to make HTTP request", cause=e)
        ```
    """

    def __init__(self, message: str, status_code: Optional[int] = None, cause: Optional[Exception] = None) -> None:
        self.status_code = status_code
        if status_code is not None:
            super().__init__(f"HTTP error {status_code}: {message}", cause)
        else:
            super().__init__(f"HTTP error: {message}", cause)


class ServerError(PyWattSDKError):
    """Error that occurs during server operations.
    
    This error is raised when server operations such as starting, stopping,
    or handling requests fail.
    
    Examples:
        ```python
        try:
            # Start a server
            await server.start()
        except Exception as e:
            raise ServerError("Failed to start server", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"server error: {message}", cause)


class RegistrationError(PyWattSDKError):
    """Error that occurs during module registration.
    
    This error is raised when a module fails to register with the orchestrator
    or when service registration encounters issues.
    
    Examples:
        ```python
        try:
            # Register a module
            await module.register()
        except Exception as e:
            raise RegistrationError("Failed to register module", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"registration error: {message}", cause)


class AuthenticationError(PyWattSDKError):
    """Error that occurs during authentication operations.
    
    This error is raised when authentication fails, such as when
    invalid credentials are provided or the authentication service
    is unavailable.
    
    Examples:
        ```python
        try:
            # Authenticate with a service
            await client.authenticate(credentials)
        except Exception as e:
            raise AuthenticationError("Failed to authenticate", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"authentication error: {message}", cause)


class ModuleError(PyWattSDKError):
    """Error that occurs in module operation.
    
    This error is raised when a module encounters an error during its operation,
    such as when handling a request or performing a task.
    
    Examples:
        ```python
        try:
            # Perform module operation
            await module.process_request(request)
        except Exception as e:
            raise ModuleError("Failed to process request", cause=e)
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"module error: {message}", cause)


class OrchestrationError(PyWattSDKError):
    """Error returned by the orchestrator.
    
    This error is raised when the orchestrator returns an error response,
    such as when a request is invalid or the orchestrator encounters an issue.
    
    Examples:
        ```python
        try:
            # Call orchestrator API
            response = await orchestrator.get_services()
            if response.get("error"):
                raise OrchestrationError(response["error"])
        except Exception as e:
            if not isinstance(e, OrchestrationError):
                raise OrchestrationError("Failed to call orchestrator API", cause=e)
            raise
        ```
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"orchestration error: {message}", cause)


class Result(Generic[T]):
    """A Result type similar to Rust's Result<T, E>.
    
    This provides a more explicit way to handle operations that can fail,
    making error handling more visible in the code.
    
    Examples:
        ```python
        # Creating a successful Result
        result = Result.ok(value)
        
        # Creating an error Result
        result = Result.err(error)
        
        # Using a Result
        if result.is_ok():
            value = result.unwrap()
        else:
            error = result.unwrap_err()
            
        # Chaining operations
        result = (
            Result.ok(initial_value)
            .map(transform_value)
            .and_then(validate_value)
        )
        ```
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
        """Create a successful Result.
        
        Args:
            value: The success value
            
        Returns:
            A successful Result containing the value
        """
        return cls(value=value)

    @classmethod
    def err(cls, error: PyWattSDKError) -> "Result[T]":
        """Create an error Result.
        
        Args:
            error: The error value
            
        Returns:
            An error Result containing the error
        """
        return cls(error=error)

    def is_ok(self) -> bool:
        """Check if the Result is successful.
        
        Returns:
            True if the Result is successful, False otherwise
        """
        return self._error is None

    def is_err(self) -> bool:
        """Check if the Result is an error.
        
        Returns:
            True if the Result is an error, False otherwise
        """
        return self._error is not None

    def unwrap(self) -> T:
        """Get the value, raising an exception if it's an error.
        
        Returns:
            The success value
            
        Raises:
            PyWattSDKError: If the Result is an error
        """
        if self._error is not None:
            raise self._error
        assert self._value is not None
        return self._value

    def unwrap_or(self, default: T) -> T:
        """Get the value or return a default if it's an error.
        
        Args:
            default: The default value to return if the Result is an error
            
        Returns:
            The success value or the default value
        """
        if self._error is not None:
            return default
        assert self._value is not None
        return self._value

    def unwrap_err(self) -> PyWattSDKError:
        """Get the error, raising an exception if it's successful.
        
        Returns:
            The error value
            
        Raises:
            ValueError: If the Result is successful
        """
        if self._error is None:
            raise ValueError("Called unwrap_err on a successful Result")
        return self._error

    def map(self, func: Callable[[T], Any]) -> "Result":
        """Apply a function to the value if successful.
        
        Args:
            func: The function to apply to the value
            
        Returns:
            A new Result containing the result of applying the function
        """
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

    def and_then(self, func: Callable[[T], "Result"]) -> "Result":
        """Chain operations that return Results.
        
        Args:
            func: The function to apply to the value, which returns a Result
            
        Returns:
            The Result returned by the function, or the original error
        """
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


def wrap_exception(func: Callable) -> Callable:
    """Decorator to wrap exceptions in PyWattSDKError.
    
    This decorator wraps any exceptions raised by the decorated function
    in a PyWattSDKError, preserving the original exception as the cause.
    
    Args:
        func: The function to decorate
        
    Returns:
        The decorated function
        
    Examples:
        ```python
        @wrap_exception
        def risky_operation():
            # This might raise exceptions
            result = external_api_call()
            return result
        ```
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PyWattSDKError:
            raise  # Re-raise PyWattSDKError as-is
        except Exception as e:
            # Convert other exceptions to PyWattSDKError
            raise PyWattSDKError(str(e), cause=e)
    return wrapper


def wrap_async_exception(func: Callable) -> Callable:
    """Decorator to wrap exceptions in async functions.
    
    This decorator wraps any exceptions raised by the decorated async function
    in a PyWattSDKError, preserving the original exception as the cause.
    
    Args:
        func: The async function to decorate
        
    Returns:
        The decorated async function
        
    Examples:
        ```python
        @wrap_async_exception
        async def async_risky_operation():
            # This might raise exceptions
            result = await external_api_call()
            return result
        ```
    """
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
    """Format an error with its full chain of causes.
    
    This function recursively formats an error and all of its causes,
    providing a comprehensive error message that helps with debugging.
    
    Args:
        error: The exception to format
        
    Returns:
        A formatted string representing the error chain
    """
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
    """Get the current error context (stack trace).
    
    Returns:
        A string containing the current stack trace
    """
    return traceback.format_exc()
