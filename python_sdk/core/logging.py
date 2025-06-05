"""Structured logging with secret redaction for PyWatt modules.

This module provides logging functionality that mirrors the Rust SDK's approach,
with JSON structured logging to stderr and automatic secret redaction.
"""

import json
import logging
import logging.config
import os
import re
import sys
import threading
from typing import Any, Dict, List, Optional, Set
from datetime import datetime
import weakref


# Global registry for secrets to redact
_SECRET_REGISTRY: Set[str] = set()
_SECRET_REGISTRY_LOCK = threading.Lock()

# Weak references to secret objects for automatic cleanup
_SECRET_OBJECTS: Set[weakref.ref] = set()
_SECRET_OBJECTS_LOCK = threading.Lock()


class SecretRedactionFilter(logging.Filter):
    """Logging filter that automatically redacts registered secrets."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records to redact secrets."""
        # Redact secrets in the message
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        
        # Redact secrets in arguments
        if hasattr(record, 'args') and record.args:
            redacted_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    redacted_args.append(redact_secrets(arg))
                else:
                    redacted_args.append(arg)
            record.args = tuple(redacted_args)
        
        return True


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)


def init_module() -> None:
    """Initialize stderr logging with JSON format and secret redaction.
    
    This should be the **first** call in every module's main function before any
    logging or secret retrieval occurs.
    
    Sets up a logging configuration that:
    - Writes JSON logs to stderr
    - Automatically redacts registered secrets
    - Respects PYWATT_LOG_LEVEL environment variable
    - Uses structured logging format
    """
    # Get log level from environment
    log_level = os.getenv("PYWATT_LOG_LEVEL", "INFO").upper()
    
    # Validate log level
    numeric_level = getattr(logging, log_level, None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create stderr handler with JSON formatter and secret redaction
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(numeric_level)
    
    # Add secret redaction filter
    stderr_handler.addFilter(SecretRedactionFilter())
    
    # Set JSON formatter
    json_formatter = JSONFormatter()
    stderr_handler.setFormatter(json_formatter)
    
    # Add handler to root logger
    root_logger.addHandler(stderr_handler)
    
    # Log initialization
    logging.info("PyWatt SDK logging initialized", extra={
        'extra_fields': {
            'log_level': log_level,
            'handler': 'stderr',
            'format': 'json'
        }
    })


def register_secret_for_redaction(secret_value: str) -> None:
    """Register a secret value for automatic redaction in logs.
    
    Args:
        secret_value: The secret string to redact from logs
    """
    if not secret_value or len(secret_value.strip()) == 0:
        return
    
    with _SECRET_REGISTRY_LOCK:
        _SECRET_REGISTRY.add(secret_value.strip())


def register_secret_object_for_redaction(secret_obj: Any) -> None:
    """Register a secret object for automatic redaction.
    
    This creates a weak reference to the object and will automatically
    extract and redact its string representation.
    
    Args:
        secret_obj: The secret object to redact
    """
    def cleanup_callback(ref):
        with _SECRET_OBJECTS_LOCK:
            _SECRET_OBJECTS.discard(ref)
    
    with _SECRET_OBJECTS_LOCK:
        weak_ref = weakref.ref(secret_obj, cleanup_callback)
        _SECRET_OBJECTS.add(weak_ref)
        
        # Also register the string representation
        if hasattr(secret_obj, 'expose_secret'):
            # For secrecy-style objects
            register_secret_for_redaction(str(secret_obj.expose_secret()))
        else:
            register_secret_for_redaction(str(secret_obj))


def redact_secrets(text: str) -> str:
    """Redact all registered secrets from the given text.
    
    Args:
        text: The text to redact secrets from
        
    Returns:
        The text with secrets replaced by [REDACTED]
    """
    if not text:
        return text
    
    result = text
    
    with _SECRET_REGISTRY_LOCK:
        for secret in _SECRET_REGISTRY:
            if secret in result:
                result = result.replace(secret, "[REDACTED]")
    
    # Also check weak references to secret objects
    with _SECRET_OBJECTS_LOCK:
        for weak_ref in list(_SECRET_OBJECTS):
            secret_obj = weak_ref()
            if secret_obj is not None:
                if hasattr(secret_obj, 'expose_secret'):
                    secret_value = str(secret_obj.expose_secret())
                else:
                    secret_value = str(secret_obj)
                
                if secret_value in result:
                    result = result.replace(secret_value, "[REDACTED]")
    
    return result


def safe_log(level: str, message: str, **kwargs) -> None:
    """Log a message with automatic secret redaction.
    
    This function ensures that any secrets in the message or arguments
    are automatically redacted before logging.
    
    Args:
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        **kwargs: Additional fields to include in the log
    """
    logger = logging.getLogger(__name__)
    
    # Redact the message
    safe_message = redact_secrets(message)
    
    # Redact kwargs
    safe_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, str):
            safe_kwargs[key] = redact_secrets(value)
        else:
            safe_kwargs[key] = value
    
    # Get the logging method
    log_method = getattr(logger, level.lower(), logger.info)
    
    # Log with extra fields
    if safe_kwargs:
        log_method(safe_message, extra={'extra_fields': safe_kwargs})
    else:
        log_method(safe_message)


def clear_secret_registry() -> None:
    """Clear all registered secrets (mainly for testing)."""
    with _SECRET_REGISTRY_LOCK:
        _SECRET_REGISTRY.clear()
    
    with _SECRET_OBJECTS_LOCK:
        _SECRET_OBJECTS.clear()


def get_registered_secrets_count() -> int:
    """Get the number of registered secrets (for testing/debugging)."""
    with _SECRET_REGISTRY_LOCK:
        return len(_SECRET_REGISTRY)


# Convenience functions for different log levels
def debug(message: str, **kwargs) -> None:
    """Log a debug message with secret redaction."""
    safe_log("debug", message, **kwargs)


def info(message: str, **kwargs) -> None:
    """Log an info message with secret redaction."""
    safe_log("info", message, **kwargs)


def warning(message: str, **kwargs) -> None:
    """Log a warning message with secret redaction."""
    safe_log("warning", message, **kwargs)


def error(message: str, **kwargs) -> None:
    """Log an error message with secret redaction."""
    safe_log("error", message, **kwargs)


def critical(message: str, **kwargs) -> None:
    """Log a critical message with secret redaction."""
    safe_log("critical", message, **kwargs)


# Alias for compatibility
warn = warning 


def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance with PyWatt SDK configuration.
    
    Args:
        name: Logger name. If None, uses the calling module's name.
        
    Returns:
        A configured logger instance with secret redaction
    """
    if name is None:
        # Get the caller's module name
        import inspect
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back
            caller_module = caller_frame.f_globals.get('__name__', __name__)
            name = caller_module
        finally:
            del frame
    
    logger = logging.getLogger(name)
    
    # Ensure the logger has secret redaction filter
    if not any(isinstance(f, SecretRedactionFilter) for f in logger.filters):
        logger.addFilter(SecretRedactionFilter())
    
    return logger