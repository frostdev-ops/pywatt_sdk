"""Typed secret wrapper for PyWatt SDK.

This module provides a Secret wrapper class that prevents accidental exposure
of sensitive data while providing type-safe access to secret values.
"""

from typing import Any, Generic, TypeVar, Union, TYPE_CHECKING
import weakref

try:
    from ..core.error import SecretError
except ImportError:
    class SecretError(Exception):
        pass

try:
    from ..core.logging import register_secret_for_redaction
except ImportError:
    def register_secret_for_redaction(secret):
        pass

if TYPE_CHECKING:
    from .secret_client import SecretClient

T = TypeVar("T")


class Secret(Generic[T]):
    """A wrapper for secret values that prevents accidental exposure.
    
    This class is similar to the Rust secrecy crate's Secret type,
    providing controlled access to sensitive data.
    """
    
    def __init__(self, value: T) -> None:
        """Initialize a secret with the given value.
        
        Args:
            value: The secret value to wrap
        """
        self._value = value
        
        # Register the string representation for redaction
        register_secret_for_redaction(str(value))
    
    def expose_secret(self) -> T:
        """Expose the secret value.
        
        This method name makes it explicit that sensitive data is being accessed.
        
        Returns:
            The wrapped secret value
        """
        return self._value
    
    def __str__(self) -> str:
        """String representation that doesn't expose the secret."""
        return "[REDACTED]"
    
    def __repr__(self) -> str:
        """Representation that doesn't expose the secret."""
        return f"Secret<{type(self._value).__name__}>([REDACTED])"
    
    def __eq__(self, other: Any) -> bool:
        """Compare secrets by their values."""
        if isinstance(other, Secret):
            return self._value == other._value
        return False
    
    def __hash__(self) -> int:
        """Hash based on the secret value."""
        return hash(self._value)


class TypedSecretError(SecretError):
    """Error that occurs during typed secret operations."""
    
    def __init__(self, message: str, cause: Exception = None) -> None:
        super().__init__(f"typed secret error: {message}", cause)


async def get_typed_secret(client: "SecretClient", key: str, target_type: type) -> Secret[Any]:
    """Get a secret and parse it to the specified type.
    
    Args:
        client: The secret client to use
        key: The secret key to retrieve
        target_type: The type to parse the secret value to
        
    Returns:
        A Secret wrapper containing the parsed value
        
    Raises:
        TypedSecretError: If the secret cannot be retrieved or parsed
    """
    try:
        # Get the raw secret value
        raw_secret = await client.get_secret(key)
        raw_value = raw_secret.expose_secret()
        
        # Parse to the target type
        if target_type == str:
            parsed_value = str(raw_value)
        elif target_type == int:
            parsed_value = int(raw_value)
        elif target_type == float:
            parsed_value = float(raw_value)
        elif target_type == bool:
            # Handle boolean parsing
            if isinstance(raw_value, bool):
                parsed_value = raw_value
            elif isinstance(raw_value, str):
                lower_val = raw_value.lower()
                if lower_val in ('true', '1', 'yes', 'on'):
                    parsed_value = True
                elif lower_val in ('false', '0', 'no', 'off'):
                    parsed_value = False
                else:
                    raise ValueError(f"Cannot parse '{raw_value}' as boolean")
            else:
                parsed_value = bool(raw_value)
        else:
            # Try to construct the type directly
            parsed_value = target_type(raw_value)
        
        return Secret(parsed_value)
        
    except Exception as e:
        raise TypedSecretError(f"failed to get typed secret '{key}' as {target_type.__name__}: {e}", e)


async def get_string_secret(client: "SecretClient", key: str) -> Secret[str]:
    """Get a secret as a string.
    
    Args:
        client: The secret client to use
        key: The secret key to retrieve
        
    Returns:
        A Secret wrapper containing the string value
    """
    return await get_typed_secret(client, key, str)


async def get_int_secret(client: "SecretClient", key: str) -> Secret[int]:
    """Get a secret as an integer.
    
    Args:
        client: The secret client to use
        key: The secret key to retrieve
        
    Returns:
        A Secret wrapper containing the integer value
    """
    return await get_typed_secret(client, key, int)


async def get_float_secret(client: "SecretClient", key: str) -> Secret[float]:
    """Get a secret as a float.
    
    Args:
        client: The secret client to use
        key: The secret key to retrieve
        
    Returns:
        A Secret wrapper containing the float value
    """
    return await get_typed_secret(client, key, float)


async def get_bool_secret(client: "SecretClient", key: str) -> Secret[bool]:
    """Get a secret as a boolean.
    
    Args:
        client: The secret client to use
        key: The secret key to retrieve
        
    Returns:
        A Secret wrapper containing the boolean value
    """
    return await get_typed_secret(client, key, bool)


# Convenience type aliases
SecretString = Secret[str]
SecretInt = Secret[int]
SecretFloat = Secret[float]
SecretBool = Secret[bool]

# Main alias for backward compatibility and expected interface
TypedSecret = Secret

__all__ = [
    "Secret",
    "TypedSecret",
    "TypedSecretError",
    "get_typed_secret",
    "get_string_secret",
    "get_int_secret", 
    "get_float_secret",
    "get_bool_secret",
    "SecretString",
    "SecretInt", 
    "SecretFloat",
    "SecretBool",
] 