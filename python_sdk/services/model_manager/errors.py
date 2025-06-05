"""Error types for the Model Manager."""

from typing import Optional


class ModelManagerError(Exception):
    """Base exception for Model Manager errors."""
    
    def __init__(self, message: str, cause: Optional[Exception] = None):
        """Initialize the error.
        
        Args:
            message: Error message
            cause: Optional underlying exception
        """
        super().__init__(message)
        self.cause = cause


class ModelDefinitionError(ModelManagerError):
    """Error in model definition or validation."""
    pass


class DatabaseAdapterError(ModelManagerError):
    """Error in database adapter operations."""
    pass


class UnsupportedFeatureError(ModelManagerError):
    """Feature not supported by the database or configuration."""
    pass


class SqlGenerationError(ModelManagerError):
    """Error generating SQL statements."""
    pass


class ModelApplicationError(ModelManagerError):
    """Error applying model to database."""
    pass 