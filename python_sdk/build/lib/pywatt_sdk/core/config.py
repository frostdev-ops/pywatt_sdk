"""Configuration management for PyWatt SDK.

This module provides configuration classes and utilities for managing
application settings with validation and default values.
"""

import os
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field, validator
from enum import Enum


class LogLevel(str, Enum):
    """Supported log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Config(BaseModel):
    """Base configuration class with common settings."""
    
    # Logging configuration
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")
    log_format: str = Field(default="json", description="Log format (json or text)")
    
    # Module configuration
    module_id: Optional[str] = Field(default=None, description="Module identifier")
    orchestrator_api: Optional[str] = Field(default=None, description="Orchestrator API URL")
    
    # Timeouts and limits
    ipc_timeout_seconds: int = Field(default=30, description="IPC operation timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retries for operations")
    
    # Feature flags
    enable_metrics: bool = Field(default=False, description="Enable Prometheus metrics")
    enable_health_check: bool = Field(default=True, description="Enable health check endpoint")
    
    class Config:
        """Pydantic configuration."""
        env_prefix = "PYWATT_"
        case_sensitive = False
        
    @validator('log_level', pre=True)
    def validate_log_level(cls, v):
        """Validate and normalize log level."""
        if isinstance(v, str):
            return v.upper()
        return v
    
    @validator('orchestrator_api')
    def validate_orchestrator_api(cls, v):
        """Validate orchestrator API URL."""
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError("Orchestrator API URL must start with http:// or https://")
        return v
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Create configuration from dictionary."""
        return cls(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return self.dict()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        return getattr(self, key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value by key."""
        setattr(self, key, value)


def get_env_var(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Get environment variable with optional default and required validation.
    
    Args:
        name: Environment variable name
        default: Default value if not found
        required: Whether the variable is required
        
    Returns:
        Environment variable value or default
        
    Raises:
        ValueError: If required variable is not found
    """
    value = os.getenv(name, default)
    
    if required and value is None:
        raise ValueError(f"Required environment variable {name} is not set")
    
    return value


def get_env_bool(name: str, default: bool = False) -> bool:
    """Get boolean environment variable.
    
    Args:
        name: Environment variable name
        default: Default value if not found
        
    Returns:
        Boolean value
    """
    value = os.getenv(name)
    if value is None:
        return default
    
    return value.lower() in ('true', '1', 'yes', 'on')


def get_env_int(name: str, default: int = 0) -> int:
    """Get integer environment variable.
    
    Args:
        name: Environment variable name
        default: Default value if not found
        
    Returns:
        Integer value
    """
    value = os.getenv(name)
    if value is None:
        return default
    
    try:
        return int(value)
    except ValueError:
        return default


def get_env_float(name: str, default: float = 0.0) -> float:
    """Get float environment variable.
    
    Args:
        name: Environment variable name
        default: Default value if not found
        
    Returns:
        Float value
    """
    value = os.getenv(name)
    if value is None:
        return default
    
    try:
        return float(value)
    except ValueError:
        return default


def load_config_from_file(file_path: str) -> Dict[str, Any]:
    """Load configuration from a file.
    
    Supports JSON and YAML formats based on file extension.
    
    Args:
        file_path: Path to configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is not supported
    """
    import json
    from pathlib import Path
    
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    
    if path.suffix.lower() == '.json':
        with open(path, 'r') as f:
            return json.load(f)
    elif path.suffix.lower() in ('.yml', '.yaml'):
        try:
            import yaml
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except ImportError:
            raise ValueError("PyYAML is required to load YAML configuration files")
    else:
        raise ValueError(f"Unsupported configuration file format: {path.suffix}")


def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
    """Merge multiple configuration dictionaries.
    
    Later configurations override earlier ones.
    
    Args:
        *configs: Configuration dictionaries to merge
        
    Returns:
        Merged configuration dictionary
    """
    result = {}
    for config in configs:
        result.update(config)
    return result 