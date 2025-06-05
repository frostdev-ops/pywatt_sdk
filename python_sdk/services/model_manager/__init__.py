"""Database Model Manager for PyWatt SDK.

This module provides database-agnostic model definition and
schema generation tools for SQL databases.
"""

from .definitions import (
    IntegerSize,
    DataType,
    ReferentialAction,
    Constraint,
    ColumnDescriptor,
    IndexType,
    IndexDescriptor,
    ModelDescriptor,
)
from .errors import ModelManagerError
from .generator import ModelGenerator
from .builder import ModelBuilder
from .manager import ModelManager
from .adapters import (
    DatabaseAdapter,
    SqliteAdapter,
    PostgresAdapter,
    MySqlAdapter,
    get_adapter_for_database_type,
)

# Public API functions
from .api import (
    create_generator_for_database,
    validate_model,
    generate_complete_sql,
    create_simple_model,
)

__all__ = [
    # Data types
    "IntegerSize",
    "DataType",
    "ReferentialAction",
    "Constraint",
    "ColumnDescriptor",
    "IndexType",
    "IndexDescriptor",
    "ModelDescriptor",
    
    # Errors
    "ModelManagerError",
    
    # Core classes
    "ModelGenerator",
    "ModelBuilder",
    "ModelManager",
    
    # Adapters
    "DatabaseAdapter",
    "SqliteAdapter",
    "PostgresAdapter",
    "MySqlAdapter",
    "get_adapter_for_database_type",
    
    # API functions
    "create_generator_for_database",
    "validate_model",
    "generate_complete_sql",
    "create_simple_model",
] 